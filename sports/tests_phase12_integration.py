"""Pruebas de integración Fase 1 y 2: cuadrangular softbol completo."""

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import User
from organizations.models import Organization
from sports.models import Tournament, Team, Match, TournamentPhase, CompetitionGroup
from sports.services.structure import (
    apply_format_template,
    assign_teams_to_group,
    generate_round_robin_fixtures,
)
from sports.scoring import MatchResultService, StandingsService
from sports.formats.templates import list_templates


class Phase12IntegrationTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Municipio Test", slug="mun-test")
        self.user = User.objects.create_user(
            email="org@test.com",
            username="orgmanager",
            password="SecurePass123!",
            organization=self.org,
            role="manager",
            credits=100,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.tournament = Tournament.objects.create(
            name="Copa Softbol Municipal",
            slug="copa-softbol-municipal",
            sport_type="softball",
            organization=self.org,
            posted_by=self.user,
            start_date="2026-06-15",
            end_date="2026-06-15",
            registration_deadline="2026-06-10",
        )
        apply_format_template(self.tournament, "single_day_quadrangular")

        self.teams = []
        for i, name in enumerate(["Tigres", "Leones", "Águilas", "Toros"], start=1):
            self.teams.append(
                Team.objects.create(
                    name=name,
                    slug=f"equipo-{i}",
                    abbreviation=f"E{i}",
                    tournament=self.tournament,
                    organization=self.org,
                    posted_by=self.user,
                )
            )

        self.phase = self.tournament.phases.get(slug="cuadrangular")
        self.group = self.phase.groups.get(slug="cuadrangular")
        assign_teams_to_group(self.group, [t.id for t in self.teams])

    def test_format_templates_include_softball_quadrangular(self):
        templates = list_templates("softball")
        ids = [t["id"] for t in templates]
        self.assertIn("single_day_quadrangular", ids)

    def test_structure_api_returns_phases_and_groups(self):
        res = self.client.get(
            f"/api/v1/sports/tournaments/{self.tournament.slug}/structure/"
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["structure_mode"], "structured")
        self.assertEqual(len(data["phases"]), 1)
        self.assertEqual(len(data["phases"][0]["groups"]), 1)
        self.assertEqual(data["phases"][0]["groups"][0]["teams_count"], 4)

    def test_full_quadrangular_flow_softball_scoring(self):
        generate_round_robin_fixtures(
            tournament=self.tournament,
            phase=self.phase,
            group=self.group,
            posted_by=self.user,
            match_date=timezone.now(),
            venue="Campo Municipal",
        )
        matches = Match.objects.filter(tournament=self.tournament, phase=self.phase)
        self.assertEqual(matches.count(), 6)

        results = [(5, 2), (3, 4), (6, 1), (2, 5), (4, 3), (1, 6)]
        for match, (hr, ar) in zip(matches.order_by("id"), results):
            MatchResultService.finalize_match(
                match, {"home_runs": hr, "away_runs": ar}
            )

        standings = StandingsService.compute(
            self.tournament, phase=self.phase, group=self.group
        )
        self.assertEqual(len(standings), 4)
        self.assertEqual(standings[0]["played"], 3)
        self.assertGreater(standings[0]["runs"], 0)

        res = self.client.get(
            f"/api/v1/sports/tournaments/{self.tournament.slug}/standings/",
            {"phase": "cuadrangular", "group": "cuadrangular"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()), 4)
        self.assertIn("runs", res.json()[0])
        self.assertIn("average", res.json()[0])

        for team in self.teams:
            team.refresh_from_db()
            self.assertEqual(team.played, 3)
        self.assertEqual(
            Match.objects.filter(tournament=self.tournament, status="finished").count(), 6
        )

    def test_standings_scoped_excludes_other_groups(self):
        apply_format_template(
            Tournament.objects.create(
                name="Multi",
                slug="multi-cua",
                sport_type="softball",
                organization=self.org,
                posted_by=self.user,
                start_date="2026-06-15",
                end_date="2026-06-16",
            ),
            "multi_quadrangular",
            group_count=2,
        )
        t2 = Tournament.objects.get(slug="multi-cua")
        phase = t2.phases.first()
        g_a, g_b = list(phase.groups.order_by("order"))
        teams_a = self.teams[:2]
        teams_b = [
            Team.objects.create(
                name=f"B{i}",
                slug=f"b-{i}",
                abbreviation=f"B{i}",
                tournament=t2,
                organization=self.org,
                posted_by=self.user,
            )
            for i in range(1, 3)
        ]
        assign_teams_to_group(g_a, [t.id for t in teams_a])
        assign_teams_to_group(g_b, [t.id for t in teams_b])

        m = Match.objects.create(
            tournament=t2,
            posted_by=self.user,
            home_team=teams_a[0],
            away_team=teams_a[1],
            match_date=timezone.now(),
            phase=phase,
            group=g_a,
            match_type="group",
            status="finished",
        )
        MatchResultService.finalize_match(m, {"home_runs": 3, "away_runs": 1})

        st_a = StandingsService.compute(t2, phase=phase, group=g_a)
        st_b = StandingsService.compute(t2, phase=phase, group=g_b)
        self.assertEqual(len(st_a), 2)
        self.assertEqual(st_a[0]["played"], 1)
        self.assertEqual(len(st_b), 2)
        self.assertEqual(st_b[0]["played"], 0)

    def test_liga_simple_is_a_single_table_without_groups(self):
        league = Tournament.objects.create(
            name="Liga Simple",
            slug="liga-simple",
            sport_type="football",
            organization=self.org,
            posted_by=self.user,
            start_date="2026-07-01",
            end_date="2026-08-01",
        )
        apply_format_template(league, "round_robin_single", group_count=4)
        phase = league.phases.get()
        self.assertEqual(phase.phase_type, "round_robin")
        self.assertEqual(phase.groups.count(), 0)

        legacy = Tournament.objects.create(
            name="Liga Legacy",
            slug="liga-legacy",
            sport_type="football",
            organization=self.org,
            posted_by=self.user,
            start_date="2026-07-01",
            end_date="2026-08-01",
        )
        apply_format_template(legacy, "legacy_league", group_count=3)
        self.assertEqual(legacy.phases.count(), 0)

    def test_multi_group_fixtures_stay_inside_each_group(self):
        tournament = Tournament.objects.create(
            name="Grupos",
            slug="grupos-fixture",
            sport_type="football",
            organization=self.org,
            posted_by=self.user,
            start_date="2026-07-01",
            end_date="2026-08-01",
            max_teams=16,
        )
        apply_format_template(tournament, "multi_quadrangular", group_count=2)
        tournament.refresh_from_db()
        self.assertEqual(tournament.max_teams, 8)
        phase = tournament.phases.get()
        groups = list(phase.groups.order_by("order"))
        self.assertEqual([group.name for group in groups], ["Grupo A", "Grupo B"])

        teams = [
            Team.objects.create(
                name=f"Equipo {i}",
                slug=f"eq-{i}",
                abbreviation=f"E{i}",
                tournament=tournament,
                organization=self.org,
                posted_by=self.user,
            )
            for i in range(1, 9)
        ]
        assign_teams_to_group(groups[0], [team.id for team in teams[:4]])
        assign_teams_to_group(groups[1], [team.id for team in teams[4:]])

        created = []
        for group in groups:
            created.extend(
                generate_round_robin_fixtures(
                    tournament=tournament,
                    phase=phase,
                    group=group,
                    posted_by=self.user,
                    match_date=timezone.now(),
                )
            )

        self.assertEqual(len(created), 12)
        ids_a = {team.id for team in teams[:4]}
        ids_b = {team.id for team in teams[4:]}
        for match in created:
            pair = {match.home_team_id, match.away_team_id}
            self.assertTrue(pair <= ids_a or pair <= ids_b)
            self.assertEqual(match.group_id, groups[0].id if pair <= ids_a else groups[1].id)

    def test_group_playoffs_follow_requested_group_count(self):
        tournament = Tournament.objects.create(
            name="Playoffs",
            slug="playoffs-cinco-grupos",
            sport_type="football",
            organization=self.org,
            posted_by=self.user,
            start_date="2026-07-01",
            end_date="2026-08-01",
        )
        apply_format_template(tournament, "multi_quadrangular_knockout", group_count=5)
        tournament.refresh_from_db()
        self.assertEqual(tournament.max_teams, 20)
        phase = tournament.phases.order_by("order").first()
        self.assertEqual(phase.name, "Fase de grupos")
        self.assertEqual(phase.groups.count(), 5)
        self.assertEqual(
            list(phase.groups.order_by("order").values_list("name", flat=True)),
            ["Grupo A", "Grupo B", "Grupo C", "Grupo D", "Grupo E"],
        )
        first_ko = tournament.phases.order_by("order")[1]
        nodes = list(first_ko.bracket.nodes.order_by("position"))
        self.assertEqual(len(nodes), 5)
        self.assertEqual(nodes[0].home_source["group_slug"], "cuadrangular-a")
        self.assertEqual(nodes[0].home_source["rank"], 1)
        self.assertEqual(nodes[0].away_source["group_slug"], "cuadrangular-b")
        self.assertEqual(nodes[0].away_source["rank"], 2)
        self.assertTrue(tournament.phases.filter(slug="final").exists())

        two = Tournament.objects.create(
            name="Playoffs 2",
            slug="playoffs-dos-grupos",
            sport_type="football",
            organization=self.org,
            posted_by=self.user,
            start_date="2026-07-01",
            end_date="2026-08-01",
        )
        apply_format_template(two, "multi_quadrangular_knockout", group_count=2)
        semis = two.phases.get(slug="semifinales")
        semi_nodes = list(semis.bracket.nodes.order_by("position"))
        self.assertEqual(semi_nodes[0].away_source["group_slug"], "cuadrangular-b")
        self.assertEqual(semi_nodes[1].home_source["group_slug"], "cuadrangular-b")
        self.assertTrue(two.phases.filter(slug="final").exists())

    def _tournament_with_second_phase(self, slug, method="RANDOM", groups=2, second_out=2):
        tournament = Tournament.objects.create(
            name=slug,
            slug=slug,
            sport_type="football",
            organization=self.org,
            posted_by=self.user,
            start_date="2026-09-01",
            end_date="2026-10-01",
            has_second_group_phase=True,
            first_phase_qualified_per_group=2,
            second_phase_groups_count=groups,
            second_phase_qualified_per_group=second_out,
            second_phase_assignment_method=method,
        )
        apply_format_template(tournament, "multi_quadrangular_knockout", group_count=2)
        teams = []
        for i in range(1, 9):
            teams.append(
                Team.objects.create(
                    name=f"Equipo {i:02d}",
                    slug=f"{slug}-e{i}",
                    abbreviation=f"E{i}",
                    tournament=tournament,
                    organization=self.org,
                    posted_by=self.user,
                )
            )
        phase = tournament.phases.get(slug="cuadrangulares")
        groups_qs = list(phase.groups.order_by("order"))
        assign_teams_to_group(groups_qs[0], [t.id for t in teams[:4]])
        assign_teams_to_group(groups_qs[1], [t.id for t in teams[4:]])
        self.user.admin_level = 2
        self.user.is_staff = True
        self.user.role = "admin"
        self.user.save(update_fields=["admin_level", "is_staff", "role"])
        return tournament

    def test_second_group_phase_random_splits_qualifiers(self):
        tournament = self._tournament_with_second_phase("segunda-aleatoria", "RANDOM")
        self.assertTrue(tournament.phases.filter(slug="segunda-fase").exists())
        first_ko = tournament.phases.order_by("order")[2]
        node = first_ko.bracket.nodes.order_by("position").first()
        self.assertEqual(node.home_source["group_slug"], "segunda-a")
        self.assertEqual(node.away_source["group_slug"], "segunda-b")

        res = self.client.post(
            f"/api/v1/sports/tournaments/{tournament.slug}/generate-second-phase/",
            {},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        phase = tournament.phases.get(slug="segunda-fase")
        sizes = [
            group.memberships.count()
            for group in phase.groups.order_by("order")
        ]
        self.assertEqual(sizes, [2, 2])

    def test_second_group_phase_manual_assignment(self):
        tournament = self._tournament_with_second_phase("segunda-manual", "MANUAL")
        preview = self.client.get(
            f"/api/v1/sports/tournaments/{tournament.slug}/generate-second-phase/"
        )
        self.assertEqual(preview.status_code, 200, preview.content)
        quals = preview.json()["qualifiers"]
        self.assertEqual(len(quals), 4)
        payload = {
            "groups": [
                {"slug": "segunda-a", "team_ids": [quals[0]["team_id"], quals[1]["team_id"]]},
                {"slug": "segunda-b", "team_ids": [quals[2]["team_id"], quals[3]["team_id"]]},
            ]
        }
        res = self.client.post(
            f"/api/v1/sports/tournaments/{tournament.slug}/generate-second-phase/",
            payload,
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        phase = tournament.phases.get(slug="segunda-fase")
        group_a = phase.groups.get(slug="segunda-a")
        self.assertCountEqual(
            [str(team_id) for team_id in group_a.memberships.values_list("team_id", flat=True)],
            [quals[0]["team_id"], quals[1]["team_id"]],
        )

    def test_public_team_payload_omits_coach_phone(self):
        team = self.teams[0]
        team.coach_phone = "3001234567"
        team.save(update_fields=["coach_phone"])

        anon = APIClient()
        detail = anon.get(f"/api/v1/sports/teams/{team.slug}/")
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertNotIn("coach_phone", detail.json())

        listing = anon.get(
            "/api/v1/sports/teams/",
            {"tournament": self.tournament.slug},
        )
        self.assertEqual(listing.status_code, 200, listing.content)
        payload = listing.json()
        rows = payload["results"] if isinstance(payload, dict) else payload
        self.assertTrue(rows)
        self.assertTrue(all("coach_phone" not in row for row in rows))

        outsider = User.objects.create_user(
            email="visitante@test.com",
            username="visitante",
            password="SecurePass123!",
            organization=self.org,
            role="user",
        )
        outsider_client = APIClient()
        outsider_client.force_authenticate(user=outsider)
        hidden = outsider_client.get(f"/api/v1/sports/teams/{team.slug}/")
        self.assertEqual(hidden.status_code, 200, hidden.content)
        self.assertNotIn("coach_phone", hidden.json())

        owner = self.client.get(f"/api/v1/sports/teams/{team.slug}/")
        self.assertEqual(owner.status_code, 200, owner.content)
        self.assertEqual(owner.json()["coach_phone"], "3001234567")
