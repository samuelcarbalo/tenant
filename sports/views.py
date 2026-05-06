from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.db.models import Q, Count, Prefetch
from django.utils import timezone

from .models import Tournament, Team, Player, Match, MatchEvent, MatchLineup
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
        if self.action in ["list", "retrieve", "standings", "schedule", "teams"]:
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
        match.save()
        return Response({"status": "Partido iniciado", "match_id": str(match.id)})

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
        """
        Sustituir un jugador durante el partido
        POST /api/v1/sports/matches/{id}/substitute_player/

        Body:
        {
            "team": 3,
            "player_out": 17,
            "player_in": 23,
            "minute": 65
        }
        """
        match = self.get_object()
        team_id = request.data.get("team")
        player_out_id = request.data.get("player_out")
        player_in_id = request.data.get("player_in")
        minute = request.data.get("minute")

        # --- Validaciones ---
        if not all([team_id, player_out_id, player_in_id, minute]):
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

        # Validar que player_out está en el lineup como titular o ya entró
        lineup_out = MatchLineup.objects.filter(
            match=match,
            team_id=team_id,
            player_id=player_out_id,
        ).first()

        if not lineup_out:
            return Response(
                {
                    "error": "El jugador que sale no está en la alineación de este partido"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validar que player_in está en el lineup como suplente
        lineup_in = MatchLineup.objects.filter(
            match=match,
            team_id=team_id,
            player_id=player_in_id,
        ).first()

        # Si no está en el lineup pero pertenece al equipo, lo agregamos como suplente
        if not lineup_in:
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
                is_on_field=False,
                posted_by=request.user,
            )

        if lineup_in.is_starter and lineup_in.is_on_field:
            return Response(
                {"error": "Este jugador ya está jugando como titular"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validar que player_in no haya entrado ya
        already_subbed_in = MatchEvent.objects.filter(
            match=match, player_id=player_in_id, event_type="substitution_in"
        ).exists()

        if already_subbed_in:
            return Response(
                {"error": "Este jugador ya entró como sustituto anteriormente"},
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

        # 2. Actualizar lineup: marcar al que sale, activar al que entra
        lineup_out.is_on_field = False
        lineup_out.substitution_minute = minute
        lineup_out.save()

        # El que entra: sigue siendo is_starter=False (era suplente) pero ahora está en cancha
        lineup_in.is_on_field = True
        lineup_in.substitution_minute = minute
        lineup_in.save()

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
