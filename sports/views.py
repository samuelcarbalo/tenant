from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.db.models import Q, Count, Prefetch
from django.utils import timezone

from .models import Tournament, Team, Player, Match, MatchEvent
from .serializers import (
    TournamentListSerializer,
    TournamentDetailSerializer,
    TeamListSerializer,
    TeamDetailSerializer,
    PlayerListSerializer,
    PlayerDetailSerializer,
    MatchListSerializer,
    MatchDetailSerializer,
    MatchCreateUpdateSerializer,
    MatchEventSerializer,
    StandingsSerializer,
    TournamentCreateSerializer,
)
from core.permissions import IsOrganizationMember


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
        if self.action in ["list", "retrieve", "standings", "schedule"]:
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
            queryset = queryset.filter(status__in=["active", "finished"])

        return queryset.order_by("-start_date")

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
            queryset = (
                Tournament.objects.filter(posted_by=user.id)
                .select_related("organization")
                .annotate(
                    teams_count=Count("teams", distinct=True),
                    matches_count=Count("matches", distinct=True),
                )
                .order_by("-created_at")
            )

        # Aplicar paginación
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = TournamentListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = TournamentListSerializer(queryset, many=True)
        return Response(serializer.data)


class TeamViewSet(viewsets.ModelViewSet):
    """ViewSet para equipos"""

    queryset = Team.objects.all()

    def get_serializer_class(self):

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


class PlayerViewSet(viewsets.ModelViewSet):
    """ViewSet para jugadores"""

    queryset = Player.objects.all()

    def get_serializer_class(self):
        if self.action == "list":
            return PlayerListSerializer
        return PlayerDetailSerializer

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [AllowAny()]
        return [IsAuthenticated(), IsOrganizationMember()]

    def get_queryset(self):
        queryset = Player.objects.select_related("team", "tournament")

        # Filtros
        team_id = self.request.query_params.get("team")
        if team_id:
            queryset = queryset.filter(team_id=team_id)

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
        # Detectar si es una lista (bulk create) o un solo objeto
        is_many = isinstance(request.data, list)

        serializer = self.get_serializer(data=request.data, many=is_many)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )

    def perform_create(self, serializer):
        serializer.save()


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
        """Agregar evento al partido (gol, tarjeta, etc.)"""
        match = self.get_object()

        serializer = MatchEventSerializer(data=request.data)
        if serializer.is_valid():
            event = serializer.save(match=match)

            # Actualizar estadísticas del jugador si aplica
            if event.player:
                self._update_player_stats(event)

            return Response(
                MatchEventSerializer(event).data, status=status.HTTP_201_CREATED
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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
        match.save()
        return Response({"status": "Partido iniciado", "match_id": str(match.id)})

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def finish_match(self, request, pk=None):
        """Finalizar partido"""
        return self.update_score(request, pk)
