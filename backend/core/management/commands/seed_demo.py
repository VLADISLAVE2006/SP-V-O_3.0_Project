"""Small, repeatable local dataset for frontend development and manual QA."""

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import Answer, Ban, Comment, CommentLike, Poll, Report, Response, Role, User, Warning
from core.serializers import PollInputSerializer, save_poll


ACCOUNTS = {
    "owner": ("demo.owner@example.test", "demo_owner", "user"),
    "participant": ("demo.participant@example.test", "demo_participant", "user"),
    "moderator": ("demo.moderator@example.test", "demo_moderator", "moderator"),
    "admin": ("demo.admin@example.test", "demo_admin", "admin"),
    "banned": ("demo.banned@example.test", "demo_banned", "user"),
}


class Command(BaseCommand):
    help = "Create local demo accounts and polls. Requires DEBUG=1; existing data is never reset."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password", default="Demo-Polls-2026!", help="Password for newly created demo users."
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Demo data is allowed only with DJANGO_DEBUG=1.")
        users = {}
        for key, (email, nickname, role_name) in ACCOUNTS.items():
            role, _ = Role.objects.get_or_create(name=role_name)
            user = User.objects.filter(email=email).first()
            if user:
                if user.nickname != nickname:
                    raise CommandError(f"Demo email already belongs to another user: {email}")
            else:
                if User.objects.filter(nickname__iexact=nickname).exists():
                    raise CommandError(f"Demo nickname already exists: {nickname}")
                user = User.objects.create_user(email, nickname, options["password"], role=role)
            users[key] = user

        polls = {}
        definitions = [
            ("DEMO0001", "Формат занятий", "active", "anonymous", "public", False),
            ("DEMO0002", "Опрос для зарегистрированных", "active", "registered", "public", True),
            ("DEMO0003", "Черновик анкеты", "draft", "anonymous", "public", False),
            ("DEMO0004", "Завершённый опрос", "finished", "anonymous", "public", False),
            ("DEMO0005", "Опрос по ссылке", "active", "anonymous", "link", False),
            ("DEMO0006", "Отложенная публикация", "draft", "anonymous", "public", False),
        ]
        for slug, title, status, access, visibility, revote in definitions:
            poll = Poll.objects.filter(slug=slug).first()
            if poll:
                if poll.author_id != users["owner"].pk:
                    raise CommandError(f"Demo slug is already used: {slug}")
            else:
                serializer = PollInputSerializer(
                    data={
                        "title": title,
                        "access_mode": access,
                        "visibility": visibility,
                        "allow_revote": revote,
                        "questions": [
                            {
                                "text": "Какой формат удобнее?",
                                "type": "single",
                                "options": [{"text": "Очно"}, {"text": "Онлайн"}],
                            },
                            {
                                "text": "Какие темы интересны?",
                                "type": "multiple",
                                "min_choices": 1,
                                "max_choices": 2,
                                "options": [
                                    {"text": "Python"},
                                    {"text": "Базы данных"},
                                    {"text": "Интерфейсы"},
                                ],
                            },
                            {"text": "Оцените интерес к теме", "type": "scale"},
                        ],
                    }
                )
                serializer.is_valid(raise_exception=True)
                data = dict(serializer.validated_data)
                data["slug"] = slug
                poll = save_poll(data, author=users["owner"])
                poll.status = status
                poll.published_at = timezone.now() if status != "draft" else None
                poll.finished_at = timezone.now() if status == "finished" else None
                if slug == "DEMO0006":
                    poll.starts_at = timezone.now() + timedelta(minutes=10)
                poll.save()
            polls[slug] = poll

        # Only fill new demo objects. Re-running must not overwrite manual testing work.
        for slug in ["DEMO0001", "DEMO0002", "DEMO0004"]:
            poll = polls[slug]
            response, created = Response.objects.get_or_create(poll=poll, user=users["participant"])
            if created:
                for question in poll.questions.all():
                    Answer.objects.create(
                        response=response, question=question, option=question.options.first()
                    )
                poll.responses_count = poll.responses.count()
                poll.save(update_fields=["responses_count"])

        comment, _ = Comment.objects.get_or_create(
            poll=polls["DEMO0001"], author=users["owner"], parent=None, text="Как вам такой формат опроса?"
        )
        Comment.objects.get_or_create(
            poll=polls["DEMO0001"],
            author=users["participant"],
            parent=comment,
            text="Удобно, особенно шкала оценки.",
        )
        CommentLike.objects.get_or_create(user=users["participant"], comment=comment)
        comment.likes_count = comment.likes.count()
        comment.save(update_fields=["likes_count"])
        Report.objects.get_or_create(
            reporter=users["participant"],
            poll=polls["DEMO0005"],
            reason="Демо-жалоба для проверки модерации.",
        )
        Warning.objects.get_or_create(
            user=users["participant"], moderator=users["moderator"], reason="Демо-предупреждение."
        )
        banned = users["banned"]
        if not banned.is_banned and not banned.bans.exists():
            Ban.objects.create(user=banned, banned_by=users["admin"], reason="Демо-блокировка.")
            banned.is_banned = True
            banned.save(update_fields=["is_banned"])
        self.stdout.write(
            self.style.SUCCESS("Demo data is ready. Existing passwords and poll states were not reset.")
        )
        for email, _, role in ACCOUNTS.values():
            self.stdout.write(f"{email} ({role})")
        self.stdout.write("Poll codes: " + ", ".join(polls))
