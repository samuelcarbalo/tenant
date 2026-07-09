"""E2E: Cuadrangulares + Semis + Final (8 equipos, softbol)."""

from itertools import combinations

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


def _finish_quadrangular(tournament, phase, group, teams):
    """Finaliza round-robin: el primer equipo en la lista queda 1°, el segundo 2°, etc."""
    seed = {t.id: i for i, t in enumerate(teams)}

    for home, away in combinations(teams, 2):
        if seed[home.id] < seed[away.id]:
            hr, ar = 5, 2
        else:
            hr, ar = 2, 5

        if Match.objects.filter(
            tournament=tournament,
            home_team=home,
            away_team=away,
            phase=phase,
            group=group,
        ).exists():
            m = Match.objects.get(
                tournament=tournament,
                home_team=home,
                away_team=away,
                phase=phase,
                group=group,
            )
        else:
            m = Match.objects.get(
                tournament=tournament,
                home_team=away,
                away_team=home,
                phase=phase,
                group=group,
            )
            hr, ar = ar, hr

        MatchResultService.finalize_match(m, {"home_runs": hr, "away_runs": ar})


class Command(BaseCommand):
    help = "E2E cuadrangulares + semis + final (8 equipos)"

    def handle(self, *args, **options):
        org, _ = Organization.objects.get_or_create(
            slug="e2e-municipio", defaults={"name": "E2E Municipio"}
        )
        user, _ = User.objects.get_or_create(
            email="e2e-softbol@test.com",
            defaults={
                "username": "e2e_softbol",
                "organization": org,
                "role": "manager",
                "credits": 500,
            },
        )

        slug = f"e2e-semis-{timezone.now().strftime('%H%M%S')}"
        tournament = Tournament.objects.create(
            name=f"E2E Cuadrangulares+Semis {timezone.now().strftime('%H:%M')}",
            slug=slug,
            sport_type="softball",
            organization=org,
            posted_by=user,
            start_date=timezone.now().date(),
            end_date=timezone.now().date(),
            registration_deadline=timezone.now().date(),
        )
        apply_format_template(tournament, "multi_quadrangular_knockout", group_count=2)
        tournament.status = "active"
        tournament.save(update_fields=["status"])

        phase = tournament.phases.get(slug="cuadrangulares")
        group_a = phase.groups.get(slug="cuadrangular-a")
        group_b = phase.groups.get(slug="cuadrangular-b")

        teams_a = []
        teams_b = []
        for i, name in enumerate(["Tigres", "Leones", "Aguilas", "Toros"], start=1):
            teams_a.append(
                Team.objects.create(
                    name=f"{name} A",
                    slug=f"{slug}-a{i}",
                    abbreviation=f"A{i}",
                    tournament=tournament,
                    organization=org,
                    posted_by=user,
                )
            )
            teams_b.append(
                Team.objects.create(
                    name=f"{name} B",
                    slug=f"{slug}-b{i}",
                    abbreviation=f"B{i}",
                    tournament=tournament,
                    organization=org,
                    posted_by=user,
                )
            )

        assign_teams_to_group(group_a, [t.id for t in teams_a])
        assign_teams_to_group(group_b, [t.id for t in teams_b])

        generate_round_robin_fixtures(
            tournament, phase, group_a, user, timezone.now(), "Campo A"
        )
        generate_round_robin_fixtures(
            tournament, phase, group_b, user, timezone.now(), "Campo B"
        )

        _finish_quadrangular(tournament, phase, group_a, teams_a)
        _finish_quadrangular(tournament, phase, group_b, teams_b)

        self.stdout.write(self.style.SUCCESS("=== CUADRANGULAR A ==="))
        for row in StandingsService.compute(tournament, phase=phase, group=group_a):
            self.stdout.write(
                f"  {row['position']}. {row['team'].name} ({row['won']}G)"
            )
        self.stdout.write(self.style.SUCCESS("=== CUADRANGULAR B ==="))
        for row in StandingsService.compute(tournament, phase=phase, group=group_b):
            self.stdout.write(
                f"  {row['position']}. {row['team'].name} ({row['won']}G)"
            )

        semi_result = advance_phase(tournament, "cuadrangulares", user, timezone.now())
        semis = semi_result["matches_created"]
        self.stdout.write(self.style.SUCCESS(f"\n=== SEMIFINALES ({len(semis)}) ==="))
        for m in semis:
            self.stdout.write(f"  {m.home_team.name} vs {m.away_team.name}")

        # 1A vs 2B -> Tigres A vs Leones B; 1B vs 2A -> Tigres B vs Leones A
        expected = {
            (teams_a[0].name, teams_b[1].name),
            (teams_b[0].name, teams_a[1].name),
        }
        actual = {(m.home_team.name, m.away_team.name) for m in semis}
        assert actual == expected, f"Semis incorrectas: {actual} vs {expected}"

        for m in semis:
            MatchResultService.finalize_match(m, {"home_runs": 4, "away_runs": 2})

        final = Match.objects.filter(tournament=tournament, phase__slug="final").first()
        assert final is not None, "Final no generada tras semis"
        self.stdout.write(self.style.SUCCESS("\n=== FINAL ==="))
        self.stdout.write(f"  {final.home_team.name} vs {final.away_team.name}")

        MatchResultService.finalize_match(final, {"home_runs": 5, "away_runs": 3})
        self.stdout.write(self.style.SUCCESS(f"\n=== CAMPEON: {final.winner.name} ==="))

        self.stdout.write(self.style.SUCCESS("\n=== URLs ==="))
        self.stdout.write(
            f"  Estructura: http://localhost:3001/deportes/tournaments/{slug}/structure"
        )
        self.stdout.write(
            f"  Tabla A:    http://localhost:3001/deportes/tournaments/{slug}/standings?phase=cuadrangulares&group=cuadrangular-a"
        )
        self.stdout.write(
            f"  Tabla B:    http://localhost:3001/deportes/tournaments/{slug}/standings?phase=cuadrangulares&group=cuadrangular-b"
        )
        self.stdout.write(
            f"  Final:      http://localhost:3001/deportes/matches/{final.id}"
        )
        self.stdout.write(self.style.SUCCESS(f"\nE2E SEMIS OK — slug: {slug}"))
