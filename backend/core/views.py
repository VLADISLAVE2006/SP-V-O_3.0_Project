import io
import uuid

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import IntegrityError, connection, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from PIL import Image
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from . import serializers as S
from .auth import PublicEndpointAuthentication, digest, issue_tokens, rotate_tokens
from .models import Comment, CommentLike, Poll, Report, Role, User, Warning
from .services import (
    Conflict,
    ban_user_locked,
    broadcast_after_commit,
    check_poll_access,
    current_poll,
    require_owner,
    require_results,
    require_role,
    require_user,
    response_answers,
    results,
    set_guest_cookie,
    sync_due_polls,
    update_poll_state,
    vote,
    warn_user,
)

PAGING = [OpenApiParameter("limit", int), OpenApiParameter("offset", int)]
POLL_FILTERS = PAGING + [
    OpenApiParameter("status", str),
    OpenApiParameter("sort", str),
    OpenApiParameter("q", str),
]


def validated(cls, request, *, partial=False, **context):
    serializer = cls(data=request.data, partial=partial, context={"request": request, **context})
    try:
        serializer.is_valid(raise_exception=True)
    except DjangoValidationError as exc:
        raise ValidationError({"password": exc.messages})
    return serializer.validated_data


def page(request, queryset, serializer, **context):
    class Pagination(serializers.Serializer):
        limit = serializers.IntegerField(min_value=1, max_value=100, default=20)
        offset = serializers.IntegerField(min_value=0, default=0)

    p = Pagination(data=request.query_params)
    p.is_valid(raise_exception=True)
    limit, offset = p.validated_data["limit"], p.validated_data["offset"]
    total = queryset.count()
    return Response(
        {
            "items": serializer(
                queryset[offset : offset + limit], many=True, context={"request": request, **context}
            ).data,
            "total": total,
            "has_more": offset + limit < total,
        }
    )


def poll_list(request, queryset):
    if "status" in request.query_params:
        value = request.query_params["status"]
        if value not in {"draft", "active", "finished"}:
            raise ValidationError({"status": "Неизвестный статус."})
        queryset = queryset.filter(status=value)
    if request.query_params.get("q"):
        queryset = queryset.filter(title__icontains=request.query_params["q"])
    sort = request.query_params.get("sort", "new")
    if sort not in {"new", "popular"}:
        raise ValidationError({"sort": "Допустимо new или popular."})
    return page(
        request,
        queryset.select_related("author").order_by(
            "-responses_count" if sort == "popular" else "-created_at", "-pk"
        ),
        S.PollSummarySerializer,
    )


class AuthenticatedView(APIView):
    permission_classes = [IsAuthenticated]


class HealthView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT, tags=["Служебное"])
    def get(self, request):
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return Response({"status": "ok"})


class RegisterView(APIView):
    authentication_classes = [PublicEndpointAuthentication]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    @extend_schema(
        auth=[], request=S.RegisterSerializer, responses={201: S.AuthResultSerializer}, tags=["Авторизация"]
    )
    def post(self, request):
        data = validated(S.RegisterSerializer, request)
        data.pop("password_confirm")
        try:
            with transaction.atomic():
                if User.objects.filter(
                    Q(email__iexact=data["email"]) | Q(nickname__iexact=data["nickname"])
                ).exists():
                    raise Conflict("Почта или никнейм уже заняты.")
                user = User.objects.create_user(**data)
                pair = issue_tokens(user)
        except IntegrityError:
            raise Conflict("Почта или никнейм уже заняты.")
        return Response({**pair, "profile": S.ProfileSerializer(user).data}, status=201)


class LoginView(APIView):
    authentication_classes = [PublicEndpointAuthentication]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    @extend_schema(auth=[], request=S.LoginSerializer, responses=S.AuthResultSerializer, tags=["Авторизация"])
    def post(self, request):
        data = validated(S.LoginSerializer, request)
        with transaction.atomic():
            user = User.objects.select_for_update().filter(email__iexact=data["email"]).first()
            if not user:
                User().set_password(data["password"])
                raise AuthenticationFailed("Неверная почта или пароль.")
            if not user.check_password(data["password"]) or user.is_banned:
                raise AuthenticationFailed("Неверные данные или пользователь заблокирован.")
            pair = issue_tokens(user)
        return Response({**pair, "profile": S.ProfileSerializer(user).data})


class RefreshView(APIView):
    authentication_classes = [PublicEndpointAuthentication]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    @extend_schema(auth=[], request=S.RefreshSerializer, responses=S.TokensSerializer, tags=["Авторизация"])
    def post(self, request):
        return Response(rotate_tokens(validated(S.RefreshSerializer, request)["refresh"]))


class LogoutView(AuthenticatedView):
    @extend_schema(request=S.RefreshSerializer, responses={204: None}, tags=["Авторизация"])
    def post(self, request):
        user = require_user(request)
        raw = validated(S.RefreshSerializer, request)["refresh"]
        with transaction.atomic():
            User.objects.select_for_update().get(pk=user.pk)
            user.sessions.filter(token_hash=digest(raw)).delete()
        return Response(status=204)


class MeView(AuthenticatedView):
    @extend_schema(responses=S.ProfileSerializer, tags=["Профиль"])
    def get(self, request):
        return Response(S.ProfileSerializer(require_user(request)).data)

    @extend_schema(request=S.NicknameSerializer, responses=S.ProfileSerializer, tags=["Профиль"])
    def patch(self, request):
        user = require_user(request)
        data = validated(S.NicknameSerializer, request)
        try:
            with transaction.atomic():
                if User.objects.filter(nickname__iexact=data["nickname"]).exclude(pk=user.pk).exists():
                    raise Conflict("Никнейм занят.")
                user.nickname = data["nickname"]
                user.save(update_fields=["nickname"])
        except IntegrityError:
            raise Conflict("Никнейм занят.")
        return Response(S.ProfileSerializer(user).data)


def delete_avatar_file(url):
    if url and url.startswith("/media/avatars/"):
        default_storage.delete(url.removeprefix("/media/"))


class AvatarView(AuthenticatedView):
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(request=S.AvatarSerializer, responses=S.ProfileSerializer, tags=["Профиль"])
    def post(self, request):
        user = require_user(request)
        image = validated(S.AvatarSerializer, request)["avatar"]
        # Re-encode instead of trusting user filenames or embedded file metadata.
        with Image.open(image) as source:
            source.thumbnail((1024, 1024))
            out = io.BytesIO()
            source.convert("RGB").save(out, "JPEG", quality=90)
        filename = default_storage.save(f"avatars/{uuid.uuid4().hex}.jpg", ContentFile(out.getvalue()))
        try:
            with transaction.atomic():
                user = User.objects.select_for_update().get(pk=user.pk)
                old = user.avatar_url
                user.avatar_url = default_storage.url(filename)
                user.save(update_fields=["avatar_url"])
                transaction.on_commit(lambda: delete_avatar_file(old))
        except Exception:
            default_storage.delete(filename)
            raise
        return Response(S.ProfileSerializer(user).data)

    @extend_schema(responses={204: None}, tags=["Профиль"])
    def delete(self, request):
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=require_user(request).pk)
            old = user.avatar_url
            user.avatar_url = None
            user.save(update_fields=["avatar_url"])
            transaction.on_commit(lambda: delete_avatar_file(old))
        return Response(status=204)


class PasswordView(AuthenticatedView):
    @extend_schema(request=S.PasswordSerializer, responses=S.TokensSerializer, tags=["Профиль"])
    def post(self, request):
        require_user(request)
        data = validated(S.PasswordSerializer, request)
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=request.user.pk)
            if not user.check_password(data["old_password"]):
                raise ValidationError({"old_password": "Неверный текущий пароль."})
            user.set_password(data["new_password"])
            user.save(update_fields=["password"])
            user.sessions.all().delete()
            pair = issue_tokens(user)
        return Response(pair)


class MyPollsView(AuthenticatedView):
    @extend_schema(parameters=POLL_FILTERS, responses=S.PollPageSerializer, tags=["Профиль"])
    def get(self, request):
        require_user(request)
        sync_due_polls()
        return poll_list(request, request.user.polls.all())


class MyResponsesView(AuthenticatedView):
    @extend_schema(parameters=PAGING, responses=S.PollPageSerializer, tags=["Профиль"])
    def get(self, request):
        require_user(request)
        sync_due_polls()
        return poll_list(request, Poll.objects.filter(responses__user=request.user))


class MyWarningsView(AuthenticatedView):
    @extend_schema(parameters=PAGING, responses=S.WarningPageSerializer, tags=["Профиль"])
    def get(self, request):
        return page(
            request, require_user(request).warnings.order_by("-created_at", "-pk"), S.WarningSerializer
        )


class PublicUserView(APIView):
    @extend_schema(responses=S.PublicUserSerializer, tags=["Пользователи"])
    def get(self, request, pk):
        return Response(S.PublicUserSerializer(get_object_or_404(User, pk=pk)).data)


class PublicUserPollsView(APIView):
    @extend_schema(parameters=POLL_FILTERS, responses=S.PollPageSerializer, tags=["Пользователи"])
    def get(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        sync_due_polls()
        return poll_list(request, user.polls.filter(visibility="public").exclude(status="draft"))


class PollsView(APIView):
    @extend_schema(
        operation_id="polls_list", parameters=POLL_FILTERS, responses=S.PollPageSerializer, tags=["Опросы"]
    )
    def get(self, request):
        sync_due_polls()
        return poll_list(request, Poll.objects.filter(visibility="public").exclude(status="draft"))

    @extend_schema(request=S.PollInputSerializer, responses={201: S.PollDetailSerializer}, tags=["Опросы"])
    def post(self, request):
        user = require_user(request)
        data = validated(S.PollInputSerializer, request)
        poll = S.save_poll(data, author=user)
        return Response(S.PollDetailSerializer(poll, context={"request": request}).data, status=201)


class PollView(APIView):
    @extend_schema(responses=S.PollDetailSerializer, tags=["Опросы"])
    def get(self, request, slug):
        poll = current_poll(slug)
        check_poll_access(poll, request)
        return Response(S.PollDetailSerializer(poll, context={"request": request}).data)

    @extend_schema(request=S.PollInputSerializer, responses=S.PollDetailSerializer, tags=["Опросы"])
    def patch(self, request, slug):
        current_poll(slug)
        with transaction.atomic():
            poll = get_object_or_404(Poll.objects.select_for_update(), slug=slug)
            require_owner(request, poll)
            if poll.status == "finished":
                raise PermissionDenied("Завершённый опрос нельзя изменить.")
            data = validated(S.PollInputSerializer, request, partial=True, poll=poll)
            poll = S.save_poll(data, poll=poll)
            update_poll_state(poll)
        return Response(S.PollDetailSerializer(poll, context={"request": request}).data)

    @extend_schema(responses={204: None}, tags=["Опросы"])
    def delete(self, request, slug):
        with transaction.atomic():
            poll = get_object_or_404(Poll.objects.select_for_update(), slug=slug)
            require_owner(request, poll)
            pk = poll.pk
            poll.delete()
            broadcast_after_commit(pk, "deleted")
        return Response(status=204)


class PublishView(AuthenticatedView):
    @extend_schema(request=S.PublishSerializer, responses=S.PollDetailSerializer, tags=["Опросы"])
    def post(self, request, slug):
        current_poll(slug)
        with transaction.atomic():
            poll = get_object_or_404(Poll.objects.select_for_update(), slug=slug)
            require_owner(request, poll)
            data = validated(S.PublishSerializer, request)
            if poll.status != "draft":
                raise Conflict("Публикация доступна только из черновика.")
            start = data.get("starts_at")
            now = timezone.now()
            if poll.ends_at and poll.ends_at <= max(start or now, now):
                raise ValidationError({"starts_at": "Публикация должна предшествовать завершению."})
            poll.starts_at = start
            if not start or start <= now:
                poll.status = "active"
                poll.published_at = now
            poll.save()
        return Response(S.PollDetailSerializer(poll, context={"request": request}).data)


class CloseView(AuthenticatedView):
    @extend_schema(request=None, responses=S.PollDetailSerializer, tags=["Опросы"])
    def post(self, request, slug):
        current_poll(slug)
        with transaction.atomic():
            poll = get_object_or_404(Poll.objects.select_for_update(), slug=slug)
            require_owner(request, poll)
            if poll.status != "active":
                raise Conflict("Завершить можно только активный опрос.")
            poll.status, poll.finished_at = "finished", timezone.now()
            poll.save(update_fields=["status", "finished_at", "updated_at"])
            broadcast_after_commit(poll.pk, "status_changed")
        return Response(S.PollDetailSerializer(poll, context={"request": request}).data)


class VoteView(APIView):
    @extend_schema(request=S.VoteSerializer, responses=S.ResultsSerializer, tags=["Голосование"])
    def post(self, request, slug):
        poll = current_poll(slug)
        data = validated(S.VoteSerializer, request)
        payload, token = vote(poll, request, data)
        response = Response(payload)
        if token:
            set_guest_cookie(response, token)
        return response


class ResultsView(APIView):
    @extend_schema(responses=S.ResultsSerializer, tags=["Голосование"])
    def get(self, request, slug):
        poll = current_poll(slug)
        require_results(poll, request)
        return Response(results(poll))


class VotersView(AuthenticatedView):
    @extend_schema(parameters=PAGING, responses=S.VoterPageSerializer, tags=["Голосование"])
    def get(self, request, slug):
        poll = current_poll(slug)
        require_owner(request, poll)
        if poll.access_mode != "registered":
            raise PermissionDenied("В анонимном режиме личности участников скрыты.")

        class VoterAdapter(S.VoterSerializer):
            def to_representation(self, obj):
                return {"user": S.PublicUserSerializer(obj.user).data, "answers": response_answers(obj)}

        return page(request, poll.responses.select_related("user").order_by("created_at", "pk"), VoterAdapter)


class ExportView(AuthenticatedView):
    @extend_schema(
        parameters=[OpenApiParameter("format", str, enum=["csv", "xlsx", "pdf"])],
        responses={(200, "application/octet-stream"): OpenApiTypes.BINARY},
        tags=["Голосование"],
    )
    def get(self, request, slug):
        from .exports import export_results

        poll = current_poll(slug)
        require_owner(request, poll)
        return export_results(poll, request.query_params.get("format", "csv"))


class CommentsView(APIView):
    @extend_schema(parameters=PAGING, responses=S.CommentPageSerializer, tags=["Комментарии"])
    def get(self, request, slug):
        poll = current_poll(slug)
        check_poll_access(poll, request)
        # Flat pagination includes every reply; parent_id reconstructs the discussion tree.
        return page(
            request, poll.comments.select_related("author").order_by("created_at", "pk"), S.CommentSerializer
        )

    @extend_schema(
        request=S.CommentInputSerializer, responses={201: S.CommentSerializer}, tags=["Комментарии"]
    )
    def post(self, request, slug):
        user = require_user(request)
        current_poll(slug)
        data = validated(S.CommentInputSerializer, request)
        with transaction.atomic():
            poll = get_object_or_404(Poll.objects.select_for_update(), slug=slug)
            check_poll_access(poll, request)
            if (
                poll.status != "active"
                or not poll.comments_enabled
                or (poll.ends_at and poll.ends_at <= timezone.now())
            ):
                raise PermissionDenied("Комментарии сейчас недоступны.")
            if data.get("parent_id"):
                get_object_or_404(Comment, pk=data["parent_id"], poll=poll)
            comment = Comment.objects.create(poll=poll, author=user, **data)
        return Response(S.CommentSerializer(comment).data, status=201)


class CommentView(AuthenticatedView):
    @extend_schema(request=S.CommentEditSerializer, responses=S.CommentSerializer, tags=["Комментарии"])
    def patch(self, request, pk):
        user = require_user(request)
        data = validated(S.CommentEditSerializer, request)
        with transaction.atomic():
            c = get_object_or_404(Comment.objects.select_for_update(), pk=pk)
            if c.author_id != user.pk:
                raise PermissionDenied("Изменять комментарий может только его автор.")
            c.text = data["text"]
            c.save(update_fields=["text", "updated_at"])
        return Response(S.CommentSerializer(c).data)

    @extend_schema(responses={204: None}, tags=["Комментарии"])
    def delete(self, request, pk):
        user = require_user(request)
        with transaction.atomic():
            c = get_object_or_404(Comment.objects.select_for_update(), pk=pk)
            if user.pk not in {c.author_id, c.poll.author_id}:
                raise PermissionDenied("Удаление доступно автору комментария или опроса.")
            c.delete()
        return Response(status=204)


class LikeView(AuthenticatedView):
    def change(self, request, pk, liked):
        user = require_user(request)
        with transaction.atomic():
            comment = get_object_or_404(Comment.objects.select_for_update(), pk=pk)
            check_poll_access(comment.poll, request)
            if liked:
                if comment.author_id == user.pk:
                    raise ValidationError("Нельзя лайкнуть свой комментарий.")
                CommentLike.objects.get_or_create(user=user, comment=comment)
            else:
                CommentLike.objects.filter(user=user, comment=comment).delete()
            comment.likes_count = comment.likes.count()
            comment.save(update_fields=["likes_count"])
        return Response({"liked": liked, "likes_count": comment.likes_count})

    @extend_schema(request=None, responses=S.LikeResultSerializer, tags=["Комментарии"])
    def post(self, request, pk):
        return self.change(request, pk, True)

    @extend_schema(responses=S.LikeResultSerializer, tags=["Комментарии"])
    def delete(self, request, pk):
        return self.change(request, pk, False)


class ReportsView(AuthenticatedView):
    @extend_schema(request=S.ReportInputSerializer, responses={201: S.ReportSerializer}, tags=["Жалобы"])
    def post(self, request):
        user = require_user(request)
        data = validated(S.ReportInputSerializer, request)
        if "poll_slug" in data:
            poll = current_poll(data.pop("poll_slug"))
            check_poll_access(poll, request)
            data["poll"] = poll
        else:
            comment = get_object_or_404(Comment.objects.select_related("poll"), pk=data["comment_id"])
            check_poll_access(comment.poll, request)
        report = Report.objects.create(reporter=user, **data)
        return Response(S.ReportSerializer(report).data, status=201)


class ModerationReportsView(AuthenticatedView):
    @extend_schema(
        parameters=PAGING + [OpenApiParameter("status", str, enum=["new", "accepted", "rejected"])],
        responses=S.ReportPageSerializer,
        tags=["Модерация"],
    )
    def get(self, request):
        require_role(request, {"moderator", "admin"})
        queryset = Report.objects.all()
        value = request.query_params.get("status")
        if value:
            if value not in {"new", "accepted", "rejected"}:
                raise ValidationError({"status": "Неизвестный статус."})
            queryset = queryset.filter(status=value)
        return page(request, queryset.order_by("-created_at", "-pk"), S.ReportSerializer)


class ReviewReportView(AuthenticatedView):
    @extend_schema(request=S.ReviewSerializer, responses=S.ReportSerializer, tags=["Модерация"])
    def patch(self, request, pk):
        actor = require_role(request, {"moderator", "admin"})
        data = validated(S.ReviewSerializer, request)
        with transaction.atomic():
            report = get_object_or_404(Report.objects.select_for_update(), pk=pk)
            report.status, report.reviewed_by, report.reviewed_at = data["status"], actor, timezone.now()
            report.save(update_fields=["status", "reviewed_by", "reviewed_at"])
        return Response(S.ReportSerializer(report).data)


class ModerationDeletePollView(AuthenticatedView):
    @extend_schema(request=S.ModerationDeleteSerializer, responses={204: None}, tags=["Модерация"])
    def post(self, request, slug):
        actor = require_role(request, {"moderator", "admin"})
        data = validated(S.ModerationDeleteSerializer, request)
        with transaction.atomic():
            # User before poll follows the session/moderation lock ordering.
            author_id = get_object_or_404(Poll, slug=slug).author_id
            target = User.objects.select_for_update().get(pk=author_id)
            poll = get_object_or_404(Poll.objects.select_for_update(), slug=slug)
            if data["is_violation"]:
                warn_user(target, actor, data["comment"])
            pk = poll.pk
            poll.delete()
            broadcast_after_commit(pk, "deleted")
        return Response(status=204)


class ModerationDeleteCommentView(AuthenticatedView):
    @extend_schema(request=S.ModerationDeleteSerializer, responses={204: None}, tags=["Модерация"])
    def post(self, request, pk):
        actor = require_role(request, {"moderator", "admin"})
        data = validated(S.ModerationDeleteSerializer, request)
        with transaction.atomic():
            author_id = get_object_or_404(Comment, pk=pk).author_id
            target = User.objects.select_for_update().get(pk=author_id)
            comment = get_object_or_404(Comment.objects.select_for_update(), pk=pk)
            if data["is_violation"]:
                warn_user(target, actor, data["comment"])
            comment.delete()
        return Response(status=204)


class ModerationWarningsView(AuthenticatedView):
    @extend_schema(parameters=PAGING, responses=S.WarningPageSerializer, tags=["Модерация"])
    def get(self, request, pk):
        require_role(request, {"moderator", "admin"})
        target = get_object_or_404(User, pk=pk)
        return page(request, target.warnings.order_by("-created_at", "-pk"), S.WarningSerializer)

    @extend_schema(request=S.ReasonSerializer, responses={201: S.WarningResultSerializer}, tags=["Модерация"])
    def post(self, request, pk):
        actor = require_role(request, {"moderator", "admin"})
        target = get_object_or_404(User, pk=pk)
        data = validated(S.ReasonSerializer, request)
        return Response(warn_user(target, actor, data["reason"]), status=201)


class DeleteWarningView(AuthenticatedView):
    @extend_schema(responses={204: None}, tags=["Модерация"])
    def delete(self, request, pk):
        require_role(request, {"moderator", "admin"})
        with transaction.atomic():
            target_id = get_object_or_404(Warning, pk=pk).user_id
            User.objects.select_for_update().get(pk=target_id)
            get_object_or_404(Warning, pk=pk).delete()
        return Response(status=204)


class AdminUsersView(AuthenticatedView):
    @extend_schema(
        parameters=PAGING
        + [
            OpenApiParameter("status", str, enum=["all", "users", "moderators", "admins", "banned"]),
            OpenApiParameter("q", str),
        ],
        responses=S.UserPageSerializer,
        tags=["Администрирование"],
    )
    def get(self, request):
        require_role(request, {"admin"})
        queryset = User.objects.select_related("role")
        value = request.query_params.get("status", "all")
        if value == "banned":
            queryset = queryset.filter(is_banned=True)
        elif value in {"users", "moderators", "admins"}:
            queryset = queryset.filter(
                role__name={"users": "user", "moderators": "moderator", "admins": "admin"}[value]
            )
        elif value != "all":
            raise ValidationError({"status": "Неизвестный фильтр."})
        if request.query_params.get("q"):
            q = request.query_params["q"]
            queryset = queryset.filter(Q(nickname__icontains=q) | Q(email__icontains=q))
        return page(request, queryset.order_by("pk"), S.ProfileSerializer)


class AdminRoleView(AuthenticatedView):
    @extend_schema(request=S.RoleInputSerializer, responses=S.ProfileSerializer, tags=["Администрирование"])
    def patch(self, request, pk):
        require_role(request, {"admin"})
        data = validated(S.RoleInputSerializer, request)
        with transaction.atomic():
            user = get_object_or_404(User.objects.select_for_update(), pk=pk)
            if user.role.name == "admin":
                raise PermissionDenied("Изменение роли администратора этим методом запрещено.")
            user.role = Role.objects.get(name=data["role"])
            user.save(update_fields=["role"])
        return Response(S.ProfileSerializer(user).data)


class AdminBanView(AuthenticatedView):
    @extend_schema(request=S.BanInputSerializer, responses=S.ProfileSerializer, tags=["Администрирование"])
    def post(self, request, pk):
        actor = require_role(request, {"admin"})
        data = validated(S.BanInputSerializer, request)
        with transaction.atomic():
            user = get_object_or_404(User.objects.select_for_update(), pk=pk)
            if user.pk == actor.pk:
                raise ValidationError("Нельзя заблокировать себя.")
            ban_user_locked(user, actor, data.get("reason"))
        return Response(S.ProfileSerializer(user).data)


class AdminUnbanView(AuthenticatedView):
    @extend_schema(request=None, responses=S.ProfileSerializer, tags=["Администрирование"])
    def post(self, request, pk):
        require_role(request, {"admin"})
        with transaction.atomic():
            user = get_object_or_404(User.objects.select_for_update(), pk=pk)
            if not user.is_banned:
                raise Conflict("Пользователь не заблокирован.")
            user.bans.filter(unbanned_at__isnull=True).update(unbanned_at=timezone.now())
            user.is_banned = False
            user.save(update_fields=["is_banned"])
        return Response(S.ProfileSerializer(user).data)


class AdminBansView(AuthenticatedView):
    @extend_schema(parameters=PAGING, responses=S.BanPageSerializer, tags=["Администрирование"])
    def get(self, request, pk):
        require_role(request, {"admin"})
        user = get_object_or_404(User, pk=pk)
        return page(request, user.bans.order_by("-banned_at", "-pk"), S.BanSerializer)
