# Generated manually for MercadoPagoConfig singleton

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0002_mp_webhook_events_and_payment_notifications"),
    ]

    operations = [
        migrations.CreateModel(
            name="MercadoPagoConfig",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "is_production",
                    models.BooleanField(
                        default=False,
                        help_text="Desactivado = credenciales de prueba (Test). Activado = Producción (Live).",
                    ),
                ),
                ("public_key_test", models.CharField(blank=True, max_length=255)),
                ("access_token_test", models.CharField(blank=True, max_length=512)),
                ("public_key_prod", models.CharField(blank=True, max_length=255)),
                ("access_token_prod", models.CharField(blank=True, max_length=512)),
                ("client_id_prod", models.CharField(blank=True, max_length=255)),
                ("client_secret_prod", models.CharField(blank=True, max_length=512)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Configuración Mercado Pago",
                "verbose_name_plural": "Configuración Mercado Pago",
                "db_table": "mercadopago_config",
            },
        ),
    ]
