from django.contrib.contenttypes.models import ContentType
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from moderation.models import ReportePublicacion
from moderation.serializers import CreateReportSerializer, ReportePublicacionSerializer
from moderation.services import CONTENT_TYPE_MAP, apply_moderation_if_needed


class ReportViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def create(self, request):
        serializer = CreateReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        model_class = CONTENT_TYPE_MAP[data["content_type"]]
        content_type = ContentType.objects.get_for_model(model_class)

        if not model_class.objects.filter(pk=data["object_id"]).exists():
            return Response({"detail": "Publicación no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        if ReportePublicacion.objects.filter(
            reporter=request.user,
            content_type=content_type,
            object_id=data["object_id"],
        ).exists():
            return Response(
                {"detail": "Ya reportaste esta publicación."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        report = ReportePublicacion.objects.create(
            reporter=request.user,
            content_type=content_type,
            object_id=data["object_id"],
            reason=data["reason"],
            description=data.get("description", ""),
        )

        apply_moderation_if_needed(content_type, data["object_id"])

        return Response(
            ReportePublicacionSerializer(report).data,
            status=status.HTTP_201_CREATED,
        )
