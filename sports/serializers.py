from rest_framework import serializers
from .models import Tournament, Team, Player, Match, MatchEvent


class TournamentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tournament
        fields = [
            "name",
            "slug",
            "description",
            "sport_type",
            "start_date",
            "end_date",
            "registration_deadline",
            "max_teams",
            "min_players_per_team",
            "max_players_per_team",
            "logo",
            "banner",
        ]


class TournamentListSerializer(serializers.ModelSerializer):
    """Serializer para listado de torneos"""

    organization_name = serializers.CharField(
        source="organization.name", read_only=True
    )
    teams_count = serializers.IntegerField(source="teams.count", read_only=True)
    matches_count = serializers.IntegerField(source="matches.count", read_only=True)
    sport_type_display = serializers.CharField(
        source="get_sport_type_display", read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Tournament
        fields = [
            "id",
            "name",
            "slug",
            "sport_type",
            "sport_type_display",
            "organization",
            "organization_name",
            "start_date",
            "end_date",
            "status",
            "status_display",
            "logo",
            "teams_count",
            "matches_count",
            "posted_by",
        ]


class TournamentDetailSerializer(serializers.ModelSerializer):
    """Serializer detallado de torneo"""

    organization_name = serializers.CharField(
        source="organization.name", read_only=True
    )
    sport_type_display = serializers.CharField(
        source="get_sport_type_display", read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Tournament
        fields = "__all__"


class TeamListSerializer(serializers.ModelSerializer):
    """Serializer para listado de equipos"""

    tournament_name = serializers.CharField(source="tournament.name", read_only=True)
    players_count = serializers.IntegerField(source="players.count", read_only=True)
    position = serializers.SerializerMethodField()

    class Meta:
        model = Team
        fields = [
            "id",
            "name",
            "slug",
            "abbreviation",
            "logo",
            "tournament",
            "tournament_name",
            "played",
            "won",
            "drawn",
            "lost",
            "goals_for",
            "goals_against",
            "goal_difference",
            "played",
            "points",
            "position",
            "players_count",
            # Softbol stats
            "runs",
            "runs_against",
            "average",
            "posted_by",
            "coach_name",
            "coach_email",
            "coach_phone",
        ]

    def get_position(self, obj):
        """Calcular posición en la tabla"""
        teams = Team.objects.filter(tournament=obj.tournament).order_by(
            "-points", "-goals_for", "name"
        )
        for idx, team in enumerate(teams, 1):
            if team.id == obj.id:
                return idx
        return None


class TeamDetailSerializer(serializers.ModelSerializer):
    """Serializer detallado de equipo"""

    tournament_name = serializers.CharField(source="tournament.name", read_only=True)
    players = serializers.SerializerMethodField()

    class Meta:
        model = Team
        fields = "__all__"

    def get_players(self, obj):
        """Lista de jugadores activos"""
        players = obj.players.filter(is_active=True)
        return PlayerListSerializer(players, many=True).data


class TeamCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer para crear/actualizar equipos - posted_by es read_only"""

    posted_by = serializers.PrimaryKeyRelatedField(read_only=True)
    organization = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Team
        fields = [
            "id",
            "name",
            "slug",
            "abbreviation",
            "description",
            "logo",
            "primary_color",
            "secondary_color",
            "tournament",
            "coach_name",
            "coach_email",
            "coach_phone",
            "posted_by",
            "organization",
        ]
        read_only_fields = ["posted_by", "organization"]


class PlayerListSerializer(serializers.ModelSerializer):
    """Serializer para listado de jugadores"""

    team_name = serializers.CharField(source="team.name", read_only=True)
    position_display = serializers.CharField(
        source="get_position_display", read_only=True
    )
    tournament_slug = serializers.CharField(source="tournament.slug", read_only=True)

    class Meta:
        model = Player
        fields = [
            "id",
            "full_name",
            "first_name",
            "last_name",
            "nickname",
            "jersey_number",
            "position",
            "position_display",
            "team",
            "team_name",
            "photo",
            "is_captain",
            "matches_played",
            "goals",
            "assists",
            "average",
            "yellow_cards",
            "red_cards",
            "is_active",
            "posted_by",
            "birth_date",
            "tournament",
            "tournament_slug",
        ]


class PlayerDetailSerializer(serializers.ModelSerializer):
    """Serializer detallado de jugador"""

    team_name = serializers.CharField(source="team.name", read_only=True)
    tournament_name = serializers.CharField(source="tournament.name", read_only=True)
    position_display = serializers.CharField(
        source="get_position_display", read_only=True
    )
    tournament_slug = serializers.CharField(source="tournament.slug", read_only=True)

    class Meta:
        model = Player
        fields = "__all__"


class PlayerCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer para crear/actualizar jugadores"""

    posted_by = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Player
        fields = [
            "id",
            "first_name",
            "last_name",
            "nickname",
            "jersey_number",
            "position",
            "tournament",
            "team",
            "photo",
            "birth_date",
            "is_captain",
            "is_active",
            "posted_by",
        ]


class MatchEventSerializer(serializers.ModelSerializer):
    """Serializer para eventos de partido"""

    player_name = serializers.CharField(source="player.full_name", read_only=True)
    team_name = serializers.CharField(source="team.name", read_only=True)
    event_type_display = serializers.CharField(
        source="get_event_type_display", read_only=True
    )

    class Meta:
        model = MatchEvent
        fields = [
            "id",
            "event_type",
            "event_type_display",
            "minute",
            "player",
            "player_name",
            "team",
            "team_name",
            "description",
        ]


class MatchListSerializer(serializers.ModelSerializer):
    """Serializer para listado de partidos"""

    home_team_name = serializers.CharField(source="home_team.name", read_only=True)
    away_team_name = serializers.CharField(source="away_team.name", read_only=True)
    home_team_logo = serializers.CharField(source="home_team.logo", read_only=True)
    away_team_logo = serializers.CharField(source="away_team.logo", read_only=True)
    tournament_name = serializers.CharField(source="tournament.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Match
        fields = [
            "id",
            "tournament",
            "tournament_name",
            "home_team",
            "home_team_name",
            "home_team_logo",
            "away_team",
            "away_team_name",
            "away_team_logo",
            "home_score",
            "away_score",
            "home_runs",
            "away_runs",  # Softbol
            "match_date",
            "venue",
            "status",
            "status_display",
            "round_number",
        ]


class MatchDetailSerializer(serializers.ModelSerializer):
    """Serializer detallado de partido con eventos"""

    home_team_detail = TeamListSerializer(source="home_team", read_only=True)
    away_team_detail = TeamListSerializer(source="away_team", read_only=True)
    tournament_name = serializers.CharField(source="tournament.name", read_only=True)
    events = MatchEventSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Match
        fields = "__all__"


class MatchCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer para crear/actualizar partidos"""

    class Meta:
        model = Match
        fields = [
            "tournament",
            "home_team",
            "away_team",
            "match_date",
            "venue",
            "stadium",
            "round_number",
            "match_week",
            "notes",
        ]

    def validate(self, data):
        # Validar que los equipos pertenezcan al mismo torneo
        if data["home_team"] == data["away_team"]:
            raise serializers.ValidationError("Los equipos deben ser diferentes")

        if data["home_team"].tournament != data["away_team"].tournament:
            raise serializers.ValidationError(
                "Los equipos deben pertenecer al mismo torneo"
            )

        return data


class StandingsSerializer(serializers.Serializer):
    """Serializer para tabla de posiciones"""

    position = serializers.IntegerField()
    team = TeamListSerializer()
    played = serializers.IntegerField()
    won = serializers.IntegerField()
    drawn = serializers.IntegerField()
    lost = serializers.IntegerField()
    goals_for = serializers.IntegerField()
    goals_against = serializers.IntegerField()
    goal_difference = serializers.IntegerField()
    points = serializers.IntegerField()
    # Softbol
    runs = serializers.IntegerField(required=False)
    runs_against = serializers.IntegerField(required=False)
    average = serializers.FloatField(required=False)
