from datetime import timedelta
from django.utils import timezone
from rest_framework import serializers
from .models import (
    Tournament,
    TournamentPhase,
    CompetitionGroup,
    GroupMembership,
    Bracket,
    BracketNode,
    Team,
    Player,
    Match,
    MatchEvent,
    MatchLineup,
    AdvertisementBanner,
)


class TournamentCreateSerializer(serializers.ModelSerializer):
    format_template = serializers.CharField(required=False, allow_blank=True, default="")
    format_group_count = serializers.IntegerField(required=False, default=1, write_only=True)

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
            "structure_mode",
            "format_template",
            "format_group_count",
            "scoring_config",
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
            "structure_mode",
            "format_template",
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
            "id_number",
            "email",
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
    team_slug = serializers.CharField(source="team.slug", read_only=True)
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
            "id_number",
            "email",
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
            "started_at",
            "finished_at",
            "status",
            "status_display",
            "round_number",
            "match_week",
            "match_type",
            "phase",
            "group",
        ]


class MatchDetailSerializer(serializers.ModelSerializer):
    """Serializer detallado de partido con eventos"""

    home_team_detail = TeamListSerializer(source="home_team", read_only=True)
    away_team_detail = TeamListSerializer(source="away_team", read_only=True)
    tournament_name = serializers.CharField(source="tournament.name", read_only=True)
    tournament_slug = serializers.CharField(source="tournament.slug", read_only=True)
    events = MatchEventSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    # Logos
    home_team_logo = serializers.CharField(source="home_team.logo", read_only=True)
    away_team_logo = serializers.CharField(source="away_team.logo", read_only=True)

    class Meta:
        model = Match
        fields = "__all__"


class GroupMembershipSerializer(serializers.ModelSerializer):
    team = TeamListSerializer(read_only=True)
    team_id = serializers.PrimaryKeyRelatedField(
        queryset=Team.objects.all(), source="team", write_only=True
    )

    class Meta:
        model = GroupMembership
        fields = ["id", "team", "team_id", "seed"]


class CompetitionGroupSerializer(serializers.ModelSerializer):
    memberships = GroupMembershipSerializer(many=True, read_only=True)
    teams_count = serializers.IntegerField(source="memberships.count", read_only=True)

    class Meta:
        model = CompetitionGroup
        fields = [
            "id",
            "name",
            "slug",
            "order",
            "max_teams",
            "teams_count",
            "memberships",
        ]


class BracketNodeSerializer(serializers.ModelSerializer):
    round_display = serializers.CharField(source="get_round_display", read_only=True)
    match = MatchListSerializer(read_only=True)
    home_team = serializers.SerializerMethodField()
    away_team = serializers.SerializerMethodField()
    home_label = serializers.SerializerMethodField()
    away_label = serializers.SerializerMethodField()

    class Meta:
        model = BracketNode
        fields = [
            "id",
            "round",
            "round_display",
            "position",
            "match",
            "home_source",
            "away_source",
            "home_team",
            "away_team",
            "home_label",
            "away_label",
        ]

    def _resolve(self, obj, side):
        from sports.services.advancement import resolve_team_source

        source = obj.home_source if side == "home" else obj.away_source
        tournament = obj.bracket.phase.tournament
        from_phase = self.context.get("from_phase")
        team = resolve_team_source(source, tournament, from_phase=from_phase)
        if team:
            return TeamListSerializer(team).data
        return None

    def get_home_team(self, obj):
        return self._resolve(obj, "home")

    def get_away_team(self, obj):
        return self._resolve(obj, "away")

    def _label(self, source):
        if not source:
            return "Por definir"
        t = source.get("type")
        if t == "group_rank":
            return f"{source.get('rank')}° {source.get('group_slug', 'grupo')}"
        if t == "overall_rank":
            return f"{source.get('rank')}° fase regular"
        if t == "bracket_winner":
            return f"Ganador {source.get('round')} #{source.get('position')}"
        if t == "team":
            return "Equipo fijo"
        return "Por definir"

    def get_home_label(self, obj):
        return self._label(obj.home_source)

    def get_away_label(self, obj):
        return self._label(obj.away_source)


class BracketSerializer(serializers.ModelSerializer):
    nodes = BracketNodeSerializer(many=True, read_only=True)

    class Meta:
        model = Bracket
        fields = ["id", "name", "nodes"]


class TournamentPhaseSerializer(serializers.ModelSerializer):
    groups = CompetitionGroupSerializer(many=True, read_only=True)
    bracket = BracketSerializer(read_only=True)
    phase_type_display = serializers.CharField(
        source="get_phase_type_display", read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = TournamentPhase
        fields = [
            "id",
            "name",
            "slug",
            "phase_type",
            "phase_type_display",
            "order",
            "status",
            "status_display",
            "config",
            "advancement_rules",
            "groups",
            "bracket",
        ]


class TournamentStructureSerializer(serializers.Serializer):
    structure_mode = serializers.CharField()
    format_template = serializers.CharField()
    phases = TournamentPhaseSerializer(many=True)


class AssignTeamsToGroupSerializer(serializers.Serializer):
    group_id = serializers.UUIDField()
    team_ids = serializers.ListField(
        child=serializers.UUIDField(), allow_empty=False
    )


class GenerateFixtureSerializer(serializers.Serializer):
    phase_id = serializers.UUIDField()
    group_id = serializers.UUIDField(required=False, allow_null=True)
    match_date = serializers.DateTimeField()
    venue = serializers.CharField(required=False, allow_blank=True, default="")


class AdvancePhaseSerializer(serializers.Serializer):
    from_phase = serializers.SlugField()
    match_date = serializers.DateTimeField(required=False, allow_null=True)
    venue = serializers.CharField(required=False, allow_blank=True, default="")


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
            "phase",
            "group",
            "match_type",
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


# en tournaments/serializers.py


class MatchLineupSerializer(serializers.ModelSerializer):
    """Ver alineación de un partido"""

    player_name = serializers.CharField(source="player.full_name", read_only=True)
    player_photo = serializers.CharField(source="player.photo", read_only=True)
    team_name = serializers.CharField(source="team.name", read_only=True)
    position_display = serializers.CharField(
        source="get_position_display", read_only=True
    )
    status = serializers.SerializerMethodField()  # ← NUEVO
    status_display = serializers.SerializerMethodField()  # ← NUEVO
    minute_out = serializers.SerializerMethodField()  # ← NUEVO
    minute_in = serializers.SerializerMethodField()
    entry_number = serializers.IntegerField(read_only=True)

    class Meta:
        model = MatchLineup
        fields = [
            "id",
            "match",
            "team",
            "team_name",
            "player",
            "player_name",
            "player_photo",
            "is_starter",
            "position",
            "position_display",
            "jersey_number",
            "substitution_minute",
            "status",
            "status_display",
            "minute_out",
            "minute_in",
            "entry_number",
        ]

    def get_status(self, obj):
        if obj.is_starter and obj.is_on_field:
            return "playing"  # titular jugando

        if obj.is_starter and not obj.is_on_field:
            return "substituted"  # titular que salió

        if not obj.is_starter and obj.is_on_field:
            return "entered"  # suplente que entró

        if not obj.is_starter and not obj.is_on_field:
            return "on_bench"  # suplente en banca

        return "unknown"

    def get_status_display(self, obj):
        return dict(MatchLineup.STATUS_CHOICES).get(self.get_status(obj), "")

    def get_minute_out(self, obj):
        # Salió si estaba en cancha y ya no está (is_starter y no is_on_field)
        if not obj.is_on_field and obj.substitution_minute is not None:
            return obj.substitution_minute
        return None

    def get_minute_in(self, obj):
        # Entró como sustituto (no es starter y está en cancha)
        if (
            not obj.is_starter
            and obj.is_on_field
            and obj.substitution_minute is not None
        ):
            return obj.substitution_minute
        return None


class MatchLineupCreateSerializer(serializers.ModelSerializer):
    """Crear/actualizar alineación"""

    posted_by = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = MatchLineup
        fields = [
            "match",
            "team",
            "player",
            "is_starter",
            "position",
            "jersey_number",
            "substitution_minute",
            "posted_by",
        ]

    def validate(self, data):
        # El jugador debe pertenecer al equipo
        if data["player"].team != data["team"]:
            raise serializers.ValidationError("El jugador no pertenece a este equipo")
        # El equipo debe pertenecer al partido
        match = data["match"]
        team = data["team"]
        if team != match.home_team and team != match.away_team:
            raise serializers.ValidationError("El equipo no participa en este partido")
        return data


class MatchLineupBulkCreateSerializer(serializers.Serializer):
    """Crear la alineación completa de un equipo de una sola vez"""

    team = serializers.PrimaryKeyRelatedField(queryset=Team.objects.all())
    players = MatchLineupCreateSerializer(many=True)

    def validate(self, data):
        starters = [p for p in data["players"] if p.get("is_starter", True)]
        if len(starters) > 11:  # Ajusta según el deporte
            raise serializers.ValidationError("No puedes tener más de 11 titulares")
        return data


class AdvertisementBannerSerializer(serializers.ModelSerializer):
    """Serializer para listado público de banners"""

    position_display = serializers.CharField(
        source="get_position_display", read_only=True
    )
    is_visible = serializers.BooleanField(read_only=True)
    posted_by_name = serializers.CharField(
        source="posted_by.get_full_name", read_only=True
    )
    tournament_name = serializers.CharField(source="tournament.name", read_only=True)
    tournament_slug = serializers.CharField(source="tournament.slug", read_only=True)

    class Meta:
        model = AdvertisementBanner
        fields = [
            "id",
            "title",
            "description",
            "image",
            "link_url",
            "position",
            "position_display",
            "tournament",  # ← ID del torneo
            "tournament_name",
            "tournament_slug",
            "is_active",
            "display_order",
            "start_date",
            "end_date",
            "is_visible",
            "clicks",
            "impressions",
            "posted_by",  # ← ID del usuario
            "posted_by_name",
            "created_at",
        ]


class AdvertisementBannerCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer para crear/actualizar banners (requiere autenticación)"""

    posted_by = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = AdvertisementBanner
        fields = [
            "id",
            "title",
            "description",
            "image",
            "link_url",
            "position",
            "is_active",
            "display_order",
            "start_date",
            "end_date",
            "tournament",
            "posted_by",
        ]

    def validate(self, data):
        # Obtener start_date de los datos o de la instancia existente o usar hoy
        start = data.get("start_date")
        if not start:
            if self.instance:
                start = self.instance.start_date
            else:
                start = timezone.now().date()
                data["start_date"] = start

        # Si no se envía end_date, poner automáticamente 30 días después de start_date
        end = data.get("end_date")
        if not end:
            end = start + timedelta(days=30)
            data["end_date"] = end

        # Validar que fecha fin sea posterior a fecha inicio
        if end < start:
            raise serializers.ValidationError(
                {"end_date": "La fecha de fin debe ser posterior a la fecha de inicio."}
            )
        return data
