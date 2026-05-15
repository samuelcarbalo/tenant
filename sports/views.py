from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.db.models import Q, Count, Prefetch, F
from django.utils import timezone
from django.db import transaction
from .models import (
    Tournament,
    Team,
    Player,
    Match,
    MatchEvent,
    MatchLineup,
    MatchPeriod,
    AdvertisementBanner,
)
from .serializers import (
    TournamentListSerializer,
    TournamentDetailSerializer,
    TeamListSerializer,
    TeamDetailSerializer,
    TeamCreateUpdateSerializer,  # NUEVO
    PlayerListSerializer,
    PlayerDetailSerializer,
    PlayerCreateUpdateSerializer,  # NUEVO
    MatchListSerializer,
    MatchDetailSerializer,
    MatchCreateUpdateSerializer,
    MatchEventSerializer,
    StandingsSerializer,
    TournamentCreateSerializer,
    MatchLineupSerializer,
    MatchLineupCreateSerializer,
    AdvertisementBannerCreateUpdateSerializer,
    AdvertisementBannerSerializer,
)
from core.permissions import IsOrganizationMember, IsCoachOfTeam


class TournamentViewSet(viewsets.ModelViewSet):
    """ViewSet para torneos"""

    queryset = Tournament.objects.all()
    lookup_field = "slug"
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "description"]
    ordering_fields = ["start_date", "created_at"]

    def get_serializer_class(self):
        if self.action == "create":
            return TournamentCreateSerializer
        if self.action == "list":
            return TournamentListSerializer
        return TournamentDetailSerializer

    def get_permissions(self):
        if self.action == "create":
            return [IsAuthenticated()]
        if self.action in [
            "list",
            "retrieve",
            "standings",
            "schedule",
            "teams",
            "player_stats",
        ]:
            return [AllowAny()]
        return [IsAuthenticated(), IsOrganizationMember()]

    def get_queryset(self):
        queryset = Tournament.objects.select_related("organization").annotate(
            teams_count=Count("teams", distinct=True),
            matches_count=Count("matches", distinct=True),
        )

        # Filtrar por tipo de deporte
        sport_type = self.request.query_params.get("sport_type")
        if sport_type:
            queryset = queryset.filter(sport_type=sport_type)

        # Filtrar por estado
        status_param = self.request.query_params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param)

        # Filtrar por organización
        org_slug = self.request.query_params.get("organization")
        if org_slug:
            queryset = queryset.filter(organization__slug=org_slug)

        # Usuarios no autenticados solo ven activos/finalizados
        if not self.request.user.is_authenticated:
            queryset = queryset.filter(
                status__in=["active", "finished", "cancelled", "draft", "registration"]
            )

        # 2. Lógica de visibilidad (Aquí está el truco)
        # Si la acción NO es 'my_tournaments', aplicamos restricciones de visibilidad pública
        if self.action != "my_tournaments":
            if not self.request.user.is_authenticated:
                queryset = queryset.filter(status__in=["active", "finished"])

        return queryset.order_by("-start_date")

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        tournament_name = instance.name

        # Aquí podrías agregar lógica adicional, como borrar imágenes en S3
        # o verificar condiciones especiales antes de borrar.

        self.perform_destroy(instance)

        return Response(
            {
                "message": f"Torneo '{tournament_name}' y todos sus datos asociados han sido eliminados."
            },
            status=status.HTTP_204_NO_CONTENT,
        )

    def perform_create(self, serializer):
        serializer.save(
            posted_by=self.request.user,
            organization=self.request.user.organization,
        )

    @action(detail=True, methods=["get"], permission_classes=[AllowAny])
    def standings(self, request, slug=None):
        """Tabla de posiciones del torneo"""
        """Tabla de posiciones del torneo"""

        # DEBUG: Ver qué permisos se están aplicando
        print(f"User: {request.user}")
        print(f"Auth: {request.auth}")
        print(f"Is authenticated: {request.user.is_authenticated}")
        print(f"Permission classes: {self.permission_classes}")
        print(f"Get permissions result: {self.get_permissions()}")
        tournament = self.get_object()
        teams = Team.objects.filter(tournament=tournament).order_by(
            "-points", "-goals_for", "name"
        )

        standings = []
        for idx, team in enumerate(teams, 1):
            data = {
                "position": idx,
                "team": team,
                "played": team.played,
                "won": team.won,
                "drawn": team.drawn,
                "lost": team.lost,
                "goals_for": team.goals_for,
                "goals_against": team.goals_against,
                "goal_difference": team.goal_difference,
                "points": team.points,
            }
            # Agregar stats de softbol si aplica
            if tournament.sport_type == "softball":
                data.update(
                    {
                        "runs": team.runs,
                        "runs_against": team.runs_against,
                        "average": team.average,
                    }
                )
            standings.append(data)

        serializer = StandingsSerializer(standings, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def schedule(self, request, slug=None):
        """Calendario de partidos del torneo"""
        tournament = self.get_object()
        matches = (
            Match.objects.filter(tournament=tournament)
            .select_related("home_team", "away_team")
            .order_by("match_date")
        )

        # Filtro por estado
        status_param = request.query_params.get("status")
        if status_param:
            matches = matches.filter(status=status_param)

        # Filtro por equipo
        team_id = request.query_params.get("team")
        if team_id:
            matches = matches.filter(Q(home_team_id=team_id) | Q(away_team_id=team_id))

        serializer = MatchListSerializer(matches, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def my_tournaments(self, request):
        """
        Endpoint: /api/v1/sports/tournaments/my_tournaments/
        Solo para admins: ve todos los torneos (activos e inactivos) de su organización.
        """
        user = request.user

        # Verificar que el usuario sea admin de la organización
        if user.role not in ["manager"]:
            print(f"DEBUG: User {user} is not an admin")
            print(f"DEBUG: User role is {user.role}")
            return Response(
                {
                    "error": "No tienes permisos de administrador para ver esta información."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        else:
            queryset = self.get_queryset().filter(posted_by=user)

        # Aplicar paginación
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = TournamentListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = TournamentListSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(
        detail=True,
        methods=["get"],
        permission_classes=[AllowAny],
        authentication_classes=[],
    )
    def teams(self, request, slug=None):
        """Listar equipos de un torneo específico con paginación de DRF"""
        tournament = self.get_object()
        queryset = (
            Team.objects.filter(tournament=tournament)
            .annotate(players_count=Count("players", filter=Q(players__is_active=True)))
            .order_by("-points", "name")
        )

        # Filtro opcional por posición (si se usa 'top', cortamos el queryset)
        top_only = request.query_params.get("top")
        if top_only:
            queryset = queryset[: int(top_only)]

        # 1. Aplicar la paginación configurada en el ViewSet
        page = self.paginate_queryset(queryset)

        if page is not None:
            # 2. Si hay paginación, serializamos solo la página
            serializer = TeamListSerializer(page, many=True)
            # 3. get_paginated_response devuelve la estructura con "count", "next", etc.
            return self.get_paginated_response(serializer.data)

        # Fallback en caso de que la paginación no esté configurada
        serializer = TeamListSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"], permission_classes=[AllowAny])
    def player_stats(self, request, slug=None):
        """
        Estadísticas agregadas de jugadores del torneo
        GET /api/v1/sports/tournaments/{slug}/player_stats/
        """
        tournament = self.get_object()

        # Jugadores del torneo con stats
        players = (
            Player.objects.filter(tournament=tournament, is_active=True)
            .select_related("team")
            .order_by("-goals", "-yellow_cards", "-red_cards")
        )

        # Top goleadores
        top_scorers = players.filter(goals__gt=0).order_by("-goals")[:10]

        # Top tarjetas amarillas
        top_yellow_cards = players.filter(yellow_cards__gt=0).order_by("-yellow_cards")[
            :10
        ]

        # Top tarjetas rojas
        top_red_cards = players.filter(red_cards__gt=0).order_by("-red_cards")[:10]

        # Stats de softbol
        top_strikes = None
        top_home_runs = None
        if tournament.sport_type == "softball":
            top_strikes = players.filter(strikes__gt=0).order_by("-strikes")[:10]
            top_home_runs = players.filter(home_runs__gt=0).order_by("-home_runs")[:10]

        def serialize_players(queryset, stat_field):
            return [
                {
                    "id": p.id,
                    "full_name": p.full_name,
                    "first_name": p.first_name,
                    "last_name": p.last_name,
                    "jersey_number": p.jersey_number,
                    "photo": p.photo,
                    "team_name": p.team.name,
                    "team_slug": p.team.slug,
                    "position": p.position,
                    "position_display": p.get_position_display(),
                    stat_field: getattr(p, stat_field),
                }
                for p in queryset
            ]

        data = {
            "tournament": {
                "id": tournament.id,
                "name": tournament.name,
                "slug": tournament.slug,
                "sport_type": tournament.sport_type,
            },
            "top_scorers": serialize_players(top_scorers, "goals"),
            "top_yellow_cards": serialize_players(top_yellow_cards, "yellow_cards"),
            "top_red_cards": serialize_players(top_red_cards, "red_cards"),
        }

        if tournament.sport_type == "softball":
            data.update(
                {
                    "top_strikes": serialize_players(top_strikes, "strikes"),
                    "top_home_runs": serialize_players(top_home_runs, "home_runs"),
                }
            )

        return Response(data)


class TeamViewSet(viewsets.ModelViewSet):
    """ViewSet para equipos"""

    queryset = Team.objects.all()
    lookup_field = "slug"  # IMPORTANTE: Agregado para consistencia

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return TeamCreateUpdateSerializer  # Usar serializer específico para crear
        if self.action == "list":
            return TeamListSerializer
        return TeamDetailSerializer

    def get_permissions(self):
        if self.action in [
            "list",
            "retrieve",
            "players",
            "matches",
            "stats",
            "teams",
        ]:
            return [AllowAny()]
        return [IsAuthenticated(), IsOrganizationMember()]

    def get_queryset(self):
        queryset = Team.objects.select_related("tournament", "organization").annotate(
            players_count=Count("players", filter=Q(players__is_active=True))
        )

        # Filtrar por torneo
        tournament_slug = self.request.query_params.get("tournament")
        if tournament_slug:
            queryset = queryset.filter(tournament__slug=tournament_slug)

        # Filtrar por organización
        if self.request.user.is_authenticated and not self.request.user.is_superuser:
            queryset = queryset.filter(organization=self.request.user.organization)

        # Filtrar por estado
        return queryset.order_by("-points", "name")

    @action(detail=True, methods=["get"], permission_classes=[AllowAny])
    def players(self, request, pk=None):
        """Jugadores del equipo"""
        team = self.get_object()
        players = team.players.filter(is_active=True)

        position = request.query_params.get("position")
        if position:
            players = players.filter(position=position)

        serializer = PlayerListSerializer(players, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"], permission_classes=[AllowAny])
    def matches(self, request, pk=None):
        """Partidos del equipo"""
        team = self.get_object()
        matches = (
            Match.objects.filter(Q(home_team=team) | Q(away_team=team))
            .select_related("home_team", "away_team")
            .order_by("match_date")
        )

        serializer = MatchListSerializer(matches, many=True)
        return Response(serializer.data)

    def perform_create(self, serializer):
        """CORREGIDO: Asignar posted_by y organization automáticamente"""
        serializer.save(
            posted_by=self.request.user,
            organization=self.request.user.organization,
        )

    def perform_update(self, serializer):
        """Mantener posted_by original en actualizaciones"""
        serializer.save()


class PlayerViewSet(viewsets.ModelViewSet):
    """ViewSet para jugadores - CRUD con permisos de Coach"""

    queryset = Player.objects.all()

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return PlayerCreateUpdateSerializer
        if self.action == "list":
            return PlayerListSerializer
        return PlayerDetailSerializer

    def get_permissions(self):
        # Listar/ver detalle es público
        if self.action in ["list", "retrieve", "stats"]:
            return [AllowAny()]
        # Crear/actualizar/eliminar requiere ser coach del equipo
        return [IsAuthenticated(), IsCoachOfTeam()]

    def get_queryset(self):
        queryset = Player.objects.select_related(
            "team", "tournament", "team__tournament"
        )

        # Filtros
        team_id = self.request.query_params.get("team")
        if team_id:
            queryset = queryset.filter(team_id=team_id)
        id_number = self.request.query_params.get("id_number")
        if id_number:
            queryset = queryset.filter(id_number__icontains=id_number)

        email = self.request.query_params.get("email")
        if email:
            queryset = queryset.filter(email__icontains=email)

        tournament_slug = self.request.query_params.get("tournament")
        if tournament_slug:
            queryset = queryset.filter(tournament__slug=tournament_slug)

        position = self.request.query_params.get("position")
        if position:
            queryset = queryset.filter(position=position)

        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(nickname__icontains=search)
            )

        return queryset.order_by("jersey_number", "last_name")

    def perform_update(self, serializer):
        """Mantener posted_by original"""
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        """Eliminar jugador - solo coach puede eliminar"""
        player = self.get_object()

        if not IsCoachOfTeam().has_object_permission(request, self, player):
            return Response(
                {"error": "Solo el coach del equipo puede eliminar jugadores"},
                status=status.HTTP_403_FORBIDDEN,
            )

        player_name = player.full_name
        self.perform_destroy(player)

        return Response(
            {"message": f"Jugador '{player_name}' eliminado correctamente"},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get"], permission_classes=[AllowAny])
    def stats(self, request, pk=None):
        """Estadísticas detalladas del jugador"""
        player = self.get_object()
        # Calcular promedio de bateo para softbol
        stats = {
            "matches_played": player.matches_played,
            "goals": player.goals,
            "assists": player.assists,
            "yellow_cards": player.yellow_cards,
            "red_cards": player.red_cards,
        }

        if player.tournament.sport_type == "softball":
            stats.update(
                {
                    "average": player.average,
                    "strikes": player.strikes,
                    "walks": player.walks,
                    "home_runs": player.home_runs,
                    "strikes_out": player.strikes_out,
                }
            )

        return Response(stats)

    def create(self, request, *args, **kwargs):
        is_many = isinstance(request.data, list)
        serializer = self.get_serializer(data=request.data, many=is_many)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)  # ← Esto SÍ está bien

        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )

    def perform_create(self, serializer):
        """Asignar posted_by desde el usuario autenticado y tournament desde el team"""
        team = serializer.validated_data.get("team")
        tournament = serializer.validated_data.get("tournament")

        if not tournament and team:
            tournament = team.tournament

        serializer.save(posted_by=self.request.user, tournament=tournament)

    @property
    def tournament_slug(self):
        """Obtiene el slug del torneo automáticamente"""
        return self.tournament.slug if self.tournament else None


class MatchViewSet(viewsets.ModelViewSet):
    """ViewSet para partidos"""

    queryset = Match.objects.all()

    def get_serializer_class(self):
        if self.action == "list":
            return MatchListSerializer
        elif self.action in ["create", "update", "partial_update"]:
            return MatchCreateUpdateSerializer
        return MatchDetailSerializer

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [AllowAny()]
        return [IsAuthenticated(), IsOrganizationMember()]

    def get_queryset(self):
        queryset = Match.objects.select_related(
            "tournament", "home_team", "away_team"
        ).prefetch_related("events", "events__player")

        # Filtros
        tournament_slug = self.request.query_params.get("tournament")
        if tournament_slug:
            queryset = queryset.filter(tournament__slug=tournament_slug)

        team_id = self.request.query_params.get("team")
        if team_id:
            queryset = queryset.filter(
                Q(home_team_id=team_id) | Q(away_team_id=team_id)
            )

        status_param = self.request.query_params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param)

        # Partidos en vivo o próximos
        live_only = self.request.query_params.get("live")
        if live_only:
            queryset = queryset.filter(status="live")

        # Fecha
        date_from = self.request.query_params.get("from")
        date_to = self.request.query_params.get("to")
        if date_from:
            queryset = queryset.filter(match_date__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(match_date__date__lte=date_to)

        return queryset.order_by("match_date")

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def update_score(self, request, pk=None):
        """Actualizar marcador del partido"""
        match = self.get_object()

        # Verificar que el usuario pertenezca a la organización del torneo
        if (
            not request.user.is_superuser
            and request.user.organization != match.tournament.organization
        ):
            return Response(
                {"error": "No tienes permiso para editar este partido"},
                status=status.HTTP_403_FORBIDDEN,
            )

        home_score = request.data.get("home_score")
        away_score = request.data.get("away_score")

        # Softbol stats
        home_runs = request.data.get("home_runs")
        away_runs = request.data.get("away_runs")

        if home_score is not None:
            match.home_score = home_score
        if away_score is not None:
            match.away_score = away_score
        if home_runs is not None:
            match.home_runs = home_runs
        if away_runs is not None:
            match.away_runs = away_runs

        match.status = "finished"
        match.finished_at = timezone.now()
        match.save()

        # Actualizar estadísticas de equipos
        self._update_team_stats(match)

        serializer = MatchDetailSerializer(match)
        return Response(serializer.data)

    def _update_team_stats(self, match):
        """Actualizar estadísticas de equipos después de un partido"""
        home = match.home_team
        away = match.away_team

        # Actualizar partidos jugados
        home.played += 1
        away.played += 1

        # Determinar resultado
        if match.home_score > match.away_score:
            home.won += 1
            home.points += 3
            away.lost += 1
        elif match.away_score > match.home_score:
            away.won += 1
            away.points += 3
            home.lost += 1
        else:
            home.drawn += 1
            away.drawn += 1
            home.points += 1
            away.points += 1

        # Goles/Carreras
        home.goals_for += match.home_score or 0
        home.goals_against += match.away_score or 0
        away.goals_for += match.away_score or 0
        away.goals_against += match.home_score or 0

        # Softbol stats
        if match.tournament.sport_type == "softball":
            home.runs += match.home_runs or 0
            home.runs_against += match.away_runs or 0
            away.runs += match.away_runs or 0
            away.runs_against += match.home_runs or 0

            # Calcular average
            if home.runs_against > 0:
                home.average = home.runs / home.runs_against
            if away.runs_against > 0:
                away.average = away.runs / away.runs_against

        home.save()
        away.save()

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def add_event(self, request, pk=None):
        match = self.get_object()
        serializer = MatchEventSerializer(data=request.data)
        if serializer.is_valid():
            event = serializer.save(match=match, posted_by=request.user)
            if event.player:
                self._update_player_stats(event)
            self._update_score_from_event(event)  # ← AGREGAR
            return Response(
                MatchEventSerializer(event).data, status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def _update_score_from_event(self, event):
        """Actualizar marcador automáticamente según el evento"""
        if event.event_type != "goal":
            return

        match = event.match
        if event.team == match.home_team:
            match.home_score = (match.home_score or 0) + 1
        elif event.team == match.away_team:
            match.away_score = (match.away_score or 0) + 1

        match.save(update_fields=["home_score", "away_score"])

    def _update_player_stats(self, event):
        """Actualizar estadísticas del jugador"""
        player = event.player

        if event.event_type == "goal":
            player.goals += 1
            if event.match.tournament.sport_type == "softball":
                player.strikes += 1
        elif event.event_type == "yellow_card":
            player.yellow_cards += 1
        elif event.event_type == "red_card":
            player.red_cards += 1

        player.save()

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def start_match(self, request, pk=None):
        """Iniciar partido (cambiar estado a 'live')"""
        match = self.get_object()
        match.status = "live"
        match.started_at = timezone.now()
        match.save()
        return Response(
            {
                "status": "Partido iniciado",
                "match_id": str(match.id),
                "started_at": match.started_at,
            }
        )

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def finish_match(self, request, pk=None):
        """Finalizar partido"""
        return self.update_score(request, pk)

    def perform_create(self, serializer):
        """Asignar posted_by desde el usuario autenticado"""
        serializer.save(posted_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save()

    def perform_destroy(self, instance):
        instance.delete()

    @action(detail=True, methods=["get"], permission_classes=[AllowAny])
    def lineup(self, request, pk=None):
        """
        Ver alineación del partido separada por equipo
        GET /api/v1/sports/matches/{id}/lineup/
        """
        match = self.get_object()
        lineups = MatchLineup.objects.filter(match=match).select_related(
            "player", "team"
        )

        home_lineup = lineups.filter(team=match.home_team)
        away_lineup = lineups.filter(team=match.away_team)

        return Response(
            {
                "match_id": match.id,
                "home_team": {
                    "id": match.home_team.id,
                    "name": match.home_team.name,
                    "starters": MatchLineupSerializer(
                        home_lineup.filter(is_starter=True), many=True
                    ).data,
                    "substitutes": MatchLineupSerializer(
                        home_lineup.filter(is_starter=False), many=True
                    ).data,
                },
                "away_team": {
                    "id": match.away_team.id,
                    "name": match.away_team.name,
                    "starters": MatchLineupSerializer(
                        away_lineup.filter(is_starter=True), many=True
                    ).data,
                    "substitutes": MatchLineupSerializer(
                        away_lineup.filter(is_starter=False), many=True
                    ).data,
                },
            }
        )

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def set_lineup(self, request, pk=None):
        """
        Crear la alineación completa de UN equipo de una vez
        POST /api/v1/sports/matches/{id}/set_lineup/

        Body:
        {
            "team": 3,
            "players": [
                {"player": 42, "is_starter": true, "position": "goalkeeper", "jersey_number": 1},
                {"player": 17, "is_starter": true, "position": "defender", "jersey_number": 4},
                {"player": 23, "is_starter": false, "position": "forward", "jersey_number": 9}
            ]
        }
        """
        match = self.get_object()
        team_id = request.data.get("team")
        players_data = request.data.get("players", [])

        # Validar que el equipo pertenece al partido
        if not Team.objects.filter(
            id=team_id, id__in=[match.home_team_id, match.away_team_id]
        ).exists():
            return Response(
                {"error": "El equipo no participa en este partido"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        created = []
        errors = []

        for player_data in players_data:
            data = {"match": match.id, "team": team_id, **player_data}
            serializer = MatchLineupCreateSerializer(data=data)
            if serializer.is_valid():
                lineup = serializer.save(posted_by=request.user)
                # ← AGREGAR ESTO: los titulares empiezan en cancha
                if lineup.is_starter:
                    lineup.is_on_field = True
                    lineup.save(update_fields=["is_on_field"])
                created.append(MatchLineupSerializer(lineup).data)
            else:
                errors.append(
                    {"player": player_data.get("player"), "errors": serializer.errors}
                )

        return Response(
            {
                "created": created,
                "errors": errors,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["delete"], permission_classes=[IsAuthenticated])
    def clear_lineup(self, request, pk=None):
        """
        Borrar la alineación de un equipo para rehacer
        DELETE /api/v1/sports/matches/{id}/clear_lineup/?team=3
        """
        match = self.get_object()
        team_id = request.query_params.get("team")

        if not team_id:
            return Response(
                {"error": "Debes especificar el equipo con ?team={id}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        deleted, _ = MatchLineup.objects.filter(match=match, team_id=team_id).delete()

        return Response({"deleted": deleted})

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def substitute_player(self, request, pk=None):
        match = self.get_object()
        team_id = request.data.get("team")
        player_out_id = request.data.get("player_out")
        player_in_id = request.data.get("player_in")
        minute = request.data.get("minute")

        # --- Validaciones básicas ---
        if (
            team_id is None
            or player_out_id is None
            or player_in_id is None
            or minute is None
        ):
            return Response(
                {"error": "team, player_out, player_in y minute son requeridos"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validar que el equipo juega en este partido
        if str(match.home_team_id) != str(team_id) and str(match.away_team_id) != str(
            team_id
        ):
            return Response(
                {"error": "El equipo no participa en este partido"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # --- Validar jugador que SALE ---
        # Buscar el lineup ACTIVO (el que está en cancha actualmente)
        lineup_out = MatchLineup.objects.filter(
            match=match,
            team_id=team_id,
            player_id=player_out_id,
            is_on_field=True,  # Debe estar en cancha
        ).first()

        if not lineup_out:
            return Response(
                {"error": "El jugador que sale no está actualmente en el campo"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # --- Validar jugador que ENTRA ---
        # Buscar si ya tiene un lineup en este partido (puede haber salido antes)
        existing_lineup_in = (
            MatchLineup.objects.filter(
                match=match,
                team_id=team_id,
                player_id=player_in_id,
            )
            .order_by("-entry_number")
            .first()
        )

        # Validar que NO está actualmente en cancha
        if existing_lineup_in and existing_lineup_in.is_on_field:
            return Response(
                {"error": "Este jugador ya está jugando actualmente"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # --- Ejecutar sustitución ---

        # 1. Registrar eventos
        MatchEvent.objects.create(
            match=match,
            team_id=team_id,
            player_id=player_out_id,
            event_type="substitution_out",
            minute=minute,
            posted_by=request.user,
            description=f"Sale al minuto {minute}",
        )
        MatchEvent.objects.create(
            match=match,
            team_id=team_id,
            player_id=player_in_id,
            event_type="substitution_in",
            minute=minute,
            posted_by=request.user,
            description=f"Entra al minuto {minute}",
        )

        # 2. Actualizar jugador que SALE
        lineup_out.is_on_field = False
        lineup_out.substitution_minute = minute
        lineup_out.save()

        # 3. Crear o reactivar lineup del jugador que ENTRA
        if existing_lineup_in:
            # El jugador ya estuvo en el partido, crear nueva entrada
            new_entry_number = existing_lineup_in.entry_number + 1
            lineup_in = MatchLineup.objects.create(
                match=match,
                team_id=team_id,
                player_id=player_in_id,
                is_starter=False,
                is_on_field=True,
                entry_number=new_entry_number,
                substitution_minute=minute,
                posted_by=request.user,
            )
        else:
            # Primera vez que entra
            # Verificar que pertenece al equipo
            from .models import Player

            player_in = Player.objects.filter(id=player_in_id, team_id=team_id).first()
            if not player_in:
                return Response(
                    {"error": "El jugador no pertenece a este equipo"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            lineup_in = MatchLineup.objects.create(
                match=match,
                team_id=team_id,
                player=player_in,
                is_starter=False,
                is_on_field=True,
                entry_number=1,
                posted_by=request.user,
            )

        return Response(
            {
                "message": "Sustitución registrada correctamente",
                "minute": minute,
                "player_out": {
                    "id": player_out_id,
                    "name": lineup_out.player.full_name,
                },
                "player_in": {
                    "id": player_in_id,
                    "name": lineup_in.player.full_name,
                },
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def start_period(self, request, pk=None):
        """Iniciar un período del partido"""
        match = self.get_object()
        period_number = request.data.get("period_number", 1)
        period_name = request.data.get("name", "1er Tiempo")

        # Verificar que el partido esté en vivo
        if match.status != "live":
            return Response(
                {"error": "El partido no está en vivo"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            # Desactivar períodos anteriores
            MatchPeriod.objects.filter(match=match, is_active=True).update(
                is_active=False, ended_at=timezone.now()
            )

            # Crear o activar el período
            period, created = MatchPeriod.objects.get_or_create(
                match=match, period_number=period_number, defaults={"name": period_name}
            )

            if not created:
                period.name = period_name

            period.started_at = timezone.now()
            period.paused_at = None
            period.resumed_at = None
            period.ended_at = None
            period.is_active = True
            period.is_completed = False
            period.save()

            # Si es el primer período, actualizar started_at del match si no existe
            if period_number == 1 and not match.started_at:
                match.started_at = timezone.now()
                match.save(update_fields=["started_at"])

        return Response(
            {
                "period": period.period_number,
                "name": period.name,
                "started_at": period.started_at,
                "elapsed_minutes": period.elapsed_minutes,
            }
        )

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def pause_period(self, request, pk=None):
        """Pausar el período actual"""
        match = self.get_object()

        period = MatchPeriod.objects.filter(match=match, is_active=True).first()
        if not period:
            return Response(
                {"error": "No hay período activo"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Calcular tiempo transcurrido hasta ahora
        reference = period.resumed_at or period.started_at
        current_segment = (timezone.now() - reference).total_seconds()

        period.elapsed_seconds_before_pause += int(current_segment)
        period.paused_at = timezone.now()
        period.resumed_at = None  # Resetear para próxima reanudación
        period.save()

        return Response(
            {
                "period": period.period_number,
                "paused_at": period.paused_at,
                "elapsed_minutes": period.elapsed_minutes,
                "elapsed_seconds": period.elapsed_seconds,
            }
        )

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def resume_period(self, request, pk=None):
        """Reanudar el período pausado"""
        match = self.get_object()

        period = MatchPeriod.objects.filter(match=match, is_active=True).first()
        if not period or not period.paused_at:
            return Response(
                {"error": "No hay período pausado"}, status=status.HTTP_400_BAD_REQUEST
            )

        period.resumed_at = timezone.now()
        period.paused_at = None
        period.save()

        return Response(
            {
                "period": period.period_number,
                "resumed_at": period.resumed_at,
                "elapsed_minutes": period.elapsed_minutes,
            }
        )

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def end_period(self, request, pk=None):
        """Finalizar el período actual (ej: fin del 1T)"""
        match = self.get_object()

        period = MatchPeriod.objects.filter(match=match, is_active=True).first()
        if not period:
            return Response(
                {"error": "No hay período activo"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Calcular tiempo final
        reference = period.resumed_at or period.started_at
        if period.paused_at:
            reference = None  # Está pausado, no hay segmento actual

        if reference:
            current_segment = (timezone.now() - reference).total_seconds()
            period.elapsed_seconds_before_pause += int(current_segment)

        period.ended_at = timezone.now()
        period.is_active = False
        period.is_completed = True
        period.save()

        return Response(
            {
                "period": period.period_number,
                "ended_at": period.ended_at,
                "elapsed_minutes": period.elapsed_minutes,
                "elapsed_seconds": period.elapsed_seconds,
            }
        )

    @action(detail=True, methods=["get"], permission_classes=[AllowAny])
    def periods(self, request, pk=None):
        """Obtener todos los períodos del partido"""
        match = self.get_object()
        periods = match.periods.all()

        return Response(
            [
                {
                    "period_number": p.period_number,
                    "name": p.name,
                    "started_at": p.started_at,
                    "paused_at": p.paused_at,
                    "resumed_at": p.resumed_at,
                    "ended_at": p.ended_at,
                    "elapsed_minutes": p.elapsed_minutes,
                    "elapsed_seconds": p.elapsed_seconds,
                    "is_active": p.is_active,
                    "is_completed": p.is_completed,
                }
                for p in periods
            ]
        )


class AdvertisementBannerViewSet(viewsets.ModelViewSet):
    """
    ViewSet para Banners Publicitarios
    - LIST / RETRIEVE: Público (sin autenticación)
    - CREATE / UPDATE / DELETE: Requiere autenticación + ser miembro de organización
    """

    queryset = AdvertisementBanner.objects.all()
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["title", "description"]
    ordering_fields = ["display_order", "created_at", "start_date"]
    ordering = ["position", "display_order"]

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return AdvertisementBannerCreateUpdateSerializer
        return AdvertisementBannerSerializer

    def get_permissions(self):
        # Todas las operaciones de lectura son públicas
        if self.action in ["list", "retrieve", "by_position", "active", "track_click"]:
            return [AllowAny()]
        # Crear, editar, eliminar requieren autenticación
        return [IsAuthenticated(), IsOrganizationMember()]

    def get_queryset(self):
        queryset = AdvertisementBanner.objects.all()

        # Filtro por posición
        position = self.request.query_params.get("position")
        if position:
            queryset = queryset.filter(position=position)

        tournament_id = self.request.query_params.get("tournament")
        if tournament_id:
            queryset = queryset.filter(tournament_id=tournament_id)
        # Filtro por activo/inactivo (solo admins ven inactivos)
        active_only = self.request.query_params.get("active")
        if active_only == "true":
            today = timezone.now().date()
            queryset = queryset.filter(
                is_active=True,
                start_date__lte=today,
            ).filter(Q(end_date__isnull=True) | Q(end_date__gte=today))

        # Filtro por fecha
        date_from = self.request.query_params.get("from")
        date_to = self.request.query_params.get("to")
        if date_from:
            queryset = queryset.filter(start_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(end_date__lte=date_to)

        return queryset

    def perform_create(self, serializer):
        serializer.save(posted_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        banner_title = instance.title
        self.perform_destroy(instance)
        return Response(
            {"message": f"Banner '{banner_title}' eliminado correctamente."},
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"], permission_classes=[AllowAny])
    def by_position(self, request):
        position = request.query_params.get("position")
        tournament_id = request.query_params.get("tournament")  # ← NUEVO

        if not position:
            return Response(
                {"error": "El parámetro 'position' es requerido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        today = timezone.now().date()
        banners = AdvertisementBanner.objects.filter(
            position=position,
            is_active=True,
            start_date__lte=today,
        ).filter(Q(end_date__isnull=True) | Q(end_date__gte=today))

        # Filtrar por torneo si se proporciona
        if tournament_id:
            banners = banners.filter(tournament_id=tournament_id)

        banners = banners.order_by("display_order")

        # Incrementar impresiones
        banner_ids = list(banners.values_list("id", flat=True))
        AdvertisementBanner.objects.filter(id__in=banner_ids).update(
            impressions=F("impressions") + 1
        )

        serializer = AdvertisementBannerSerializer(banners, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], permission_classes=[AllowAny])
    def active(self, request):
        """
        Obtener SOLO banners activos y visibles actualmente
        GET /api/v1/sports/banners/active/
        """
        today = timezone.now().date()
        banners = (
            AdvertisementBanner.objects.filter(
                is_active=True,
                start_date__lte=today,
            )
            .filter(Q(end_date__isnull=True) | Q(end_date__gte=today))
            .order_by("position", "display_order")
        )

        serializer = AdvertisementBannerSerializer(banners, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], permission_classes=[AllowAny])
    def track_click(self, request, pk=None):
        """
        Registrar un click en el banner
        POST /api/v1/sports/banners/{id}/track_click/
        """
        banner = self.get_object()
        banner.clicks += 1
        banner.save(update_fields=["clicks"])
        return Response(
            {
                "message": "Click registrado",
                "banner_id": str(banner.id),
                "total_clicks": banner.clicks,
            }
        )

    @action(detail=False, methods=["get"], permission_classes=[AllowAny])
    def positions(self, request):
        """
        Listar las posiciones disponibles para banners
        GET /api/v1/sports/banners/positions/
        """
        return Response(
            [
                {"value": value, "label": label}
                for value, label in AdvertisementBanner.POSITION_CHOICES
            ]
        )
