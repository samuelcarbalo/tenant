import csv
from datetime import datetime
from io import StringIO

from django.http import HttpResponse
from django.db.models import Q

from authentication.models import CreditSubscriptionTransaction
from ecommerce.models import ShopOrder
from events.models import EventListing
from payments.advertising_packages import CREDIT_COST_EVENT
from payments.packages import CREDIT_VALUE_COP


STATUS_LABEL = {
    "pending": "Pendiente",
    "approved": "Completado",
    "rejected": "Rechazado",
    "cancelled": "Cancelado",
    "refunded": "Reembolsado",
    "issued": "Completado",
    "void": "Anulado",
    "completed": "Completado",
}


def _dt(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def build_payment_ledger(category: str = "all", search: str = "", date_from: str = "", date_to: str = ""):
    category = (category or "all").lower()
    rows = []

    if category in ("all", "shop", "tienda"):
        qs = ShopOrder.objects.select_related("buyer", "organization", "invoice")
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        if search:
            qs = qs.filter(
                Q(buyer__email__icontains=search)
                | Q(buyer__first_name__icontains=search)
                | Q(invoice__number__icontains=search)
                | Q(mp_payment_id__icontains=search)
            )
        for order in qs.order_by("-created_at")[:500]:
            buyer = order.buyer
            invoice_number = ""
            try:
                invoice_number = order.invoice.number
            except Exception:
                invoice_number = ""
            rows.append(
                {
                    "id": str(order.id),
                    "category": "tienda",
                    "category_label": "Tienda",
                    "payer_name": (getattr(buyer, "full_name", None) or "").strip() or buyer.email,
                    "payer_email": buyer.email,
                    "amount": float(order.total_cop),
                    "amount_unit": "COP",
                    "amount_label": f"${order.total_cop:,.0f} COP".replace(",", "."),
                    "payment_method": "Mercado Pago",
                    "status": order.status,
                    "status_label": STATUS_LABEL.get(order.status, order.status),
                    "created_at": _dt(order.created_at),
                    "reference": invoice_number or order.mp_payment_id or str(order.id)[:8],
                }
            )

    if category in ("all", "sports", "deportes"):
        qs = CreditSubscriptionTransaction.objects.select_related("user")
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        if search:
            qs = qs.filter(
                Q(user__email__icontains=search) | Q(user__first_name__icontains=search)
            )
        for tx in qs.order_by("-created_at")[:500]:
            user = tx.user
            cop = tx.credits_spent * CREDIT_VALUE_COP
            rows.append(
                {
                    "id": str(tx.id),
                    "category": "deportes",
                    "category_label": "Deportes",
                    "payer_name": (getattr(user, "full_name", None) or "").strip() or user.email,
                    "payer_email": user.email,
                    "amount": tx.credits_spent,
                    "amount_unit": "credits",
                    "amount_label": f"{tx.credits_spent} créditos (~${cop:,.0f} COP)".replace(",", "."),
                    "payment_method": "Créditos",
                    "status": "approved",
                    "status_label": "Completado",
                    "created_at": _dt(tx.created_at),
                    "reference": "Módulo Deportivo 30 días",
                }
            )

    if category in ("all", "events", "eventos"):
        qs = EventListing.objects.select_related("posted_by")
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        if search:
            qs = qs.filter(
                Q(posted_by__email__icontains=search)
                | Q(title__icontains=search)
                | Q(posted_by__first_name__icontains=search)
            )
        cop = CREDIT_COST_EVENT * CREDIT_VALUE_COP
        for ev in qs.order_by("-created_at")[:500]:
            user = ev.posted_by
            rows.append(
                {
                    "id": str(ev.id),
                    "category": "eventos",
                    "category_label": "Eventos",
                    "payer_name": (getattr(user, "full_name", None) or "").strip() or user.email,
                    "payer_email": user.email,
                    "amount": CREDIT_COST_EVENT,
                    "amount_unit": "credits",
                    "amount_label": f"{CREDIT_COST_EVENT} créditos (~${cop:,.0f} COP)".replace(",", "."),
                    "payment_method": "Créditos",
                    "status": "approved",
                    "status_label": "Completado",
                    "created_at": _dt(ev.created_at),
                    "reference": f"Publicación: {ev.title[:80]}",
                }
            )

    rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return rows


def ledger_csv_response(rows):
    buf = StringIO()
    buf.write("\ufeff")
    writer = csv.writer(buf)
    writer.writerow(
        [
            "ID Transacción",
            "Categoría",
            "Usuario",
            "Correo",
            "Monto",
            "Unidad",
            "Método de pago",
            "Estado",
            "Fecha",
            "Referencia",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row["id"],
                row["category_label"],
                row["payer_name"],
                row["payer_email"],
                row["amount"],
                row["amount_unit"],
                row["payment_method"],
                row["status_label"],
                row["created_at"],
                row["reference"],
            ]
        )
    response = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="historial-pagos-chever.csv"'
    return response
