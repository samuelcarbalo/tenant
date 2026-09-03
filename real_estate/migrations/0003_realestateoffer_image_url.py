from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("real_estate", "0002_realestateoffer_moderation_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="realestateoffer",
            name="image_url",
            field=models.URLField(
                blank=True,
                help_text="URL pública de la imagen (archivo subido o enlace HTTPS).",
                max_length=500,
            ),
        ),
    ]
