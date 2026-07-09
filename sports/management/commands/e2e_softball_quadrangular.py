"""Prueba E2E: cuadrangular softbol + avance a final (Fases 1-3)."""

from django.core.management.base import BaseCommand
from django.utils import timezone

from authentication.models import User
from organizations.models import Organization
from sports.models import Match, Team, Tournament
from sports.services.structure import (
    apply_format_template,
    assign_teams_to_group,
    generate_round_robin_fixtures,
)
from sports.services.advancement import advance_phase
from sports.scoring import MatchResultService, StandingsService


class Command(BaseCommand):
    help = "E2E cuadrangular softbol + final"

    def handle(self, *args, **options):
        org, _ = Organization.objects.get_or_create(
            slug="e2e-municipio", defaults={"name": "E2E Municipio"}
        )
        user, created = User.objects.get_or_create(
            email="e2e-softbol@test.com",
            defaults={
                "username": "e2e_softbol",
                "organization": org,
                "role": "manager",
                "credits": 500,
            },
        )
        if not created:
            user.credits = 500
            user.save(update_fields=["credits"])

        slug = f"e2e-copa-softbol-{timezone.now().strftime('%H%M%S')}"
        tournament = Tournament.objects.create(
            name=f"E2E Copa Softbol {timezone.now().strftime('%H:%M')}",
            slug=slug,
            sport_type="softball",
            organization=org,
            posted_by=user,
            start_date=timezone.now().date(),
            end_date=timezone.now().date(),
            registration_deadline=timezone.now().date(),
        )
        apply_format_template(tournament, "single_quadrangular_final")
        tournament.status = "active"
        tournament.save(update_fields=["status"])

        names = ["Tigres", "Leones", "Aguilas", "Toros"]
        teams = []
        for i, name in enumerate(names, start=1):
            teams.append(
                Team.objects.create(
                    name=name,
                    slug=f"{slug}-t{i}",
                    abbreviation=name[:3].upper(),
                    tournament=tournament,
                    organization=org,
                    posted_by=user,
                )
            )

        phase = tournament.phases.get(slug="cuadrangular")
        group = phase.groups.get(slug="cuadrangular")
        assign_teams_to_group(group, [t.id for t in teams])
        generate_round_robin_fixtures(
            tournament, phase, group, user, timezone.now(), "Campo E2E"
        )

        alpha, beta, gamma, delta = teams
        pairs = [
            (alpha, beta, 5, 2),
            (alpha, gamma, 4, 1),
            (alpha, delta, 6, 0),
            (beta, gamma, 3, 2),
            (beta, delta, 4, 3),
            (gamma, delta, 2, 1),
        ]
        for home, away, hr, ar in pairs:
            m = Match.objects.get(
                tournament=tournament, home_team=home, away_team=away, phase=phase
            )
            MatchResultService.finalize_match(m, {"home_runs": hr, "away_runs": ar})

        standings = StandingsService.compute(tournament, phase=phase, group=group)
        self.stdout.write(self.style.SUCCESS("=== STANDINGS CUADRANGULAR ==="))
        for row in standings:
            t = row["team"]
            self.stdout.write(
                f"  {row['position']}. {t.name} — {row['won']}G {row['lost']}P "
                f"CR:{row['runs']} AVG:{row['average']:.3f}"
            )

        result = advance_phase(tournament, "cuadrangular", user, timezone.now())
        final = result["matches_created"][0]
        self.stdout.write(self.style.SUCCESS("\n=== FINAL GENERADA ==="))
        self.stdout.write(
            f"  {final.home_team.name} vs {final.away_team.name} (id={final.id})"
        )

        MatchResultService.finalize_match(final, {"home_runs": 3, "away_runs": 1})
        winner = final.winner
        self.stdout.write(self.style.SUCCESS(f"\n=== CAMPEON: {winner.name} ==="))

        import urllib.request
        import json

        base = "http://127.0.0.1:8000/api/v1"
        for path in (
            f"/sports/tournaments/{slug}/structure/",
            f"/sports/tournaments/{slug}/bracket/?phase=final",
            f"/sports/tournaments/{slug}/standings/?phase=cuadrangular&group=cuadrangular",
        ):
            with urllib.request.urlopen(base + path) as resp:
                assert resp.status == 200, path

        with urllib.request.urlopen(
            base + f"/sports/tournaments/{slug}/structure/"
        ) as resp:
            struct_data = json.loads(resp.read().decode())
        assert struct_data["phases"][1]["bracket"]["nodes"][0]["home_team"]["name"] == "Tigres"

        self.stdout.write(self.style.SUCCESS("\n=== URLs PARA BROWSER ==="))
        self.stdout.write(f"  Estructura: http://localhost:3001/deportes/tournaments/{slug}/structure")
        self.stdout.write(f"  Posiciones: http://localhost:3001/deportes/tournaments/{slug}/standings?phase=cuadrangular&group=cuadrangular")
        self.stdout.write(f"  Torneo:     http://localhost:3001/deportes/tournaments/{slug}")
        self.stdout.write(f"  Final:      http://localhost:3001/deportes/matches/{final.id}")
        self.stdout.write(self.style.SUCCESS(f"\nE2E OK — slug: {slug}"))
