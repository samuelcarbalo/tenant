"""Rastreo de impresiones de banners y reporte de métricas para Super Admin L1/L2."""

from datetime import datetime, time, timedelta

from django.db.models import Count, F, Q
from django.db.models.functions import TruncDay
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import user_is_module_super_admin
from sports.models import AdvertisementBanner

from .models import AdImpression

DEDUP_WINDOW = timedelta(seconds=60)
DEFAULT_RANGE_DAYS = 7
MAX_RANGE_DAYS = 366


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")
    return ip or None


def record_ad_impression(ad, request) -> bool:
    """Registra la impresión salvo que el mismo espectador ya la haya contado en la última ventana."""
    user = request.user if request.user.is_authenticated else None
    ip = client_ip(request)
    user_agent = (request.META.get("HTTP_USER_AGENT") or "")[:255]

    recent = AdImpression.objects.filter(ad=ad, viewed_at__gte=timezone.now() - DEDUP_WINDOW)
    recent = recent.filter(user=user) if user else recent.filter(
        user__isnull=True, ip_address=ip, user_agent=user_agent
    )
    if recent.exists():
        return False

    AdImpression.objects.create(ad=ad, user=user, ip_address=ip, user_agent=user_agent)
    AdvertisementBanner.objects.filter(pk=ad.pk).update(impressions=F("impressions") + 1)
    return True


class TrackAdImpressionView(APIView):
    """POST /api/v1/ads/{id}/track-impression/ — público y ligero."""

    permission_classes = [AllowAny]

    def post(self, request, ad_id):
        ad = get_object_or_404(AdvertisementBanner.objects.only("id"), pk=ad_id)
        counted = record_ad_impression(ad, request)
        return Response({"counted": counted}, status=status.HTTP_200_OK)


def _sponsor_name(banner) -> str:
    owner = None
    if banner.sponsorship_id:
        owner = banner.sponsorship.posted_by
    elif banner.campaign_id:
        owner = banner.campaign.posted_by
    else:
        owner = banner.posted_by
    if owner is None:
        return ""
    return (getattr(owner, "full_name", "") or "").strip() or owner.email


def _parse_range(params):
    today = timezone.localdate()
    raw_start, raw_end = params.get("start"), params.get("end")
    end = parse_date(raw_end) if raw_end else today
    start = parse_date(raw_start) if raw_start else end - timedelta(days=DEFAULT_RANGE_DAYS - 1)
    if start is None or end is None:
        raise ValidationError({"detail": "Fechas inválidas. Usa el formato YYYY-MM-DD."})
    if start > end:
        raise ValidationError({"detail": "La fecha de inicio no puede ser posterior a la fecha fin."})
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise ValidationError({"detail": f"El rango máximo es de {MAX_RANGE_DAYS} días."})
    return start, end


class AdAnalyticsView(APIView):
    """
    GET /api/v1/admin/ads/analytics/?start=YYYY-MM-DD&end=YYYY-MM-DD&ad=<uuid>
    Solo Super Admin Nivel 1 / Nivel 2. Días agrupados en America/Bogota.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not user_is_module_super_admin(request.user):
            raise PermissionDenied("Solo Super Administradores (Nivel 1 o Nivel 2).")

        start, end = _parse_range(request.query_params)
        tz = timezone.get_current_timezone()
        start_dt = timezone.make_aware(datetime.combine(start, time.min), tz)
        end_dt = timezone.make_aware(datetime.combine(end + timedelta(days=1), time.min), tz)

        selected = None
        ad_id = request.query_params.get("ad")
        impressions = AdImpression.objects.filter(viewed_at__gte=start_dt, viewed_at__lt=end_dt)
        if ad_id:
            selected = AdvertisementBanner.objects.filter(pk=ad_id).first()
            if selected is None:
                raise ValidationError({"ad": "Anuncio no encontrado."})
            impressions = impressions.filter(ad=selected)

        per_day = {
            row["day"].date(): row["views"]
            for row in impressions.annotate(day=TruncDay("viewed_at", tzinfo=tz))
            .values("day")
            .annotate(views=Count("id"))
            .order_by("day")
        }
        daily = []
        current = start
        while current <= end:
            daily.append({"date": current.isoformat(), "views": per_day.get(current, 0)})
            current += timedelta(days=1)
        total_views = sum(item["views"] for item in daily)
        peak = max(daily, key=lambda item: item["views"]) if total_views else None

        in_range = Q(impression_logs__viewed_at__gte=start_dt, impression_logs__viewed_at__lt=end_dt)
        banners = (
            AdvertisementBanner.objects.select_related(
                "tournament", "posted_by", "sponsorship__posted_by", "campaign__posted_by"
            )
            .annotate(
                views_in_range=Count("impression_logs", filter=in_range),
                total_views=Count("impression_logs"),
            )
            .order_by("-views_in_range", "-total_views", "title")
        )

        ads = [
            {
                "id": str(banner.id),
                "title": banner.title,
                "sponsor": _sponsor_name(banner),
                "position": banner.position,
                "position_display": banner.get_position_display(),
                "tournament_name": banner.tournament.name if banner.tournament_id else "",
                "is_active": bool(banner.is_visible),
                "start_date": banner.start_date.isoformat() if banner.start_date else None,
                "end_date": banner.end_date.isoformat() if banner.end_date else None,
                "views_in_range": banner.views_in_range,
                "total_views": banner.total_views,
                "clicks": banner.clicks,
            }
            for banner in banners
        ]

        return Response(
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "timezone": str(tz),
                "ad": {"id": str(selected.id), "title": selected.title} if selected else None,
                "total_views": total_views,
                "peak_day": peak,
                "daily": daily,
                "ads": ads,
            }
        )
