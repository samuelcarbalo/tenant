from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.exceptions import ValidationError
from django.db.models import Q, Count, Prefetch, F
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.db import transaction
from authentication.models import User
from profiles.models import Profile
from .services.suspensions import (
    create_player_suspension,
    is_player_suspended_for_match,
    process_suspensions_on_match_finish,
)
from .models import (
    Tournament,
    TournamentPhase,
    CompetitionGroup,
    GroupMembership,
    Team,
    Player,
    Match,
    MatchEvent,
    MatchLineup,
    MatchPeriod,
    MatchInning,
    AdvertisementBanner,
    PlayerSuspension,
)
from .serializers import (
    TournamentListSerializer,
    TournamentDetailSerializer,
    TeamListSerializer,
    TeamDetailSerializer,
    TeamCreateUpdateSerializer,
    PlayerListSerializer,
    PlayerDetailSerializer,
    PlayerCreateUpdateSerializer,
    MatchListSerializer,
    MatchDetailSerializer,
    MatchCreateUpdateSerializer,
    MatchEventSerializer,
    StandingsSerializer,
    TournamentCreateSerializer,
    MatchLineupSerializer,
    MatchLineupCreateSerializer,
    MatchLineupBulkCreateSerializer,
    AdvertisementBannerCreateUpdateSerializer,
    AdvertisementBannerSerializer,
    TournamentStructureSerializer,
    TournamentPhaseSerializer,
    CompetitionGroupSerializer,
    AssignTeamsToGroupSerializer,
    GenerateFixtureSerializer,
    AdvancePhaseSerializer,
    PlayerSuspensionSerializer,
)
from .scoring import MatchResultService, StandingsService, get_scoring_config
from .formats.templates import list_templates
from .services.structure import (
    apply_format_template,
    assign_teams_to_group,
    generate_round_robin_fixtures,
)
from .services.advancement import advance_phase as run_advance_phase, SourceResolutionError
from sports.models import BracketNode
from core.permissions import IsOrganizationMember, IsCoachOfTeam, resolve_request_organization, user_can_manage_content, user_is_platform_elevated


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
            "structure",
            "format_templates",
            "bracket",
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
            queryset = queryset.filter(moderation_status="approved")

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
        from django.db import transaction

        user = self.request.user
        format_template = serializer.validated_data.pop("format_template", "") or self.request.data.get("format_template", "")
        format_group_count = serializer.validated_data.pop("format_group_count", 1)

        with transaction.atomic():
            fresh_user = User.objects.select_for_update().get(id=user.id)
            from authentication.credits import charge_credits

            user.credits = charge_credits(
                fresh_user,
                50,
                "No tienes suficientes créditos para crear un torneo. "
                f"Crear un torneo cuesta 50 créditos y actualmente tienes {fresh_user.credits} créditos.",
            )

            org = resolve_request_organization(self.request)
            if not org:
                raise ValidationError(
                    {"detail": "No se pudo resolver la organización (cabecera X-Tenant)."}
                )

            tournament = serializer.save(
                posted_by=user,
                organization=org,
            )

            if format_template and format_template not in ("", "legacy_league"):
                apply_format_template(
                    tournament,
                    format_template,
                    group_count=max(1, int(format_group_count or 1)),
                )

    @action(detail=True, methods=["get"], permission_classes=[AllowAny])
    def standings(self, request, slug=None):
        """Tabla de posiciones del torneo (global, por fase o por grupo)."""
        tournament = self.get_object()
        phase = group = None

        phase_slug = request.query_params.get("phase")
        group_slug = request.query_params.get("group")
        phase_id = request.query_params.get("phase_id")
        group_id = request.query_params.get("group_id")

        if phase_id:
            phase = tournament.phases.filter(id=phase_id).first()
        elif phase_slug:
            phase = tournament.phases.filter(slug=phase_slug).first()

        if group_id:
            group = CompetitionGroup.objects.filter(
                id=group_id, phase__tournament=tournament
            ).first()
        elif group_slug:
            group = CompetitionGroup.objects.filter(
                slug=group_slug, phase__tournament=tournament
            ).first()

        standings = StandingsService.compute(tournament, phase=phase, group=group)
        serializer = StandingsSerializer(standings, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], permission_classes=[AllowAny])
    def format_templates(self, request):
        """Plantillas de formato disponibles."""
        sport_type = request.query_params.get("sport_type")
        return Response(list_templates(sport_type))

    @action(detail=True, methods=["get"], permission_classes=[AllowAny])
    def structure(self, request, slug=None):
        """Estructura completa del torneo (fases y grupos)."""
        tournament = self.get_object()
        phases = (
            tournament.phases.prefetch_related(
                Prefetch(
                    "groups",
                    queryset=CompetitionGroup.objects.prefetch_related(
                        Prefetch(
                            "memberships",
                            queryset=GroupMembership.objects.select_related("team"),
                        )
                    ),
                ),
                Prefetch(
                    "bracket__nodes",
                    queryset=BracketNode.objects.select_related(
                        "match",
                        "match__home_team",
                        "match__away_team",
                    ).order_by("round", "position"),
                ),
            )
            .all()
            .order_by("order")
        )
        data = {
            "structure_mode": tournament.structure_mode,
            "format_template": tournament.format_template,
            "phases": TournamentPhaseSerializer(phases, many=True).data,
        }
        return Response(data)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def assign_group_teams(self, request, slug=None):
        """Asigna equipos a un grupo/cuadrangular."""
        tournament = self.get_object()
        serializer = AssignTeamsToGroupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        group = CompetitionGroup.objects.filter(
            id=serializer.validated_data["group_id"],
            phase__tournament=tournament,
        ).first()
        if not group:
            return Response({"error": "Grupo no encontrado"}, status=status.HTTP_404_NOT_FOUND)

        team_ids = serializer.validated_data["team_ids"]
        invalid = Team.objects.filter(id__in=team_ids).exclude(tournament=tournament)
        if invalid.exists():
            return Response(
                {"error": "Todos los equipos deben pertenecer al torneo"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(team_ids) > group.max_teams:
            return Response(
                {"error": f"Máximo {group.max_teams} equipos en este grupo"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        assign_teams_to_group(group, team_ids)
        return Response(CompetitionGroupSerializer(group).data)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def generate_fixture(self, request, slug=None):
        """Genera fixture round-robin para una fase/grupo."""
        tournament = self.get_object()
        serializer = GenerateFixtureSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        phase = tournament.phases.filter(id=data["phase_id"]).first()
        if not phase:
            return Response({"error": "Fase no encontrada"}, status=status.HTTP_404_NOT_FOUND)

        group = None
        if data.get("group_id"):
            group = phase.groups.filter(id=data["group_id"]).first()
            if not group:
                return Response({"error": "Grupo no encontrado"}, status=status.HTTP_404_NOT_FOUND)

        try:
            if group or not phase.groups.exists():
                matches = generate_round_robin_fixtures(
                    tournament=tournament,
                    phase=phase,
                    group=group,
                    posted_by=request.user,
                    match_date=data["match_date"],
                    venue=data.get("venue", ""),
                )
            else:
                matches = []
                for grp in phase.groups.all():
                    matches.extend(
                        generate_round_robin_fixtures(
                            tournament=tournament,
                            phase=phase,
                            group=grp,
                            posted_by=request.user,
                            match_date=data["match_date"],
                            venue=data.get("venue", ""),
                        )
                    )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "created_count": len(matches),
                "matches": MatchListSerializer(matches, many=True).data,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def advance_phase(self, request, slug=None):
        """Cierra una fase y genera partidos de la siguiente (eliminatoria)."""
        tournament = self.get_object()
        serializer = AdvancePhaseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            result = run_advance_phase(
                tournament=tournament,
                from_phase_slug=data["from_phase"],
                posted_by=request.user,
                match_date=data.get("match_date"),
                venue=data.get("venue", ""),
            )
        except SourceResolutionError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "from_phase": TournamentPhaseSerializer(result["from_phase"]).data,
                "next_phase": TournamentPhaseSerializer(result["next_phase"]).data,
                "matches_created": MatchListSerializer(
                    result["matches_created"], many=True
                ).data,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get"], permission_classes=[AllowAny])
    def bracket(self, request, slug=None):
        """Bracket de una fase eliminatoria."""
        tournament = self.get_object()
        phase_slug = request.query_params.get("phase")
        if not phase_slug:
            return Response(
                {"error": "Parámetro phase requerido"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        phase = tournament.phases.filter(slug=phase_slug, phase_type="knockout").first()
        if not phase or not hasattr(phase, "bracket"):
            return Response(
                {"error": "Fase eliminatoria no encontrada"},
                status=status.HTTP_404_NOT_FOUND,
            )

        from .serializers import BracketSerializer

        from_phase = (
            tournament.phases.filter(order__lt=phase.order).order_by("-order").first()
        )
        return Response(
            BracketSerializer(
                phase.bracket,
                context={"from_phase": from_phase},
            ).data
        )

    @action(detail=True, methods=["get"])
    def schedule(self, request, slug=None):
        """Calendario de partidos del torneo"""
        tournament = self.get_object()
        matches = (
            Match.objects.filter(tournament=tournament)
            .select_related("home_team", "away_team", "phase", "group")
            .order_by("match_date")
        )

        status_param = request.query_params.get("status")
        if status_param:
            matches = matches.filter(status=status_param)

        team_id = request.query_params.get("team")
        if team_id:
            matches = matches.filter(Q(home_team_id=team_id) | Q(away_team_id=team_id))

        phase_param = request.query_params.get("phase")
        group_param = request.query_params.get("group")
        if phase_param:
            matches = matches.filter(phase__slug=phase_param)
        if group_param:
            matches = matches.filter(group__slug=group_param)

        serializer = MatchListSerializer(matches, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def my_tournaments(self, request):
        """
        Endpoint: /api/v1/sports/tournaments/my_tournaments/
        Solo para admins: ve todos los torneos (activos e inactivos) de su organización.
        """
        user = request.user

        if not user_can_manage_content(user):
            print(f"DEBUG: User {user} is not an admin")
            print(f"DEBUG: User role is {user.role}")
            return Response(
                {
                    "error": "No tienes permisos de administrador para ver esta información."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        queryset = self.get_queryset()
        if not user_is_platform_elevated(user):
            queryset = queryset.filter(posted_by=user)
        else:
            # Plataforma: ver todos, o filtrar por los propios si se pide
            mine = request.query_params.get("mine", "false")
            if mine.lower() == "true":
                queryset = queryset.filter(posted_by=user)

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
        top_average = None
        top_hits = None
        top_home_runs = None
        top_rbis = None
        top_runs = None
        if tournament.sport_type == "softball":
            top_average = players.filter(at_bats__gte=3).order_by(
                "-batting_average", "-hits"
            )[:10]
            top_hits = players.filter(hits__gt=0).order_by("-hits")[:10]
            top_home_runs = players.filter(home_runs__gt=0).order_by("-home_runs")[:10]
            top_rbis = players.filter(rbis__gt=0).order_by("-rbis")[:10]
            top_runs = players.filter(runs_scored__gt=0).order_by("-runs_scored")[:10]

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
                    "top_average": serialize_players(top_average, "batting_average"),
                    "top_hits": serialize_players(top_hits, "hits"),
                    "top_home_runs": serialize_players(top_home_runs, "home_runs"),
                    "top_rbis": serialize_players(top_rbis, "rbis"),
                    "top_runs": serialize_players(top_runs, "runs_scored"),
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
        """Asignar posted_by desde el usuario autenticado y crear usuario automático."""
        team = serializer.validated_data.get("team")
        tournament = serializer.validated_data.get("tournament")
        if not tournament and team:
            tournament = team.tournament

        organization = None
        if self.request.user.organization:
            organization = self.request.user.organization
        elif tournament:
            organization = tournament.organization

        email = (serializer.validated_data.get("email") or "").strip()
        id_number = (serializer.validated_data.get("id_number") or "").strip()
        linked_user = None
        if organization and email:
            username = email.split("@", 1)[0]
            existing_user = User.objects.filter(email__iexact=email, organization=organization).first()
            if existing_user:
                existing_user.first_name = serializer.validated_data.get("first_name") or existing_user.first_name
                existing_user.last_name = serializer.validated_data.get("last_name") or existing_user.last_name
                existing_user.username = username
                existing_user.role = "user"
                existing_user.is_active = True
                if id_number:
                    existing_user.set_password(id_number)
                existing_user.save()
                linked_user = existing_user
            else:
                linked_user = User.objects.create_user(
                    email=email,
                    username=username,
                    password=id_number,
                    organization=organization,
                    first_name=serializer.validated_data.get("first_name", ""),
                    last_name=serializer.validated_data.get("last_name", ""),
                    role="user",
                    is_active=True,
                )
            Profile.objects.get_or_create(
                user=linked_user,
                organization=organization,
                defaults={"dynamic_data": {}},
            )

        serializer.save(
            posted_by=self.request.user,
            tournament=tournament,
            user=linked_user,
        )

    @property
    def tournament_slug(self):
        """Obtiene el slug del torneo automáticamente"""
        return self.tournament.slug if self.tournament else None


class PlayerSuspensionViewSet(viewsets.ModelViewSet):
    """Gestión de suspensiones de jugadores."""

    queryset = PlayerSuspension.objects.select_related(
        "player", "tournament", "created_by", "revoked_by"
    )
    serializer_class = PlayerSuspensionSerializer

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_queryset(self):
        queryset = self.queryset
        tournament_id = self.request.query_params.get("tournament")
        if tournament_id:
            queryset = queryset.filter(tournament_id=tournament_id)
        player_id = self.request.query_params.get("player")
        if player_id:
            queryset = queryset.filter(player_id=player_id)
        if self.request.user.is_authenticated and not self.request.user.is_superuser and self.request.user.role not in {"admin", "manager"}:
            queryset = queryset.filter(tournament__organization=self.request.user.organization)
        return queryset.order_by("-created_at")

    def _can_manage(self, request):
        return request.user.is_superuser or request.user.role in {"admin", "manager"}

    def create(self, request, *args, **kwargs):
        if not self._can_manage(request):
            return Response({"detail": "No tienes permiso para gestionar suspensiones."}, status=status.HTTP_403_FORBIDDEN)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if not self._can_manage(request):
            return Response({"detail": "No tienes permiso para gestionar suspensiones."}, status=status.HTTP_403_FORBIDDEN)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        if not self._can_manage(request):
            return Response({"detail": "No tienes permiso para gestionar suspensiones."}, status=status.HTTP_403_FORBIDDEN)
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not self._can_manage(request):
            return Response({"detail": "No tienes permiso para gestionar suspensiones."}, status=status.HTTP_403_FORBIDDEN)
        return super().destroy(request, *args, **kwargs)

    def perform_create(self, serializer):
        suspension = serializer.save(created_by=self.request.user)
        if suspension.match_id and not suspension.suspended_until_match_id:
            from sports.services.suspensions import _team_matches_after_sanction

            next_match = _team_matches_after_sanction(suspension).first()
            if next_match:
                suspension.suspended_until_match = next_match
                suspension.save(update_fields=["suspended_until_match", "updated_at"])

    def perform_update(self, serializer):
        is_active = serializer.validated_data.get("is_active")
        if is_active is False:
            serializer.save(
                revoked_by=self.request.user,
                revoked_at=timezone.now(),
            )
        else:
            serializer.save(revoked_by=None, revoked_at=None)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def revoke(self, request, pk=None):
        """Revoca una suspensión activa (automática o manual)."""
        if not self._can_manage(request):
            return Response(
                {"detail": "No tienes permiso para gestionar suspensiones."},
                status=status.HTTP_403_FORBIDDEN,
            )
        suspension = self.get_object()
        suspension.is_active = False
        suspension.revoked_by = request.user
        suspension.revoked_at = timezone.now()
        suspension.save(update_fields=["is_active", "revoked_by", "revoked_at", "updated_at"])
        return Response(PlayerSuspensionSerializer(suspension).data)


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

    def _direction_params(self):
        """Parámetros de búsqueda asistida por cercanía de fecha."""
        direction = (self.request.query_params.get("direction") or "").strip().lower()
        if direction not in {"upcoming", "past"}:
            return None

        raw_from = (
            self.request.query_params.get("from_date")
            or self.request.query_params.get("from")
        )
        if not raw_from:
            raise ValidationError(
                {"from_date": "Requerido cuando se usa direction=upcoming|past."}
            )

        from_date = parse_date(raw_from)
        if from_date is None:
            raise ValidationError(
                {"from_date": "Formato inválido. Use YYYY-MM-DD."}
            )

        try:
            limit = int(self.request.query_params.get("limit", 5))
        except (TypeError, ValueError):
            limit = 5
        limit = max(1, min(limit, 50))

        try:
            offset = int(self.request.query_params.get("offset", 0))
        except (TypeError, ValueError):
            offset = 0
        offset = max(0, offset)

        return {
            "direction": direction,
            "from_date": from_date,
            "limit": limit,
            "offset": offset,
        }

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

        # Búsqueda asistida: partidos cercanos a from_date (solo list)
        if self.action == "list":
            direction_params = self._direction_params()
            if direction_params:
                from_date = direction_params["from_date"]
                if direction_params["direction"] == "upcoming":
                    # Próximos a partir del día seleccionado (excluye el día vacío)
                    queryset = queryset.filter(match_date__date__gt=from_date).order_by(
                        "match_date"
                    )
                else:
                    # Más recientes anteriores al día seleccionado
                    queryset = queryset.filter(match_date__date__lt=from_date).order_by(
                        "-match_date"
                    )
                return queryset

        # Fecha (rango clásico from/to)
        date_from = self.request.query_params.get("from")
        date_to = self.request.query_params.get("to")
        if date_from:
            queryset = queryset.filter(match_date__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(match_date__date__lte=date_to)

        # Filtro por fase/grupo
        phase_param = self.request.query_params.get("phase")
        group_param = self.request.query_params.get("group")
        if phase_param:
            queryset = queryset.filter(phase__slug=phase_param)
        if group_param:
            queryset = queryset.filter(group__slug=group_param)

        return queryset.order_by("match_date")

    def paginate_queryset(self, queryset):
        if self.action == "list":
            direction_params = self._direction_params()
            if direction_params:
                limit = direction_params["limit"]
                offset = direction_params["offset"]
                self._nearby_meta = {
                    "count": queryset.count(),
                    "limit": limit,
                    "offset": offset,
                    "direction": direction_params["direction"],
                    "from_date": direction_params["from_date"].isoformat(),
                }
                return list(queryset[offset : offset + limit])
        return super().paginate_queryset(queryset)

    def get_paginated_response(self, data):
        meta = getattr(self, "_nearby_meta", None)
        if meta is not None:
            count = meta["count"]
            limit = meta["limit"]
            offset = meta["offset"]
            has_more = offset + limit < count
            has_prev = offset > 0
            next_offset = offset + limit if has_more else None
            prev_offset = max(0, offset - limit) if has_prev else None
            return Response(
                {
                    "count": count,
                    "limit": limit,
                    "offset": offset,
                    "direction": meta["direction"],
                    "from_date": meta["from_date"],
                    "has_more": has_more,
                    "next": (
                        f"?direction={meta['direction']}"
                        f"&from_date={meta['from_date']}"
                        f"&limit={limit}&offset={next_offset}"
                        if next_offset is not None
                        else None
                    ),
                    "previous": (
                        f"?direction={meta['direction']}"
                        f"&from_date={meta['from_date']}"
                        f"&limit={limit}&offset={prev_offset}"
                        if prev_offset is not None
                        else None
                    ),
                    "links": {
                        "next": (
                            f"?direction={meta['direction']}"
                            f"&from_date={meta['from_date']}"
                            f"&limit={limit}&offset={next_offset}"
                            if next_offset is not None
                            else None
                        ),
                        "previous": (
                            f"?direction={meta['direction']}"
                            f"&from_date={meta['from_date']}"
                            f"&limit={limit}&offset={prev_offset}"
                            if prev_offset is not None
                            else None
                        ),
                    },
                    "results": data,
                }
            )
        return super().get_paginated_response(data)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def update_score(self, request, pk=None):
        """Actualizar marcador del partido"""
        match = self.get_object()

        if (
            not request.user.is_superuser
            and request.user.organization != match.tournament.organization
        ):
            return Response(
                {"error": "No tienes permiso para editar este partido"},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            score_data = MatchResultService.normalize_scores_from_request(
                match, request.data
            )
            match.status = "finished"
            match.finished_at = timezone.now()
            match.save(update_fields=["status", "finished_at"])
            MatchResultService.finalize_match(match, score_data)
            process_suspensions_on_match_finish(match)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        serializer = MatchDetailSerializer(match)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def add_event(self, request, pk=None):
        match = self.get_object()
        serializer = MatchEventSerializer(data=request.data)
        if serializer.is_valid():
            player = serializer.validated_data.get("player")
            if player:
                suspended, suspension = is_player_suspended_for_match(player, match)
                if suspended:
                    return Response(
                        {
                            "error": (
                                f"El jugador está suspendido y no puede participar en este partido "
                                f"({suspension.get_reason_display() if suspension else 'sanción activa'})."
                            )
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            event = serializer.save(match=match, posted_by=request.user)
            self._handle_player_card_event(event)
            if event.player and event.event_type not in {"yellow_card", "red_card"}:
                self._update_player_stats(event)
            self._update_score_from_event(event)
            return Response(
                MatchEventSerializer(event).data, status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def _handle_player_card_event(self, event):
        """Convierte la segunda amarilla del mismo partido en roja y crea suspensión."""
        if not event.player or event.event_type not in {"yellow_card", "red_card"}:
            return

        if event.event_type == "yellow_card":
            previous_yellows = MatchEvent.objects.filter(
                match=event.match,
                player=event.player,
                event_type="yellow_card",
            ).exclude(id=event.id)
            if previous_yellows.exists():
                event.event_type = "red_card"
                event.description = f"{event.description or ''} Roja automática por doble amarilla".strip()
                event.save(update_fields=["event_type", "description"])
                self._create_player_suspension(
                    player=event.player,
                    match=event.match,
                    reason="double_yellow",
                    notes="Sanción automática por doble amarilla en el mismo partido.",
                    created_by=event.posted_by,
                )
                self._update_player_stats(event)
                return

            self._update_player_stats(event)
            return

        if event.event_type == "red_card":
            self._create_player_suspension(
                player=event.player,
                match=event.match,
                reason="direct_red",
                notes="Sanción automática por tarjeta roja directa.",
                created_by=event.posted_by,
            )
            self._update_player_stats(event)

    def _create_player_suspension(self, player, match, reason, notes, created_by, matches_count=1):
        return create_player_suspension(
            player=player,
            match=match,
            reason=reason,
            notes=notes,
            created_by=created_by,
            matches_count=matches_count,
        )

    def _update_score_from_event(self, event):
        """Actualizar marcador automáticamente según el evento (solo fútbol).

        En softbol el marcador proviene del line score por entradas
        (record_inning); los eventos son solo para el box score.
        """
        match = event.match
        if match.tournament.sport_type == "softball":
            return
        if event.event_type != "goal":
            return

        config = get_scoring_config(match.tournament)
        home_field, away_field = config["primary_fields"]

        if event.team == match.home_team:
            current = getattr(match, home_field) or 0
            setattr(match, home_field, current + 1)
        elif event.team == match.away_team:
            current = getattr(match, away_field) or 0
            setattr(match, away_field, current + 1)

        match.save(
            update_fields=["home_score", "away_score", "home_runs", "away_runs"]
        )

    def _update_player_stats(self, event):
        """Actualizar estadísticas del jugador según el deporte."""
        player = event.player
        sport = event.match.tournament.sport_type

        if sport == "softball":
            et = event.event_type
            if et in ("single", "double", "triple", "home_run"):
                player.hits += 1
                player.at_bats += 1
                if et == "home_run":
                    player.home_runs += 1
            elif et == "strikeout":
                player.strikes_out += 1
                player.at_bats += 1
            elif et == "out":
                player.at_bats += 1
            elif et == "walk":
                player.walks += 1
            elif et == "run":
                player.runs_scored += 1
            elif et == "rbi":
                player.rbis += max(1, event.rbi or 0)

            player.batting_average = (
                player.hits / player.at_bats if player.at_bats > 0 else 0.0
            )
            player.save()
            return

        # Fútbol y otros
        if event.event_type == "goal":
            player.goals += 1
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

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def record_inning(self, request, pk=None):
        """Registra/actualiza una media entrada (softbol) y evalúa fin de juego.

        Body: {number:int, half:"top"|"bottom", runs?:int, hits?:int,
               errors?:int, is_complete?:bool}
        """
        match = self.get_object()

        if (
            not request.user.is_superuser
            and request.user.organization != match.tournament.organization
        ):
            return Response(
                {"error": "No tienes permiso para editar este partido"},
                status=status.HTTP_403_FORBIDDEN,
            )

        if match.tournament.sport_type != "softball":
            return Response(
                {"error": "El marcador por entradas solo aplica a softbol."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            number = int(request.data.get("number"))
            half = request.data.get("half")
        except (TypeError, ValueError):
            return Response(
                {"error": "number y half son obligatorios."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if half not in ("top", "bottom") or number < 1:
            return Response(
                {"error": "Datos de entrada inválidos."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from sports.services.innings import upsert_inning, check_game_over

        if match.status == "scheduled":
            match.status = "live"
            if not match.started_at:
                match.started_at = timezone.now()
            match.save(update_fields=["status", "started_at"])

        upsert_inning(
            match,
            number,
            half,
            runs=request.data.get("runs"),
            hits=request.data.get("hits"),
            errors=request.data.get("errors"),
            is_complete=request.data.get("is_complete"),
        )

        game = check_game_over(match)
        auto_finished = False
        if game["over"] and request.data.get("finish", True):
            try:
                MatchResultService.finalize_match(
                    match, {"home_runs": match.home_runs, "away_runs": match.away_runs}
                )
                auto_finished = True
            except ValueError:
                auto_finished = False

        match.refresh_from_db()
        data = MatchDetailSerializer(match).data
        data["game_over"] = game
        data["auto_finished"] = auto_finished
        return Response(data)

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
        """
        match = self.get_object()
        team_id = request.data.get("team")
        players_data = request.data.get("players", [])

        if match.status not in ("scheduled",):
            return Response(
                {"error": "Solo puedes definir alineación antes de iniciar el partido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not Team.objects.filter(
            id=team_id, id__in=[match.home_team_id, match.away_team_id]
        ).exists():
            return Response(
                {"error": "El equipo no participa en este partido"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        bulk_serializer = MatchLineupBulkCreateSerializer(
            data={"team": team_id, "players": players_data},
            context={"match": match, "request": request},
        )
        if not bulk_serializer.is_valid():
            return Response(
                {"success": False, "error": bulk_serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        suspended_players = []
        for player_data in players_data:
            player_id = player_data.get("player")
            if not player_id:
                continue
            try:
                player = Player.objects.get(id=player_id)
            except Player.DoesNotExist:
                continue
            suspended, _ = is_player_suspended_for_match(player, match)
            if suspended and player_data.get("is_starter"):
                suspended_players.append(player.full_name)

        if suspended_players:
            return Response(
                {
                    "success": False,
                    "error": (
                        "Jugadores suspendidos no pueden ser titulares: "
                        + ", ".join(suspended_players)
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        MatchLineup.objects.filter(match=match, team_id=team_id).delete()

        created = []
        errors = []
        for player_data in players_data:
            data = {"match": match.id, "team": team_id, **player_data}
            serializer = MatchLineupCreateSerializer(data=data)
            if serializer.is_valid():
                lineup = serializer.save(posted_by=request.user)
                if lineup.is_starter:
                    if lineup.position == "designated_hitter":
                        lineup.is_on_field = False
                    else:
                        lineup.is_on_field = True
                    lineup.save(update_fields=["is_on_field"])
                else:
                    lineup.is_on_field = False
                    lineup.save(update_fields=["is_on_field"])
                created.append(MatchLineupSerializer(lineup).data)
            else:
                errors.append(
                    {"player": player_data.get("player"), "errors": serializer.errors}
                )

        if errors:
            return Response(
                {"success": False, "created": created, "errors": errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {"success": True, "created": created, "errors": []},
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

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        # Eliminar banners cuya fecha de fin ya expiró (cumplida la fecha de caducidad)
        try:
            today = timezone.now().date()
            AdvertisementBanner.objects.filter(end_date__lt=today).delete()
        except Exception:
            pass

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
        from django.conf import settings
        from rest_framework.exceptions import ValidationError

        if not settings.TOURNAMENT_OWNER_BANNERS_ENABLED:
            raise ValidationError(
                {
                    "detail": (
                        "La carga directa de banners por el organizador está desactivada. "
                        "Compra un patrocinio exclusivo del torneo con créditos."
                    )
                }
            )
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
    def config(self, request):
        from django.conf import settings

        return Response(
            {
                "owner_banners_enabled": settings.TOURNAMENT_OWNER_BANNERS_ENABLED,
            }
        )

    @action(detail=False, methods=["get"], permission_classes=[AllowAny])
    def by_position(self, request):
        from advertising.services import expire_stale_sponsorships, get_active_sponsorship
        from django.conf import settings

        position = request.query_params.get("position")
        tournament_id = request.query_params.get("tournament")

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

        if tournament_id:
            expire_stale_sponsorships()
            sponsorship = get_active_sponsorship(tournament_id)
            if sponsorship:
                banners = banners.filter(
                    sponsorship_id=sponsorship.id,
                    tournament_id=tournament_id,
                )
            elif settings.TOURNAMENT_OWNER_BANNERS_ENABLED:
                banners = banners.filter(
                    tournament_id=tournament_id,
                    sponsorship__isnull=True,
                )
            else:
                banners = banners.none()

        if not settings.TOURNAMENT_OWNER_BANNERS_ENABLED:
            banners = banners.exclude(
                sponsorship__isnull=True,
                campaign__isnull=True,
            )

        object_id = request.query_params.get("object_id")
        viewer_hash = request.query_params.get("viewer_hash")

        if object_id:
            banners = banners.filter(campaign__object_id=object_id)

        banners = banners.order_by("display_order")[:1]

        banner_list = list(banners)
        if banner_list:
            from advertising.services import record_campaign_impression

            banner = banner_list[0]
            if banner.campaign_id and viewer_hash:
                record_campaign_impression(banner.campaign, viewer_hash[:64])
            else:
                AdvertisementBanner.objects.filter(id=banner.id).update(
                    impressions=F("impressions") + 1
                )

        serializer = AdvertisementBannerSerializer(banner_list, many=True)
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

        from django.conf import settings

        if not settings.TOURNAMENT_OWNER_BANNERS_ENABLED:
            banners = banners.exclude(
                sponsorship__isnull=True,
                campaign__isnull=True,
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
