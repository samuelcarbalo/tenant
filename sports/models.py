from django.db import models
from core.models import TimeStampedModel
from organizations.models import Organization
from authentication.models import User
from django.utils import timezone


class Tournament(TimeStampedModel):
    """
    Torneo/Competición deportiva
    """

    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    posted_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="posted_tournaments",
    )
    SPORT_TYPES = [
        ("football", "Fútbol"),
        ("basketball", "Baloncesto"),
        ("tennis", "Tenis"),
        ("volleyball", "Voleibol"),
        ("softball", "Softbol"),
        ("other", "Otro"),
    ]

    sport_type = models.CharField(
        max_length=20, choices=SPORT_TYPES, default="football"
    )
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="tournaments"
    )

    # Fechas
    start_date = models.DateField()
    end_date = models.DateField()
    registration_deadline = models.DateField(null=True, blank=True)

    # Configuración
    max_teams = models.PositiveIntegerField(default=16)
    min_players_per_team = models.PositiveIntegerField(default=5)
    max_players_per_team = models.PositiveIntegerField(default=25)

    # Estado
    STATUS_CHOICES = [
        ("draft", "Borrador"),
        ("registration", "Inscripción"),
        ("active", "En curso"),
        ("finished", "Finalizado"),
        ("cancelled", "Cancelado"),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")

    MODERATION_STATUS_CHOICES = [
        ("approved", "Aprobada"),
        ("pendiente_revision", "Pendiente revisión"),
        ("rejected", "Rechazada"),
    ]
    moderation_status = models.CharField(
        max_length=32,
        choices=MODERATION_STATUS_CHOICES,
        default="approved",
        db_index=True,
    )

    # Imagen
    logo = models.URLField(blank=True)
    banner = models.URLField(blank=True)

    impressions = models.PositiveIntegerField(default=0, verbose_name="Impresiones")

    STRUCTURE_MODE_CHOICES = [
        ("legacy", "Liga simple"),
        ("structured", "Multi-fase"),
    ]
    structure_mode = models.CharField(
        max_length=20, choices=STRUCTURE_MODE_CHOICES, default="legacy"
    )
    format_template = models.CharField(max_length=50, blank=True, default="")
    scoring_config = models.JSONField(default=dict, blank=True)
    rules_url = models.URLField(max_length=500, blank=True, verbose_name="Reglamento (URL)")
    lineup_size = models.PositiveSmallIntegerField(
        default=9,
        help_text="Titulares en campo: 9 estándar, 10 con bateador designado (softbol).",
    )
    regulation_innings = models.PositiveSmallIntegerField(
        default=7,
        help_text="Entradas reglamentarias (softbol: 7 estándar).",
    )
    mercy_rule_enabled = models.BooleanField(
        default=True,
        help_text="Aplica knockout por diferencia de carreras (softbol).",
    )

    class Meta:
        db_table = "tournaments"
        ordering = ["-start_date"]

    def __str__(self):
        return self.name


class TournamentPhase(TimeStampedModel):
    """Fase de un torneo (grupos, eliminatoria, etc.)."""

    PHASE_TYPES = [
        ("group_stage", "Fase de grupos"),
        ("round_robin", "Todos contra todos"),
        ("knockout", "Eliminatoria"),
        ("placement", "Partido por puesto"),
    ]
    STATUS_CHOICES = [
        ("pending", "Pendiente"),
        ("active", "En curso"),
        ("finished", "Finalizada"),
    ]

    tournament = models.ForeignKey(
        Tournament, on_delete=models.CASCADE, related_name="phases"
    )
    name = models.CharField(max_length=100)
    slug = models.SlugField()
    phase_type = models.CharField(max_length=20, choices=PHASE_TYPES)
    order = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    config = models.JSONField(default=dict, blank=True)
    advancement_rules = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "tournament_phases"
        ordering = ["order", "name"]
        unique_together = ["tournament", "slug"]

    def __str__(self):
        return f"{self.tournament.name} — {self.name}"


class CompetitionGroup(TimeStampedModel):
    """Grupo o cuadrangular dentro de una fase."""

    phase = models.ForeignKey(
        TournamentPhase, on_delete=models.CASCADE, related_name="groups"
    )
    name = models.CharField(max_length=50)
    slug = models.SlugField()
    order = models.PositiveSmallIntegerField(default=1)
    max_teams = models.PositiveSmallIntegerField(default=4)

    class Meta:
        db_table = "competition_groups"
        ordering = ["order", "name"]
        unique_together = ["phase", "slug"]

    def __str__(self):
        return f"{self.phase.name} — {self.name}"


class GroupMembership(models.Model):
    """Equipo asignado a un grupo."""

    group = models.ForeignKey(
        CompetitionGroup, on_delete=models.CASCADE, related_name="memberships"
    )
    team = models.ForeignKey(
        "Team", on_delete=models.CASCADE, related_name="group_memberships"
    )
    seed = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        db_table = "group_memberships"
        unique_together = ["group", "team"]

    def __str__(self):
        return f"{self.team.name} @ {self.group.name}"


class Bracket(TimeStampedModel):
    """Eliminatoria asociada a una fase."""

    phase = models.OneToOneField(
        TournamentPhase, on_delete=models.CASCADE, related_name="bracket"
    )
    name = models.CharField(max_length=100, default="Eliminatoria")

    class Meta:
        db_table = "brackets"

    def __str__(self):
        return f"{self.phase.tournament.name} — {self.name}"


class BracketNode(TimeStampedModel):
    """Nodo del bracket (semifinal, final, etc.)."""

    ROUND_CHOICES = [
        ("quarterfinal", "Cuartos de final"),
        ("semifinal", "Semifinal"),
        ("final", "Final"),
        ("third_place", "Tercer puesto"),
    ]

    bracket = models.ForeignKey(Bracket, on_delete=models.CASCADE, related_name="nodes")
    round = models.CharField(max_length=20, choices=ROUND_CHOICES)
    position = models.PositiveSmallIntegerField(default=1)
    match = models.OneToOneField(
        "Match",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="bracket_node",
    )
    home_source = models.JSONField(default=dict, blank=True)
    away_source = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "bracket_nodes"
        ordering = ["round", "position"]
        unique_together = ["bracket", "round", "position"]

    def __str__(self):
        return f"{self.get_round_display()} #{self.position}"


class Team(TimeStampedModel):
    """
    Equipo deportivo
    """

    name = models.CharField(max_length=255)
    slug = models.SlugField()
    abbreviation = models.CharField(max_length=10)
    description = models.TextField(blank=True)
    posted_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="posted_teams",
    )
    tournament = models.ForeignKey(
        Tournament, on_delete=models.CASCADE, related_name="teams"
    )
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="sports_teams"
    )

    # Colores y branding
    primary_color = models.CharField(max_length=7, default="#000000")
    secondary_color = models.CharField(max_length=7, default="#FFFFFF")
    logo = models.URLField(blank=True)

    # Contacto
    coach_name = models.CharField(max_length=255, blank=True)
    coach_email = models.EmailField(blank=True)
    coach_phone = models.CharField(max_length=20, blank=True)

    # Estadísticas del torneo
    played = models.PositiveIntegerField(default=0)
    won = models.PositiveIntegerField(default=0)
    drawn = models.PositiveIntegerField(default=0)
    lost = models.PositiveIntegerField(default=0)
    goals_for = models.PositiveIntegerField(default=0)
    goals_against = models.PositiveIntegerField(default=0)
    points = models.PositiveIntegerField(default=0)
    runs = models.PositiveIntegerField(default=0)
    runs_against = models.PositiveIntegerField(default=0)
    average = models.FloatField(default=0.0)
    strikes = models.PositiveIntegerField(default=0)
    strikes_against = models.PositiveIntegerField(default=0)
    average_strikes = models.FloatField(default=0.0)
    walks = models.PositiveIntegerField(default=0)
    walks_against = models.PositiveIntegerField(default=0)
    average_walks = models.FloatField(default=0.0)
    home_runs = models.PositiveIntegerField(default=0)
    home_runs_against = models.PositiveIntegerField(default=0)
    average_home_runs = models.FloatField(default=0.0)
    strikes_out = models.PositiveIntegerField(default=0)
    strikes_out_against = models.PositiveIntegerField(default=0)
    average_strikes_out = models.FloatField(default=0.0)

    impressions = models.PositiveIntegerField(default=0, verbose_name="Impresiones")

    class Meta:
        db_table = "teams"
        unique_together = ["tournament", "slug"]
        ordering = ["-points", "-goals_for", "name"]

    def __str__(self):
        return f"{self.name} ({self.tournament.name})"

    @property
    def goal_difference(self):
        return self.goals_for - self.goals_against


class Player(TimeStampedModel):
    """
    Jugador
    """

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    nickname = models.CharField(max_length=100, blank=True)
    id_number = models.CharField(max_length=50, blank=True, verbose_name="Cédula")
    email = models.EmailField(blank=True, verbose_name="Correo electrónico")
    posted_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="posted_players",
    )
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="players")
    tournament = models.ForeignKey(
        Tournament, on_delete=models.CASCADE, related_name="players"
    )

    # Información personal
    birth_date = models.DateField(null=True, blank=True)
    nationality = models.CharField(max_length=100, blank=True)
    photo = models.URLField(blank=True)

    # Posición
    POSITION_CHOICES = [
        ("goalkeeper", "Portero"),
        ("defender", "Defensa"),
        ("midfielder", "Mediocampista"),
        ("forward", "Delantero"),
        ("coach", "Entrenador"),
        ("staff", "Staff"),
        ("pitcher", "Lanzador"),
        ("catcher", "Receptor"),
        ("first_base", "Primera Base"),
        ("second_base", "Segunda Base"),
        ("third_base", "Tercera Base"),
        ("shortstop", "Shortstop"),
        ("left_field", "Jardinero Izquierdo"),
        ("center_field", "Jardinero Central"),
        ("right_field", "Jardinero Derecho"),
        ("designated_hitter", "Bateador Designado"),
        ("utility", "Utility"),
    ]
    position = models.CharField(
        max_length=20, choices=POSITION_CHOICES, default="midfielder"
    )

    # Número de camiseta
    jersey_number = models.PositiveIntegerField(null=True, blank=True)

    # Estado
    is_active = models.BooleanField(default=True)
    is_captain = models.BooleanField(default=False)

    # Estadísticas
    matches_played = models.PositiveIntegerField(default=0)
    goals = models.PositiveIntegerField(default=0)
    assists = models.PositiveIntegerField(default=0)
    yellow_cards = models.PositiveIntegerField(default=0)
    red_cards = models.PositiveIntegerField(default=0)
    saves = models.PositiveIntegerField(default=0)
    average = models.FloatField(default=0.0)
    strikes = models.PositiveIntegerField(default=0)
    strikes_against = models.PositiveIntegerField(default=0)
    average_strikes = models.FloatField(default=0.0)
    walks = models.PositiveIntegerField(default=0)
    walks_against = models.PositiveIntegerField(default=0)
    average_walks = models.FloatField(default=0.0)
    home_runs = models.PositiveIntegerField(default=0)
    home_runs_against = models.PositiveIntegerField(default=0)
    average_home_runs = models.FloatField(default=0.0)
    strikes_out = models.PositiveIntegerField(default=0)
    strikes_out_against = models.PositiveIntegerField(default=0)
    average_strikes_out = models.FloatField(default=0.0)

    # Bateo softbol (limpio)
    at_bats = models.PositiveIntegerField(default=0)
    hits = models.PositiveIntegerField(default=0)
    runs_scored = models.PositiveIntegerField(default=0)
    rbis = models.PositiveIntegerField(default=0)
    batting_average = models.FloatField(default=0.0)

    impressions = models.PositiveIntegerField(default=0, verbose_name="Impresiones")

    class Meta:
        db_table = "players"
        ordering = ["jersey_number", "last_name", "first_name"]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def full_name(self):
        if self.nickname:
            return f"{self.first_name} '{self.nickname}' {self.last_name}"
        return f"{self.first_name} {self.last_name}"


class PlayerSuspension(TimeStampedModel):
    """Suspensión de un jugador por una o más fechas o por una sanción automática."""

    player = models.ForeignKey(
        Player,
        on_delete=models.CASCADE,
        related_name="suspensions",
    )
    tournament = models.ForeignKey(
        Tournament,
        on_delete=models.CASCADE,
        related_name="player_suspensions",
    )
    match = models.ForeignKey(
        "Match",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="player_suspensions",
    )
    suspended_until_match = models.ForeignKey(
        "Match",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="suspended_players",
        help_text="Próximo partido programado que debe cumplir la sanción.",
    )
    reason = models.CharField(
        max_length=30,
        choices=[
            ("direct_red", "Roja directa"),
            ("double_yellow", "Doble amarilla"),
            ("manual", "Manual"),
        ],
        default="manual",
    )
    matches_count = models.PositiveSmallIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_player_suspensions",
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="revoked_player_suspensions",
    )

    class Meta:
        db_table = "player_suspensions"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.player.full_name} - {self.get_reason_display()}"

    def is_active_for_match(self, match):
        if not self.is_active or not match:
            return False
        if self.suspended_until_match_id is None:
            return True
        return self.suspended_until_match_id == match.id


class Match(TimeStampedModel):
    """
    Partido/Encuentro
    """

    tournament = models.ForeignKey(
        Tournament, on_delete=models.CASCADE, related_name="matches"
    )
    posted_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="posted_matches",
    )
    # Equipos
    home_team = models.ForeignKey(
        Team, on_delete=models.CASCADE, related_name="home_matches"
    )
    away_team = models.ForeignKey(
        Team, on_delete=models.CASCADE, related_name="away_matches"
    )

    # Fecha y lugar
    match_date = models.DateTimeField()
    venue = models.CharField(max_length=255, blank=True)
    stadium = models.CharField(max_length=255, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    # Resultado
    home_score = models.PositiveIntegerField(null=True, blank=True)
    away_score = models.PositiveIntegerField(null=True, blank=True)
    home_runs = models.PositiveIntegerField(null=True, blank=True)
    away_runs = models.PositiveIntegerField(null=True, blank=True)
    home_strikes = models.PositiveIntegerField(null=True, blank=True)
    away_strikes = models.PositiveIntegerField(null=True, blank=True)
    home_walks = models.PositiveIntegerField(null=True, blank=True)
    away_walks = models.PositiveIntegerField(null=True, blank=True)
    home_home_runs = models.PositiveIntegerField(null=True, blank=True)
    away_home_runs = models.PositiveIntegerField(null=True, blank=True)
    home_strikes_out = models.PositiveIntegerField(null=True, blank=True)
    away_strikes_out = models.PositiveIntegerField(null=True, blank=True)

    # Estado
    STATUS_CHOICES = [
        ("scheduled", "Programado"),
        ("live", "En vivo"),
        ("finished", "Finalizado"),
        ("postponed", "Postergado"),
        ("cancelled", "Cancelado"),
    ]
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="scheduled"
    )

    # Información adicional
    round_number = models.PositiveIntegerField(default=1)
    match_week = models.PositiveIntegerField(default=1)
    notes = models.TextField(blank=True)

    phase = models.ForeignKey(
        TournamentPhase,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="matches",
    )
    group = models.ForeignKey(
        CompetitionGroup,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="matches",
    )
    MATCH_TYPES = [
        ("group", "Fase de grupos"),
        ("knockout", "Eliminatoria"),
        ("friendly", "Amistoso"),
        ("legacy", "Liga simple"),
    ]
    match_type = models.CharField(max_length=20, choices=MATCH_TYPES, default="legacy")
    stats_counted = models.BooleanField(default=False)

    impressions = models.PositiveIntegerField(default=0, verbose_name="Impresiones")

    class Meta:
        db_table = "matches"
        ordering = ["match_date"]

    def __str__(self):
        return f"{self.home_team.name} vs {self.away_team.name}"

    @property
    def winner(self):
        from sports.scoring import get_scoring_config

        config = get_scoring_config(self.tournament)
        home_field, away_field = config["primary_fields"]
        home_val = getattr(self, home_field)
        away_val = getattr(self, away_field)
        if home_val is None or away_val is None:
            return None
        if home_val > away_val:
            return self.home_team
        if away_val > home_val:
            return self.away_team
        return None if config.get("allows_draw") else None


class MatchEvent(TimeStampedModel):
    """
    Eventos de un partido (goles, tarjetas, sustituciones)
    """

    posted_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="posted_match_events",
    )
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="events")
    team = models.ForeignKey(
        Team, on_delete=models.CASCADE, related_name="match_events"
    )
    player = models.ForeignKey(
        Player, on_delete=models.CASCADE, related_name="events", null=True, blank=True
    )

    EVENT_TYPES = [
        ("goal", "Gol"),
        ("own_goal", "Autogol"),
        ("yellow_card", "Tarjeta Amarilla"),
        ("red_card", "Tarjeta Roja"),
        ("substitution_in", "Entra"),
        ("substitution_out", "Sale"),
        ("penalty_goal", "Gol de Penal"),
        ("penalty_missed", "Penal Fallado"),
        ("assist", "Asistencia"),
        ("expelled", "Expulsado"),
        # Softbol / béisbol
        ("single", "Sencillo"),
        ("double", "Doble"),
        ("triple", "Triple"),
        ("home_run", "Jonrón"),
        ("walk", "Base por bolas"),
        ("strikeout", "Ponche"),
        ("run", "Carrera anotada"),
        ("rbi", "Carrera impulsada"),
        ("error", "Error"),
        ("out", "Out"),
    ]
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES)

    minute = models.PositiveIntegerField(null=True, blank=True)  # Minuto (fútbol)
    # Contexto softbol
    inning_number = models.PositiveSmallIntegerField(null=True, blank=True)
    inning_half = models.CharField(
        max_length=6, blank=True,
        choices=[("top", "Alta"), ("bottom", "Baja")],
    )
    rbi = models.PositiveSmallIntegerField(default=0)
    description = models.TextField(blank=True)

    impressions = models.PositiveIntegerField(default=0, verbose_name="Impresiones")

    class Meta:
        db_table = "match_events"
        ordering = ["minute", "created_at"]

    def __str__(self):
        return f"{self.event_type} - {self.match} ({self.minute}')"


# en tournaments/models.py


class MatchLineup(TimeStampedModel):
    """
    Alineación/Convocados por partido
    """

    # Agrega esto si necesitas un campo de estado
    STATUS_CHOICES = [
        ("active", "Activo"),
        ("substituted", "Sustituido"),
        ("injured", "Lesionado"),
        ("suspended", "Suspendido"),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")

    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="lineups")
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="lineups")
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="lineups")
    posted_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="posted_lineups"
    )

    is_starter = models.BooleanField(default=True)  # Titular vs suplente
    is_on_field = models.BooleanField(default=True)
    position = models.CharField(
        max_length=20, choices=Player.POSITION_CHOICES, blank=True
    )
    jersey_number = models.PositiveIntegerField(null=True, blank=True)

    # Si entró como sustituto, en qué minuto
    substitution_minute = models.PositiveIntegerField(null=True, blank=True)
    entry_number = models.PositiveIntegerField(default=1)
    batting_order = models.PositiveSmallIntegerField(null=True, blank=True)

    impressions = models.PositiveIntegerField(default=0, verbose_name="Impresiones")

    class Meta:
        db_table = "match_lineups"
        unique_together = ["match", "player", "entry_number"]
        ordering = ["batting_order", "-is_starter", "jersey_number"]

    def __str__(self):
        role = "Titular" if self.is_starter else "Suplente"
        return f"{self.player.full_name} - {self.match} ({role})"


class MatchPeriod(TimeStampedModel):
    """
    Períodos de un partido (1T, descanso, 2T, tiempo extra, etc.)
    """

    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="periods")
    period_number = models.PositiveIntegerField()  # 1, 2, 3...
    name = models.CharField(max_length=50)  # "1er Tiempo", "2do Tiempo", etc.

    # Tiempos
    started_at = models.DateTimeField(null=True, blank=True)
    paused_at = models.DateTimeField(null=True, blank=True)
    resumed_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    # Tiempo acumulado en segundos antes de la última pausa
    elapsed_seconds_before_pause = models.PositiveIntegerField(default=0)

    is_active = models.BooleanField(default=False)
    is_completed = models.BooleanField(default=False)

    impressions = models.PositiveIntegerField(default=0, verbose_name="Impresiones")

    class Meta:
        db_table = "match_periods"
        ordering = ["period_number"]
        unique_together = ["match", "period_number"]

    def __str__(self):
        return f"{self.match} - {self.name}"

    @property
    def elapsed_seconds(self):
        """Tiempo transcurrido real considerando pausas"""
        if not self.started_at:
            return 0

        # Si está pausado
        if self.paused_at and not self.resumed_at:
            base = self.elapsed_seconds_before_pause
            last_segment = (self.paused_at - self.started_at).total_seconds()
            # Restar tiempo de pausas anteriores
            return int(base + last_segment)

        # Si está en curso
        if self.started_at and not self.ended_at:
            now = timezone.now()
            reference = self.resumed_at or self.started_at
            base = self.elapsed_seconds_before_pause
            current_segment = (now - reference).total_seconds()
            return int(base + current_segment)

        # Si terminó
        if self.ended_at:
            return self.elapsed_seconds_before_pause

        return 0

    @property
    def elapsed_minutes(self):
        return self.elapsed_seconds // 60


class MatchInning(TimeStampedModel):
    """
    Media entrada de un partido de softbol/béisbol (line score).
    Convención: en la 'alta' (top) batea el visitante; en la 'baja' (bottom) el local.
    """

    HALF_CHOICES = [
        ("top", "Alta"),
        ("bottom", "Baja"),
    ]

    match = models.ForeignKey(
        Match, on_delete=models.CASCADE, related_name="innings"
    )
    number = models.PositiveSmallIntegerField()  # 1, 2, 3...
    half = models.CharField(max_length=6, choices=HALF_CHOICES)

    runs = models.PositiveIntegerField(default=0)
    hits = models.PositiveIntegerField(default=0)
    errors = models.PositiveIntegerField(default=0)

    is_complete = models.BooleanField(default=False)

    class Meta:
        db_table = "match_innings"
        unique_together = ["match", "number", "half"]
        # 'top' > 'bottom' alfabéticamente: -half deja la alta antes que la baja.
        ordering = ["number", "-half"]

    def __str__(self):
        return f"{self.match} - E{self.number}{'▲' if self.half == 'top' else '▼'}"

    @property
    def batting_team(self):
        return self.match.away_team if self.half == "top" else self.match.home_team


class AdvertisementBanner(TimeStampedModel):
    """
    Banners publicitarios / Imágenes publicitarias
    Todos son públicos y visibles sin autenticación
    """

    tournament = models.ForeignKey(
        Tournament,
        on_delete=models.CASCADE,
        related_name="banners",
        null=True,
        blank=True,
        verbose_name="Torneo",
    )

    title = models.CharField(max_length=255, verbose_name="Título")
    description = models.TextField(blank=True, verbose_name="Descripción")
    image = models.URLField(verbose_name="URL de la imagen")
    link_url = models.URLField(blank=True, verbose_name="URL de destino")

    sponsorship = models.ForeignKey(
        "advertising.TournamentSponsorship",
        on_delete=models.CASCADE,
        related_name="banners",
        null=True,
        blank=True,
        verbose_name="Patrocinio",
    )
    campaign = models.ForeignKey(
        "advertising.ClassifiedAdCampaign",
        on_delete=models.CASCADE,
        related_name="banners",
        null=True,
        blank=True,
        verbose_name="Campaña",
    )

    # Posición / ubicación en la app
    POSITION_CHOICES = [
        ("home_hero", "Home - Banner Principal"),
        ("home_sidebar", "Home - Sidebar"),
        ("tournament_detail", "Detalle de Torneo"),
        ("match_detail", "Detalle de Partido"),
        ("standings_top", "Tabla de Posiciones - Arriba"),
        ("standings_bottom", "Tabla de Posiciones - Abajo"),
        ("jobs_list_top", "Empleos - Listado"),
        ("job_detail", "Empleo - Detalle"),
        ("listings_list_top", "Inmuebles - Listado"),
        ("listing_detail", "Inmueble - Detalle"),
        ("events_list_top", "Eventos - Listado"),
        ("event_detail", "Evento - Detalle"),
        ("footer", "Footer"),
        ("popup", "Popup Modal"),
    ]
    position = models.CharField(
        max_length=30,
        choices=POSITION_CHOICES,
        default="home_hero",
        verbose_name="Posición",
    )

    # Control de visibilidad y orden
    is_active = models.BooleanField(default=True, verbose_name="Activo")
    display_order = models.PositiveIntegerField(
        default=0, verbose_name="Orden de visualización"
    )

    # Fechas de publicación
    start_date = models.DateField(null=True, blank=True, verbose_name="Fecha inicio")
    end_date = models.DateField(null=True, blank=True, verbose_name="Fecha fin")

    # Métricas (opcional, para tracking)
    clicks = models.PositiveIntegerField(default=0, verbose_name="Clicks")
    impressions = models.PositiveIntegerField(default=0, verbose_name="Impresiones")

    # Quién lo creó (solo para auditoria interna, no afecta visibilidad)
    posted_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="posted_banners",
    )

    class Meta:
        db_table = "advertisement_banners"
        ordering = ["position", "display_order", "-created_at"]
        verbose_name = "Banner Publicitario"
        verbose_name_plural = "Banners Publicitarios"

    def __str__(self):
        return f"{self.title} ({self.get_position_display()})"

    @property
    def is_visible(self):
        """Verificar si el banner debe mostrarse según fechas y estado"""
        today = timezone.now().date()
        if not self.is_active:
            return False
        if self.start_date and today < self.start_date:
            return False
        if self.end_date and today > self.end_date:
            return False
        return True
