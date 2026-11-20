import logging
import uuid

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.core import signing
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.exceptions import APIException, NotAuthenticated, PermissionDenied, ValidationError

from .models import Answer, Ban, Poll, Response, User, Warning

logger = logging.getLogger(__name__)


class Conflict(APIException):
    status_code = 409
    default_detail = "Конфликт данных."


def require_user(request):
    if not request.user.is_authenticated:
        raise NotAuthenticated("Требуется вход.")
    return request.user


def require_role(request, roles):
    user = require_user(request)
    if user.role.name not in roles:
        raise PermissionDenied("Недостаточно прав.")
    return user


def require_owner(request, poll):
    if require_user(request).pk != poll.author_id:
        raise PermissionDenied("Действие доступно только автору опроса.")


def check_poll_access(poll, request):
    if poll.status == "draft" and request.user.pk != poll.author_id:
        raise PermissionDenied("Черновик доступен только автору.")
    if poll.access_mode == "registered" and not request.user.is_authenticated:
        raise NotAuthenticated("Этот опрос доступен только зарегистрированным пользователям.")


def guest_token(request):
    raw = request.COOKIES.get("voter_token")
    if raw:
        try:
            return uuid.UUID(signing.loads(raw, salt="polls-guest", max_age=365 * 86400))
        except (signing.BadSignature, ValueError, TypeError):
            pass
    return None


def set_guest_cookie(response, token):
    response.set_cookie(
        "voter_token",
        signing.dumps(str(token), salt="polls-guest"),
        max_age=365 * 86400,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
    )


def participant_response(poll, request):
    if request.user.is_authenticated:
        return poll.responses.filter(user=request.user).first()
    token = guest_token(request)
    return poll.responses.filter(voter_token=token, user__isnull=True).first() if token else None


def response_answers(response):
    grouped = {}
    for question, option in response.answers.order_by("question__position", "option__position").values_list(
        "question_id", "option_id"
    ):
        grouped.setdefault(question, []).append(option)
    return [{"question_id": q, "option_ids": ids} for q, ids in grouped.items()]


def require_results(poll, request):
    check_poll_access(poll, request)
    if poll.status == "draft" or (
        poll.author_id != request.user.pk and not participant_response(poll, request)
    ):
        raise PermissionDenied("Результаты доступны автору и участникам после голосования.")


def results(poll):
    total = poll.responses.count()
    counts = dict(
        Answer.objects.filter(response__poll=poll)
        .values("option_id")
        .annotate(n=Count("id"))
        .values_list("option_id", "n")
    )
    return {
        "total_responses": total,
        "questions": [
            {
                "id": q.pk,
                "text": q.text,
                "type": q.type,
                "options": [
                    {
                        "id": o.pk,
                        "text": o.text,
                        "votes": counts.get(o.pk, 0),
                        "percent": round(counts.get(o.pk, 0) / total * 100, 2) if total else 0.0,
                    }
                    for o in q.options.all()
                ],
            }
            for q in poll.questions.prefetch_related("options")
        ],
    }


def broadcast_after_commit(poll_id, event):
    def send():
        try:
            layer = get_channel_layer()
            async_to_sync(layer.group_send)(f"poll.{poll_id}", {"type": "poll.event", "event": event})
        except Exception:
            # A broker outage must not turn an already committed vote into a failed HTTP response.
            logger.exception("WebSocket delivery failed for poll %s", poll_id)

    transaction.on_commit(send)


def update_poll_state(poll):
    """Caller holds a row lock inside an atomic transaction."""
    now = timezone.now()
    changed = False
    if poll.status == "draft" and poll.starts_at and poll.starts_at <= now:
        poll.status = "active"
        poll.published_at = now
        changed = True
    if poll.status == "active" and (
        (poll.ends_at and poll.ends_at <= now) or (poll.max_votes and poll.responses_count >= poll.max_votes)
    ):
        poll.status = "finished"
        poll.finished_at = now
        changed = True
    if changed:
        poll.save(update_fields=["status", "published_at", "finished_at", "updated_at"])
        broadcast_after_commit(poll.pk, "status_changed")
    return poll


def sync_due_polls():
    now = timezone.now()
    ids = Poll.objects.filter(
        Q(status="draft", starts_at__lte=now) | Q(status="active", ends_at__lte=now)
    ).values_list("pk", flat=True)
    for pk in list(ids):
        with transaction.atomic():
            poll = Poll.objects.select_for_update().filter(pk=pk).first()
            if poll:
                update_poll_state(poll)


def current_poll(slug):
    from django.shortcuts import get_object_or_404

    # Commit time transitions independently of any later permission or validation error.
    with transaction.atomic():
        poll = get_object_or_404(Poll.objects.select_for_update(), slug=slug)
        update_poll_state(poll)
    return poll


@transaction.atomic
def vote(poll, request, data):
    poll = Poll.objects.select_for_update().get(pk=poll.pk)
    check_poll_access(poll, request)
    # A concurrent close or scheduler update may have won the lock.
    if poll.status != "active" or (poll.ends_at and poll.ends_at <= timezone.now()):
        raise PermissionDenied("Голосовать можно только в активном опросе.")
    existing = participant_response(poll, request)
    if existing and not poll.allow_revote:
        raise Conflict("Повторное прохождение запрещено.")
    questions = {q.pk: q for q in poll.questions.prefetch_related("options")}
    answers = data["answers"]
    if len(answers) != len(questions) or {a["question_id"] for a in answers} != set(questions):
        raise ValidationError({"answers": "Ответьте на каждый вопрос ровно один раз."})
    for answer in answers:
        q = questions[answer["question_id"]]
        ids = answer["option_ids"]
        if len(ids) != len(set(ids)) or not q.min_choices <= len(ids) <= q.max_choices:
            raise ValidationError({"answers": "Неверное число вариантов или повтор варианта."})
        if not set(ids).issubset({o.pk for o in q.options.all()}):
            raise ValidationError({"answers": "Вариант не принадлежит вопросу этого опроса."})
    token = None
    if existing:
        response = existing
        response.answers.all().delete()
        response.save(update_fields=["updated_at"])
    else:
        if poll.max_votes and poll.responses_count >= poll.max_votes:
            raise PermissionDenied("Достигнут лимит участников.")
        token = None if request.user.is_authenticated else (guest_token(request) or uuid.uuid4())
        response = Response.objects.create(
            poll=poll, user=request.user if request.user.is_authenticated else None, voter_token=token
        )
    Answer.objects.bulk_create(
        [
            Answer(response=response, question_id=a["question_id"], option_id=o)
            for a in answers
            for o in a["option_ids"]
        ]
    )
    poll.responses_count = poll.responses.count()
    poll.save(update_fields=["responses_count", "updated_at"])
    update_poll_state(poll)
    broadcast_after_commit(poll.pk, "results_updated")
    return results(poll), token


def active_warning_count(user):
    last_unban = (
        user.bans.filter(unbanned_at__isnull=False)
        .order_by("-unbanned_at")
        .values_list("unbanned_at", flat=True)
        .first()
    )
    qs = user.warnings.all()
    return (qs.filter(created_at__gt=last_unban) if last_unban else qs).count()


def ban_user_locked(user, actor=None, reason=None, auto=False):
    if user.is_banned:
        raise Conflict("Пользователь уже заблокирован.")
    Ban.objects.create(user=user, banned_by=actor, reason=reason, is_auto=auto)
    user.is_banned = True
    user.save(update_fields=["is_banned"])
    user.sessions.all().delete()


@transaction.atomic
def warn_user(user, moderator, reason):
    user = User.objects.select_for_update().get(pk=user.pk)
    Warning.objects.create(user=user, moderator=moderator, reason=reason)
    count = active_warning_count(user)
    auto = count >= 3 and not user.is_banned
    if auto:
        ban_user_locked(user, reason="Три предупреждения", auto=True)
    return {"warnings_count": count, "auto_banned": auto}
