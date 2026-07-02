from rest_framework import serializers

from moderation.models import ReportePublicacion


class CreateReportSerializer(serializers.Serializer):
    content_type = serializers.ChoiceField(
        choices=["job", "real_estate", "tournament", "event"],
        help_text="Tipo: job, real_estate, tournament, event",
    )
    object_id = serializers.UUIDField()
    reason = serializers.ChoiceField(choices=[c[0] for c in ReportePublicacion.REASON_CHOICES])
    description = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class ReportePublicacionSerializer(serializers.ModelSerializer):
    reporter_email = serializers.EmailField(source="reporter.email", read_only=True)

    class Meta:
        model = ReportePublicacion
        fields = ["id", "content_type", "object_id", "reason", "description", "reporter_email", "created_at"]
        read_only_fields = fields
