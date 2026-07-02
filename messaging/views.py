from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.permissions import IsOrganizationMember
from authentication.models import User

from .models import Conversation, ConversationParticipant, Message
from .permissions import IsConversationParticipant, IsMessageSender
from .serializers import (
    ConversationListSerializer,
    ConversationDetailSerializer,
    ConversationCreateSerializer,
    MessageSerializer,
    MessageCreateSerializer,
    MessageUpdateSerializer,
)
from .services import (
    create_real_estate_conversation,
    get_or_create_conversation,
    get_user_unread_total,
    mark_conversation_as_read,
    send_message,
    user_can_access_conversation,
)


class ConversationViewSet(viewsets.ModelViewSet):
    """
    API de conversaciones.

    GET    /messaging/conversations/           — listar conversaciones del usuario
    POST   /messaging/conversations/           — crear conversación
    GET    /messaging/conversations/{id}/      — detalle
    GET    /messaging/conversations/{id}/messages/ — mensajes paginados
    POST   /messaging/conversations/{id}/send/   — enviar mensaje
    POST   /messaging/conversations/{id}/mark_read/ — marcar como leído
    GET    /messaging/conversations/unread_count/ — total no leídos
    POST   /messaging/conversations/start_real_estate/ — iniciar chat inmobiliario
    """

    permission_classes = [IsAuthenticated, IsOrganizationMember]
    lookup_field = "pk"
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        participant_conv_ids = ConversationParticipant.objects.filter(
            user=user,
        ).values_list("conversation_id", flat=True)

        return (
            Conversation.objects.filter(
                id__in=participant_conv_ids,
                is_active=True,
            )
            .select_related("content_type", "organization")
            .prefetch_related("participants__user")
        )

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ConversationDetailSerializer
        if self.action == "create":
            return ConversationCreateSerializer
        return ConversationListSerializer

    def get_permissions(self):
        if self.action in ["retrieve", "messages", "send", "mark_read"]:
            return [IsAuthenticated(), IsOrganizationMember(), IsConversationParticipant()]
        return [IsAuthenticated(), IsOrganizationMember()]

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        conv_type = request.query_params.get("type")
        if conv_type:
            queryset = queryset.filter(conversation_type=conv_type)

        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page or queryset, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = ConversationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        participant_ids = set(data["participant_ids"])
        participant_ids.add(request.user.id)
        participants = list(
            User.objects.filter(
                id__in=participant_ids,
                organization=request.user.organization,
            )
        )
        if len(participants) < 2:
            return Response(
                {"error": "Se requieren al menos 2 participantes válidos."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        content_object = None
        if data.get("content_type_model") and data.get("object_id"):
            ct = ContentType.objects.get(model=data["content_type_model"].lower())
            model_class = ct.model_class()
            content_object = model_class.objects.get(pk=data["object_id"])

        conversation, created = get_or_create_conversation(
            organization=request.user.organization,
            participants=participants,
            content_object=content_object,
            conversation_type=data.get("conversation_type", "general"),
            subject=data.get("subject", ""),
            initiated_by=request.user,
        )

        initial_message = data.get("initial_message", "").strip()
        if initial_message and created:
            send_message(
                conversation=conversation,
                sender=request.user,
                body=initial_message,
            )

        out = ConversationDetailSerializer(conversation, context={"request": request})
        return Response(
            out.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get"])
    def messages(self, request, pk=None):
        """Obtener mensajes de una conversación (paginados, más recientes primero)."""
        conversation = self.get_object()
        queryset = conversation.messages.filter(is_deleted=False).select_related("sender")

        before = request.query_params.get("before")
        if before:
            queryset = queryset.filter(created_at__lt=before)

        page = self.paginate_queryset(queryset.order_by("-created_at"))
        messages = list(reversed(page)) if page else list(queryset.order_by("-created_at")[:20])
        messages = list(reversed(messages)) if page else messages

        serializer = MessageSerializer(messages, many=True, context={"request": request})
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        """Enviar un mensaje a la conversación."""
        conversation = self.get_object()
        serializer = MessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            message = send_message(
                conversation=conversation,
                sender=request.user,
                body=serializer.validated_data["body"],
            )
        except (PermissionError, ValueError) as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        out = MessageSerializer(message, context={"request": request})
        return Response(out.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def mark_read(self, request, pk=None):
        """Marcar conversación como leída."""
        conversation = self.get_object()
        mark_conversation_as_read(conversation, request.user)
        return Response({"success": True, "read_at": timezone.now().isoformat()})

    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        """Contador total de mensajes no leídos."""
        total = get_user_unread_total(request.user)
        return Response({"unread_count": total})

    @action(detail=False, methods=["post"], url_path="start-real-estate")
    def start_real_estate(self, request):
        """Iniciar conversación sobre una propiedad inmobiliaria."""
        from real_estate.models import RealEstateOffer

        offer_id = request.data.get("offer_id")
        initial_message = request.data.get("initial_message", "").strip()

        if not offer_id:
            return Response({"error": "offer_id es requerido."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            offer = RealEstateOffer.objects.get(
                pk=offer_id,
                organization=request.user.organization,
            )
        except RealEstateOffer.DoesNotExist:
            return Response({"error": "Propiedad no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        if offer.posted_by_id == request.user.id:
            return Response(
                {"error": "No puedes contactarte contigo mismo."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        conversation, created = create_real_estate_conversation(
            offer=offer,
            interested_user=request.user,
        )

        if initial_message:
            send_message(
                conversation=conversation,
                sender=request.user,
                body=initial_message,
            )

        out = ConversationDetailSerializer(conversation, context={"request": request})
        return Response(
            out.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"], url_path="by-application/(?P<application_id>[0-9a-f-]+)")
    def by_application(self, request, application_id=None):
        """Obtener conversación vinculada a una postulación laboral."""
        from jobs.models import JobApplication

        try:
            application = JobApplication.objects.select_related("offer").get(pk=application_id)
        except JobApplication.DoesNotExist:
            return Response({"error": "Postulación no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        is_applicant = application.applicant_id == request.user.id
        is_recruiter = (
            request.user.role == "manager"
            and application.offer.posted_by_id == request.user.id
        )
        if not is_applicant and not is_recruiter and not request.user.is_superuser:
            return Response({"error": "Sin permiso."}, status=status.HTTP_403_FORBIDDEN)

        ct = ContentType.objects.get_for_model(application)
        conversation = Conversation.objects.filter(
            content_type=ct,
            object_id=application.id,
        ).first()

        if not conversation:
            return Response({"error": "Conversación no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        out = ConversationDetailSerializer(conversation, context={"request": request})
        return Response(out.data)


class MessageViewSet(viewsets.GenericViewSet):
    """Operaciones sobre mensajes individuales (editar/eliminar)."""

    permission_classes = [IsAuthenticated, IsOrganizationMember]
    queryset = Message.objects.filter(is_deleted=False).select_related("sender", "conversation")
    serializer_class = MessageSerializer
    lookup_field = "pk"

    def get_permissions(self):
        if self.action in ["update", "partial_update", "destroy"]:
            return [IsAuthenticated(), IsOrganizationMember(), IsMessageSender()]
        return super().get_permissions()

    def partial_update(self, request, pk=None):
        message = self.get_object()
        if not user_can_access_conversation(request.user, message.conversation):
            return Response({"error": "Sin permiso."}, status=status.HTTP_403_FORBIDDEN)

        serializer = MessageUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        from .services import sanitize_message_body

        try:
            message.body = sanitize_message_body(serializer.validated_data["body"])
            message.is_edited = True
            message.edited_at = timezone.now()
            message.save(update_fields=["body", "is_edited", "edited_at", "updated_at"])
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        out = MessageSerializer(message, context={"request": request})
        return Response(out.data)

    def destroy(self, request, pk=None):
        message = self.get_object()
        if not user_can_access_conversation(request.user, message.conversation):
            return Response({"error": "Sin permiso."}, status=status.HTTP_403_FORBIDDEN)

        message.is_deleted = True
        message.save(update_fields=["is_deleted", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)
