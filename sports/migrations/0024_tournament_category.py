from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sports", "0023_alter_tournament_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="tournament",
            name="category",
            field=models.CharField(
                choices=[
                    ("libre", "Libre"),
                    ("sub-13", "Sub-13"),
                    ("sub-15", "Sub-15"),
                    ("sub-17", "Sub-17"),
                    ("sub-20", "Sub-20"),
                    ("femenino", "Femenino"),
                    ("mixto", "Mixto"),
                    ("veteranos", "Veteranos"),
                ],
                db_index=True,
                default="libre",
                help_text="Categoría competitiva del torneo (fútbol y demás deportes).",
                max_length=20,
                verbose_name="Categoría",
            ),
        ),
    ]
