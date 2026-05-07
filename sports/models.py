from django.db import models
from core.models import TimeStampedModel
from organizations.models import Organization
from authentication.models import User


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

    # Imagen
    logo = models.URLField(blank=True)
    banner = models.URLField(blank=True)

    class Meta:
        db_table = "tournaments"
        ordering = ["-start_date"]

    def __str__(self):
        return self.name


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

    class Meta:
        db_table = "matches"
        ordering = ["match_date"]

    def __str__(self):
        return f"{self.home_team.name} vs {self.away_team.name}"

    @property
    def winner(self):
        if self.home_score is None or self.away_score is None:
            return None
        if self.home_score > self.away_score:
            return self.home_team
        elif self.away_score > self.home_score:
            return self.away_team
        return None  # Empate


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
    ]
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES)

    minute = models.PositiveIntegerField()  # Minuto del partido
    description = models.TextField(blank=True)

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

    class Meta:
        db_table = "match_lineups"
        unique_together = [
            "match",
            "player",
        ]  # Un jugador no puede estar dos veces en el mismo partido
        ordering = ["-is_starter", "jersey_number"]

    def __str__(self):
        role = "Titular" if self.is_starter else "Suplente"
        return f"{self.player.full_name} - {self.match} ({role})"
