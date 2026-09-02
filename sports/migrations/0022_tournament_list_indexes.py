from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sports", "0021_player_user_and_suspension_matches_served"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tournament",
            name="sport_type",
            field=models.CharField(
                choices=[
                    ("football", "Fútbol"),
                    ("basketball", "Baloncesto"),
                    ("tennis", "Tenis"),
                    ("volleyball", "Voleibol"),
                    ("softball", "Softbol"),
                    ("other", "Otro"),
                ],
                db_index=True,
                default="football",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="tournament",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Borrador"),
                    ("registration", "Inscripción"),
                    ("active", "En curso"),
                    ("finished", "Finalizado"),
                    ("cancelled", "Cancelado"),
                ],
                db_index=True,
                default="draft",
                max_length=20,
            ),
        ),
        migrations.AddIndex(
            model_name="tournament",
            index=models.Index(
                fields=["sport_type", "status", "-start_date"],
                name="tourn_sport_status_start",
            ),
        ),
        migrations.AddIndex(
            model_name="tournament",
            index=models.Index(
                fields=["moderation_status", "status", "-start_date"],
                name="tourn_mod_status_start",
            ),
        ),
        migrations.AddIndex(
            model_name="tournament",
            index=models.Index(
                fields=["posted_by", "-start_date"],
                name="tourn_posted_by_start",
            ),
        ),
        migrations.AddIndex(
            model_name="tournament",
            index=models.Index(
                fields=["organization", "-start_date"],
                name="tourn_org_start",
            ),
        ),
    ]
