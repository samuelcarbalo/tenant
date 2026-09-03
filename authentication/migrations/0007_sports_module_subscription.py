import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("authentication", "0006_user_admin_level"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="sports_module_active",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text="True si la suscripción al Servicio de Torneos está vigente.",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="sports_module_expires_at",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                help_text="Fecha de vencimiento del acceso CRUD ilimitado al módulo deportivo.",
                null=True,
            ),
        ),
        migrations.CreateModel(
            name="CreditSubscriptionTransaction",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                (
                    "transaction_type",
                    models.CharField(
                        choices=[
                            (
                                "SPORTS_MODULE_SUBSCRIPTION",
                                "Suscripción Servicio de Torneos",
                            )
                        ],
                        db_index=True,
                        max_length=64,
                    ),
                ),
                ("credits_spent", models.PositiveIntegerField()),
                ("days_granted", models.PositiveIntegerField(default=30)),
                ("expires_at", models.DateTimeField()),
                ("notes", models.CharField(blank=True, max_length=255)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="subscription_transactions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "credit_subscription_transactions",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="creditsubscriptiontransaction",
            index=models.Index(
                fields=["user", "-created_at"],
                name="credit_sub_user_created_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="creditsubscriptiontransaction",
            index=models.Index(
                fields=["transaction_type", "-created_at"],
                name="credit_sub_type_created_idx",
            ),
        ),
    ]
