import secrets
import string

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower


def new_slug():
    return "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(8))


class Role(models.Model):
    name = models.CharField(max_length=32, unique=True)

    class Meta:
        db_table = "roles"
        constraints = [
            models.CheckConstraint(condition=Q(name__in=["user", "moderator", "admin"]), name="valid_role")
        ]


class UserManager(BaseUserManager):
    def create_user(self, email, nickname, password=None, **extra):
        email = self.normalize_email(email).lower()
        if "role" not in extra and "role_id" not in extra:
            extra["role"], _ = Role.objects.get_or_create(name="user")
        user = self.model(email=email, nickname=nickname, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, nickname, password, **extra):
        extra["role"], _ = Role.objects.get_or_create(name="admin")
        return self.create_user(email, nickname, password, **extra)


class User(AbstractBaseUser):
    # Django's hashing API uses `password`, stored in the specified password_hash column.
    password = models.CharField(max_length=255, db_column="password_hash")
    last_login = None
    email = models.EmailField(max_length=255, unique=True)
    nickname = models.CharField(max_length=32, unique=True)
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="users")
    avatar_url = models.CharField(max_length=500, null=True, blank=True)
    is_banned = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = UserManager()
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["nickname"]

    @property
    def is_active(self):
        return not self.is_banned

    @property
    def is_staff(self):
        return self.role.name == "admin"

    @property
    def is_superuser(self):
        return self.is_staff

    class Meta:
        db_table = "users"
        constraints = [models.UniqueConstraint(Lower("nickname"), name="unique_nickname_case_insensitive")]


class RefreshToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sessions")
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "refresh_tokens"


class Warning(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="warnings")
    moderator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="issued_warnings")
    reason = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "warnings"


class Ban(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="bans")
    banned_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, db_column="banned_by", related_name="issued_bans"
    )
    is_auto = models.BooleanField(default=False)
    reason = models.CharField(max_length=500, null=True, blank=True)
    banned_at = models.DateTimeField(auto_now_add=True)
    unbanned_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "bans"


class Poll(models.Model):
    STATUS = [(x, x) for x in ("draft", "active", "finished")]
    ACCESS = [(x, x) for x in ("anonymous", "registered")]
    VISIBILITY = [(x, x) for x in ("public", "link")]
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="polls")
    slug = models.CharField(max_length=8, unique=True, default=new_slug)
    title = models.CharField(max_length=200)
    description = models.CharField(max_length=1000, null=True, blank=True)
    status = models.CharField(max_length=16, choices=STATUS, default="draft")
    access_mode = models.CharField(max_length=16, choices=ACCESS, default="anonymous")
    visibility = models.CharField(max_length=8, choices=VISIBILITY, default="public")
    allow_revote = models.BooleanField(default=False)
    comments_enabled = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    max_votes = models.IntegerField(null=True, blank=True)
    responses_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "polls"
        constraints = [
            models.CheckConstraint(condition=Q(slug__regex=r"^[A-Za-z0-9]{8}$"), name="valid_poll_slug"),
            models.CheckConstraint(
                condition=Q(status__in=["draft", "active", "finished"]), name="valid_poll_status"
            ),
            models.CheckConstraint(
                condition=Q(access_mode__in=["anonymous", "registered"]), name="valid_poll_access"
            ),
            models.CheckConstraint(
                condition=Q(visibility__in=["public", "link"]), name="valid_poll_visibility"
            ),
            models.CheckConstraint(
                condition=Q(max_votes__isnull=True) | Q(max_votes__gt=0), name="positive_max_votes"
            ),
            models.CheckConstraint(
                condition=Q(ends_at__isnull=True) | Q(starts_at__isnull=True) | Q(ends_at__gt=F("starts_at")),
                name="valid_poll_dates",
            ),
        ]
        indexes = [models.Index(fields=["visibility", "status", "-created_at"])]


class Question(models.Model):
    TYPES = [(x, x) for x in ("single", "multiple", "scale")]
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name="questions")
    text = models.CharField(max_length=300)
    type = models.CharField(max_length=16, choices=TYPES)
    min_choices = models.SmallIntegerField(default=1)
    max_choices = models.SmallIntegerField(default=1)
    position = models.SmallIntegerField()

    class Meta:
        db_table = "questions"
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(fields=["poll", "position"], name="unique_question_position"),
            models.CheckConstraint(
                condition=Q(type__in=["single", "multiple", "scale"]), name="valid_question_type"
            ),
            models.CheckConstraint(
                condition=Q(min_choices__gte=1) & Q(max_choices__gte=F("min_choices")),
                name="valid_choice_bounds",
            ),
        ]


class Option(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="options")
    text = models.CharField(max_length=200)
    position = models.SmallIntegerField()

    class Meta:
        db_table = "options"
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(fields=["question", "position"], name="unique_option_position")
        ]


class Response(models.Model):
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name="responses")
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, related_name="responses")
    voter_token = models.UUIDField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "responses"
        constraints = [
            models.UniqueConstraint(fields=["poll", "user"], name="unique_user_response"),
            models.UniqueConstraint(fields=["poll", "voter_token"], name="unique_guest_response"),
            models.CheckConstraint(
                condition=Q(user__isnull=False) | Q(voter_token__isnull=False),
                name="response_has_participant",
            ),
        ]


class Answer(models.Model):
    response = models.ForeignKey(Response, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="answers")
    option = models.ForeignKey(Option, on_delete=models.CASCADE, related_name="answers")

    class Meta:
        db_table = "answers"
        constraints = [models.UniqueConstraint(fields=["response", "option"], name="unique_response_option")]


class Comment(models.Model):
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="comments")
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="replies"
    )
    text = models.CharField(max_length=1000)
    likes_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "comments"


class CommentLike(models.Model):
    pk = models.CompositePrimaryKey("user_id", "comment_id")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="comment_likes")
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name="likes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "comment_likes"


class Report(models.Model):
    reporter = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reports")
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, null=True, related_name="reports")
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, null=True, related_name="reports")
    reason = models.CharField(max_length=500)
    status = models.CharField(
        max_length=16, choices=[(x, x) for x in ("new", "accepted", "rejected")], default="new"
    )
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, db_column="reviewed_by", related_name="reviewed_reports"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True)

    class Meta:
        db_table = "reports"
        constraints = [
            models.CheckConstraint(
                condition=Q(poll__isnull=False, comment__isnull=True)
                | Q(poll__isnull=True, comment__isnull=False),
                name="report_exactly_one_target",
            ),
            models.CheckConstraint(
                condition=Q(status__in=["new", "accepted", "rejected"]), name="valid_report_status"
            ),
        ]
