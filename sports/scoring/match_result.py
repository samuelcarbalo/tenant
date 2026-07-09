from django.db import transaction

from .config import get_scoring_config


class MatchResultService:
    """Aplica y revierte estadísticas de partido según el deporte."""

    @staticmethod
    def get_primary_scores(match, config=None):
        config = config or get_scoring_config(match.tournament)
        home_field, away_field = config["primary_fields"]
        home = getattr(match, home_field)
        away = getattr(match, away_field)
        if home is None or away is None:
            return None, None
        return int(home), int(away)

    @staticmethod
    def normalize_scores_from_request(match, data, config=None):
        """Normaliza payload de marcador antes de guardar."""
        config = config or get_scoring_config(match.tournament)
        home_field, away_field = config["primary_fields"]
        result = dict(data)

        if home_field == "home_runs":
            if "home_runs" in result and result["home_runs"] is not None:
                result["home_runs"] = int(result["home_runs"])
                result["home_score"] = result["home_runs"]
            elif "home_score" in result and result["home_score"] is not None:
                result["home_runs"] = int(result["home_score"])
                result["home_score"] = result["home_runs"]
            if "away_runs" in result and result["away_runs"] is not None:
                result["away_runs"] = int(result["away_runs"])
                result["away_score"] = result["away_runs"]
            elif "away_score" in result and result["away_score"] is not None:
                result["away_runs"] = int(result["away_score"])
                result["away_score"] = result["away_runs"]
        else:
            if "home_score" in result and result["home_score"] is not None:
                result["home_score"] = int(result["home_score"])
            if "away_score" in result and result["away_score"] is not None:
                result["away_score"] = int(result["away_score"])

        return result

    @staticmethod
    def apply_scores_to_match(match, score_data, config=None):
        config = config or get_scoring_config(match.tournament)
        normalized = MatchResultService.normalize_scores_from_request(
            match, score_data, config
        )
        home_field, away_field = config["primary_fields"]

        for field in [
            "home_score",
            "away_score",
            "home_runs",
            "away_runs",
        ]:
            if field in normalized and normalized[field] is not None:
                setattr(match, field, normalized[field])

        if getattr(match, home_field) is None or getattr(match, away_field) is None:
            raise ValueError("Marcador incompleto para finalizar el partido.")

    @staticmethod
    def determine_outcome(home_score, away_score, config):
        points = config["points"]
        if home_score > away_score:
            return "home_win", points["win"], points["loss"]
        if away_score > home_score:
            return "away_win", points["loss"], points["win"]
        if config.get("allows_draw"):
            return "draw", points.get("draw", 0), points.get("draw", 0)
        raise ValueError("Este deporte no permite empates.")

    @staticmethod
    @transaction.atomic
    def finalize_match(match, score_data):
        """Finaliza partido de forma idempotente (recalcula stats desde cero)."""
        from django.utils import timezone

        config = get_scoring_config(match.tournament)
        MatchResultService.apply_scores_to_match(match, score_data, config)
        match.stats_counted = True
        if match.status != "finished":
            match.status = "finished"
            if not match.finished_at:
                match.finished_at = timezone.now()
        match.save(
            update_fields=[
                "home_score",
                "away_score",
                "home_runs",
                "away_runs",
                "stats_counted",
                "status",
                "finished_at",
            ]
        )
        MatchResultService.recalculate_team_aggregates(match.home_team)
        MatchResultService.recalculate_team_aggregates(match.away_team)
        from sports.services.advancement import propagate_bracket_after_match

        propagate_bracket_after_match(match)
        return match

    @staticmethod
    def revert_match_stats(match, config=None):
        config = config or get_scoring_config(match.tournament)
        home_score, away_score = MatchResultService.get_primary_scores(match, config)
        if home_score is None or away_score is None:
            return

        home = match.home_team
        away = match.away_team

        home.played = max(0, home.played - 1)
        away.played = max(0, away.played - 1)

        try:
            outcome, home_points, away_points = MatchResultService.determine_outcome(
                home_score, away_score, config
            )
        except ValueError:
            return

        if outcome == "home_win":
            home.won = max(0, home.won - 1)
            away.lost = max(0, away.lost - 1)
        elif outcome == "away_win":
            away.won = max(0, away.won - 1)
            home.lost = max(0, home.lost - 1)
        else:
            home.drawn = max(0, home.drawn - 1)
            away.drawn = max(0, away.drawn - 1)

        home.points = max(0, home.points - home_points)
        away.points = max(0, away.points - away_points)

        stat_for = config["stat_for"]
        stat_against = config["stat_against"]
        setattr(home, stat_for, max(0, getattr(home, stat_for) - home_score))
        setattr(home, stat_against, max(0, getattr(home, stat_against) - away_score))
        setattr(away, stat_for, max(0, getattr(away, stat_for) - away_score))
        setattr(away, stat_against, max(0, getattr(away, stat_against) - home_score))

        if stat_for == "runs":
            if home.runs_against > 0:
                home.average = home.runs / home.runs_against
            else:
                home.average = float(home.runs) if home.runs else 0.0
            if away.runs_against > 0:
                away.average = away.runs / away.runs_against
            else:
                away.average = float(away.runs) if away.runs else 0.0

        home.save()
        away.save()

    @staticmethod
    def apply_match_stats(match, config=None):
        config = config or get_scoring_config(match.tournament)
        home_score, away_score = MatchResultService.get_primary_scores(match, config)
        if home_score is None or away_score is None:
            return

        home = match.home_team
        away = match.away_team

        home.played += 1
        away.played += 1

        outcome, home_points, away_points = MatchResultService.determine_outcome(
            home_score, away_score, config
        )

        if outcome == "home_win":
            home.won += 1
            away.lost += 1
        elif outcome == "away_win":
            away.won += 1
            home.lost += 1
        else:
            home.drawn += 1
            away.drawn += 1

        home.points += home_points
        away.points += away_points

        stat_for = config["stat_for"]
        stat_against = config["stat_against"]
        setattr(home, stat_for, getattr(home, stat_for) + home_score)
        setattr(home, stat_against, getattr(home, stat_against) + away_score)
        setattr(away, stat_for, getattr(away, stat_for) + away_score)
        setattr(away, stat_against, getattr(away, stat_against) + home_score)

        if stat_for == "runs":
            home.average = home.runs / home.runs_against if home.runs_against > 0 else float(home.runs)
            away.average = away.runs / away.runs_against if away.runs_against > 0 else float(away.runs)

        home.save()
        away.save()

    @staticmethod
    def recalculate_team_aggregates(team):
        """Recalcula stats globales del equipo desde partidos finalizados."""
        from django.db.models import Q
        from sports.models import Match

        config = get_scoring_config(team.tournament)
        home_field, away_field = config["primary_fields"]
        stat_for = config["stat_for"]

        team.played = 0
        team.won = 0
        team.drawn = 0
        team.lost = 0
        team.points = 0
        team.goals_for = 0
        team.goals_against = 0
        team.runs = 0
        team.runs_against = 0

        matches = Match.objects.filter(
            tournament=team.tournament,
            status="finished",
        ).filter(Q(home_team=team) | Q(away_team=team))

        for match in matches:
            if getattr(match, home_field) is None or getattr(match, away_field) is None:
                continue

            hs = getattr(match, home_field) or 0
            aws = getattr(match, away_field) or 0

            if match.home_team_id == team.id:
                scored, conceded, is_home = hs, aws, True
            else:
                scored, conceded, is_home = aws, hs, False

            team.played += 1
            team.goals_for += scored
            team.goals_against += conceded
            if stat_for == "runs":
                team.runs += scored
                team.runs_against += conceded

            try:
                outcome, _, _ = MatchResultService.determine_outcome(hs, aws, config)
            except ValueError:
                continue

            if outcome == "draw":
                team.drawn += 1
                team.points += config["points"].get("draw", 0)
            elif (outcome == "home_win" and is_home) or (
                outcome == "away_win" and not is_home
            ):
                team.won += 1
                team.points += config["points"]["win"]
            else:
                team.lost += 1
                team.points += config["points"].get("loss", 0)

        if stat_for == "runs":
            team.average = (
                team.runs / team.runs_against if team.runs_against > 0 else float(team.runs)
            )

        team.save()
