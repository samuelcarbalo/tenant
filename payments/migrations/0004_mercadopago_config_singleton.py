"""Crea la fila singleton de MercadoPagoConfig si no existe."""

from django.db import migrations


def create_mercadopago_config_singleton(apps, schema_editor):
    MercadoPagoConfig = apps.get_model("payments", "MercadoPagoConfig")
    MercadoPagoConfig.objects.get_or_create(
        pk=1,
        defaults={"is_production": False},
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0003_mercadopago_config"),
    ]

    operations = [
        migrations.RunPython(create_mercadopago_config_singleton, noop_reverse),
    ]
