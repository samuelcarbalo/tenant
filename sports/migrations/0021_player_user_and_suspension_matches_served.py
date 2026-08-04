# Generated manually for player user link and suspension matches_served

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("sports", "0020_playersuspension"),
    ]

    operations = [
        migrations.AddField(
            model_name="player",
            name="user",
            field=models.ForeignKey(
                blank=True,
                help_text="Usuario vinculado al registro automático del jugador.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="player_profiles",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="playersuspension",
            name="matches_served",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="Partidos de sanción ya cumplidos.",
            ),
        ),
    ]
