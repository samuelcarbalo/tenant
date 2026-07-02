from collections import defaultdict

from django.db.models import Q

from sports.models import Match, Team

from .config import get_scoring_config
from .match_result import MatchResultService


class StandingsService:
    """Calcula tablas de posiciones por alcance (torneo, fase, grupo)."""

    @staticmethod
    def _empty_row(team):
        return {
            "team": team,
            "played": 0,
            "won": 0,
            "drawn": 0,
            "lost": 0,
            "goals_for": 0,
            "goals_against": 0,
            "goal_difference": 0,
            "points": 0,
            "runs": 0,
            "runs_against": 0,
            "average": 0.0,
        }

    @staticmethod
    def _team_ids_from_phase_matches(tournament, phase):
        ids = set()
        for home_id, away_id in Match.objects.filter(
            tournament=tournament, phase=phase
        ).values_list("home_team_id", "away_team_id"):
            if home_id:
                ids.add(home_id)
            if away_id:
                ids.add(away_id)
        return ids

    @staticmethod
    def _team_ids_from_bracket(phase, tournament):
        """Equipos esperados en eliminatoria según bracket (si aún no hay partidos)."""
        from sports.services.advancement import resolve_team_source

        ids = set()
        if not hasattr(phase, "bracket"):
            return ids
        prior = (
            tournament.phases.filter(order__lt=phase.order, status="finished")
            .order_by("-order")
            .first()
        )
        for node in phase.bracket.nodes.all():
            for source in (node.home_source, node.away_source):
                team = resolve_team_source(source, tournament, from_phase=prior)
                if team:
                    ids.add(team.id)
        return ids

    @staticmethod
    def _get_teams_in_scope(tournament, phase=None, group=None):
        if group is not None:
            team_ids = group.memberships.values_list("team_id", flat=True)
            return Team.objects.filter(id__in=team_ids).order_by("name")
        if phase is not None:
            if phase.groups.exists():
                team_ids = phase.groups.values_list("memberships__team_id", flat=True)
                return Team.objects.filter(id__in=team_ids).distinct().order_by("name")

            # Eliminatoria u otra fase sin grupos: solo equipos que juegan esa instancia
            team_ids = StandingsService._team_ids_from_phase_matches(tournament, phase)
            if not team_ids and phase.phase_type == "knockout":
                team_ids = StandingsService._team_ids_from_bracket(phase, tournament)
            if team_ids:
                return Team.objects.filter(id__in=team_ids).order_by("name")
            return Team.objects.none()
        return Team.objects.filter(tournament=tournament).order_by("name")

    @staticmethod
    def _get_matches_in_scope(tournament, phase=None, group=None):
        qs = Match.objects.filter(
            tournament=tournament,
            status="finished",
        ).select_related("home_team", "away_team")

        if phase is not None:
            qs = qs.filter(phase=phase)
        if group is not None:
            qs = qs.filter(group=group)

        return qs

    @staticmethod
    def _head_to_head_points(team_a, team_b, matches, config):
        home_field, away_field = config["primary_fields"]
        points_a = 0
        for match in matches:
            if {match.home_team_id, match.away_team_id} != {team_a.id, team_b.id}:
                continue
            hs = getattr(match, home_field) or 0
            aws = getattr(match, away_field) or 0
            if match.home_team_id == team_a.id:
                a_score, b_score = hs, aws
            else:
                a_score, b_score = aws, hs
            try:
                outcome, home_pts, away_pts = MatchResultService.determine_outcome(
                    a_score if match.home_team_id == team_a.id else b_score,
                    b_score if match.home_team_id == team_a.id else a_score,
                    config,
                )
            except ValueError:
                continue
            if outcome == "draw":
                points_a += config["points"].get("draw", 0)
            elif (outcome == "home_win" and match.home_team_id == team_a.id) or (
                outcome == "away_win" and match.away_team_id == team_a.id
            ):
                points_a += config["points"]["win"]
            else:
                points_a += config["points"].get("loss", 0)
        return points_a

    @staticmethod
    def _sort_key(row, config, h2h_matches):
        tiebreakers = config.get("tiebreakers", ["points", "name"])
        team = row["team"]
        keys = []
        for tb in tiebreakers:
            if tb == "points":
                keys.append(-row["points"])
            elif tb == "wins":
                keys.append(-row["won"])
            elif tb == "goal_difference":
                keys.append(-row["goal_difference"])
            elif tb == "goals_for":
                keys.append(-row["goals_for"])
            elif tb == "runs_for":
                keys.append(-row["runs"])
            elif tb == "average":
                keys.append(-row["average"])
            elif tb == "head_to_head":
                keys.append(0)
            elif tb == "name":
                keys.append(team.name.lower())
        return tuple(keys)

    @staticmethod
    def compute(tournament, phase=None, group=None):
        config = get_scoring_config(tournament)
        home_field, away_field = config["primary_fields"]
        stat_for = config["stat_for"]
        stat_against = config["stat_against"]

        teams = list(StandingsService._get_teams_in_scope(tournament, phase, group))
        rows = {team.id: StandingsService._empty_row(team) for team in teams}
        matches = list(
            StandingsService._get_matches_in_scope(tournament, phase, group)
        )

        for match in matches:
            hs = getattr(match, home_field)
            aws = getattr(match, away_field)
            if hs is None or aws is None:
                continue

            for team_obj, scored, conceded, is_home in (
                (match.home_team, hs, aws, True),
                (match.away_team, aws, hs, False),
            ):
                if team_obj.id not in rows:
                    continue
                row = rows[team_obj.id]
                row["played"] += 1

                if stat_for == "runs":
                    row["runs"] += scored
                    row["runs_against"] += conceded
                row["goals_for"] += scored
                row["goals_against"] += conceded
                row["goal_difference"] = row["goals_for"] - row["goals_against"]
                if row["runs_against"] > 0:
                    row["average"] = row["runs"] / row["runs_against"]
                elif row["runs"] > 0:
                    row["average"] = float(row["runs"])

                try:
                    outcome, home_pts, away_pts = MatchResultService.determine_outcome(
                        hs, aws, config
                    )
                except ValueError:
                    continue

                if outcome == "draw":
                    row["drawn"] += 1
                    row["points"] += config["points"].get("draw", 0)
                elif (outcome == "home_win" and is_home) or (
                    outcome == "away_win" and not is_home
                ):
                    row["won"] += 1
                    row["points"] += config["points"]["win"]
                else:
                    row["lost"] += 1
                    row["points"] += config["points"].get("loss", 0)

        standings_list = list(rows.values())
        standings_list.sort(
            key=lambda r: StandingsService._sort_key(r, config, matches)
        )

        result = []
        for idx, row in enumerate(standings_list, start=1):
            entry = {
                "position": idx,
                "team": row["team"],
                "played": row["played"],
                "won": row["won"],
                "drawn": row["drawn"],
                "lost": row["lost"],
                "goals_for": row["goals_for"],
                "goals_against": row["goals_against"],
                "goal_difference": row["goal_difference"],
                "points": row["points"],
            }
            if tournament.sport_type == "softball":
                entry.update(
                    {
                        "runs": row["runs"],
                        "runs_against": row["runs_against"],
                        "average": round(row["average"], 3),
                    }
                )
            result.append(entry)
        return result
