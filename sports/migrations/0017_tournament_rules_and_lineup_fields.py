from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sports", "0016_bracket_models"),
    ]

    operations = [
        migrations.AddField(
            model_name="tournament",
            name="rules_url",
            field=models.URLField(blank=True, max_length=500, verbose_name="Reglamento (URL)"),
        ),
        migrations.AddField(
            model_name="tournament",
            name="lineup_size",
            field=models.PositiveSmallIntegerField(
                default=9,
                help_text="Titulares en campo: 9 estándar, 10 con bateador designado (softbol).",
            ),
        ),
        migrations.AddField(
            model_name="matchlineup",
            name="batting_order",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AlterModelOptions(
            name="matchlineup",
            options={"ordering": ["batting_order", "-is_starter", "jersey_number"]},
        ),
    ]
