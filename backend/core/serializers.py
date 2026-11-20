from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers

from .models import Ban, Comment, Option, Poll, Question, Report, User, Warning


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError({x: ["Неизвестное поле."] for x in unknown})
        return super().to_internal_value(data)


class PublicUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "nickname", "avatar_url", "created_at"]


class ProfileSerializer(PublicUserSerializer):
    role = serializers.CharField(source="role.name")
    polls_count = serializers.IntegerField(source="polls.count")
    warnings_count = serializers.SerializerMethodField()

    def get_warnings_count(self, obj) -> int:
        from .services import active_warning_count

        return active_warning_count(obj)

    class Meta:
        model = User
        fields = PublicUserSerializer.Meta.fields + [
            "email",
            "role",
            "is_banned",
            "polls_count",
            "warnings_count",
        ]


class RegisterSerializer(StrictSerializer):
    email = serializers.EmailField(max_length=255)
    nickname = serializers.CharField(max_length=32)
    password = serializers.CharField(write_only=True, max_length=128, trim_whitespace=False)
    password_confirm = serializers.CharField(write_only=True, max_length=128, trim_whitespace=False)

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "Пароли не совпадают."})
        validate_password(attrs["password"], User(email=attrs["email"], nickname=attrs["nickname"]))
        attrs["email"] = attrs["email"].lower()
        return attrs


class LoginSerializer(StrictSerializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False)


class RefreshSerializer(StrictSerializer):
    refresh = serializers.CharField()


class TokensSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()


class AuthResultSerializer(TokensSerializer):
    profile = ProfileSerializer()


class NicknameSerializer(StrictSerializer):
    nickname = serializers.CharField(max_length=32)


class PasswordSerializer(StrictSerializer):
    old_password = serializers.CharField(trim_whitespace=False)
    new_password = serializers.CharField(max_length=128, trim_whitespace=False)
    new_password_confirm = serializers.CharField(max_length=128, trim_whitespace=False)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError({"new_password_confirm": "Пароли не совпадают."})
        validate_password(attrs["new_password"], self.context["request"].user)
        return attrs


class AvatarSerializer(StrictSerializer):
    avatar = serializers.ImageField()

    def validate_avatar(self, image):
        if image.size > 5 * 1024 * 1024 or image.image.format not in {"JPEG", "PNG", "WEBP"}:
            raise serializers.ValidationError("Нужен JPG, PNG или WebP не больше 5 МБ.")
        return image


class OptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Option
        fields = ["id", "text", "position"]


class QuestionSerializer(serializers.ModelSerializer):
    options = OptionSerializer(many=True)

    class Meta:
        model = Question
        fields = ["id", "text", "type", "min_choices", "max_choices", "position", "options"]


class OptionInputSerializer(StrictSerializer):
    text = serializers.CharField(max_length=200)


class QuestionInputSerializer(StrictSerializer):
    text = serializers.CharField(max_length=300)
    type = serializers.ChoiceField(choices=Question.TYPES)
    min_choices = serializers.IntegerField(min_value=1, default=1)
    max_choices = serializers.IntegerField(min_value=1, default=1)
    options = OptionInputSerializer(many=True, required=False)

    def validate(self, attrs):
        attrs.setdefault("min_choices", 1)
        attrs.setdefault("max_choices", 1)
        if attrs["type"] == "scale":
            attrs["options"] = [{"text": str(x)} for x in range(1, 6)]
        options = attrs.get("options", [])
        if not 2 <= len(options) <= 10:
            raise serializers.ValidationError({"options": "Укажите от 2 до 10 вариантов."})
        low, high = attrs["min_choices"], attrs["max_choices"]
        if not 1 <= low <= high <= len(options):
            raise serializers.ValidationError("Неверные границы выбора.")
        if attrs["type"] in {"single", "scale"} and (low, high) != (1, 1):
            raise serializers.ValidationError("Для single и scale min_choices = max_choices = 1.")
        return attrs


class PollInputSerializer(StrictSerializer):
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(max_length=1000, allow_blank=True, allow_null=True, required=False)
    access_mode = serializers.ChoiceField(choices=Poll.ACCESS, default="anonymous")
    visibility = serializers.ChoiceField(choices=Poll.VISIBILITY, default="public")
    allow_revote = serializers.BooleanField(default=False)
    comments_enabled = serializers.BooleanField(default=True)
    ends_at = serializers.DateTimeField(allow_null=True, required=False)
    max_votes = serializers.IntegerField(min_value=1, allow_null=True, required=False)
    questions = QuestionInputSerializer(many=True, allow_empty=False)

    def validate(self, attrs):
        instance = self.context.get("poll")
        if instance and instance.status != "draft":
            if instance.status == "finished":
                raise serializers.ValidationError("Завершённый опрос нельзя изменить.")
            invalid = set(attrs) - {"ends_at", "max_votes", "comments_enabled"}
            if invalid:
                raise serializers.ValidationError(
                    "В активном опросе доступны только ends_at, max_votes, comments_enabled."
                )
        start = instance.starts_at if instance else None
        end = attrs.get("ends_at", instance.ends_at if instance else None)
        if start and end and end <= start:
            raise serializers.ValidationError({"ends_at": "Завершение должно быть позже публикации."})
        return attrs


@transaction.atomic
def save_poll(validated, *, author=None, poll=None):
    questions = validated.pop("questions", None)
    if poll is None:
        poll = Poll.objects.create(author=author, **validated)
    else:
        for key, value in validated.items():
            setattr(poll, key, value)
        poll.save()
    if questions is not None:
        poll.questions.all().delete()
        for position, data in enumerate(questions, 1):
            options = data.pop("options")
            question = Question.objects.create(poll=poll, position=position, **data)
            Option.objects.bulk_create(
                [Option(question=question, position=i, **v) for i, v in enumerate(options, 1)]
            )
    return poll


class PollSummarySerializer(serializers.ModelSerializer):
    author = PublicUserSerializer()

    class Meta:
        model = Poll
        fields = [
            "id",
            "slug",
            "title",
            "description",
            "status",
            "access_mode",
            "visibility",
            "author",
            "responses_count",
            "created_at",
            "ends_at",
        ]


class MyAnswerSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()
    option_ids = serializers.ListField(child=serializers.IntegerField())


class PollDetailSerializer(PollSummarySerializer):
    questions = QuestionSerializer(many=True)
    can_vote = serializers.SerializerMethodField()
    has_voted = serializers.SerializerMethodField()
    results_available = serializers.SerializerMethodField()
    my_answers = serializers.SerializerMethodField()

    def _response(self, obj):
        from .services import participant_response

        if not hasattr(self, "_participant"):
            self._participant = participant_response(obj, self.context["request"])
        return self._participant

    def get_can_vote(self, obj) -> bool:
        return obj.status == "active" and (not self._response(obj) or obj.allow_revote)

    def get_has_voted(self, obj) -> bool:
        return self._response(obj) is not None

    def get_results_available(self, obj) -> bool:
        return obj.status != "draft" and (
            obj.author_id == self.context["request"].user.pk or self._response(obj) is not None
        )

    def get_my_answers(self, obj) -> list[dict]:
        from .services import response_answers

        response = self._response(obj)
        return response_answers(response) if response else []

    class Meta:
        model = Poll
        fields = PollSummarySerializer.Meta.fields + [
            "allow_revote",
            "comments_enabled",
            "starts_at",
            "max_votes",
            "updated_at",
            "published_at",
            "finished_at",
            "questions",
            "can_vote",
            "has_voted",
            "my_answers",
            "results_available",
        ]


class PublishSerializer(StrictSerializer):
    starts_at = serializers.DateTimeField(required=False, allow_null=True)


class VoteAnswerSerializer(StrictSerializer):
    question_id = serializers.IntegerField(min_value=1)
    option_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), allow_empty=False)


class VoteSerializer(StrictSerializer):
    answers = VoteAnswerSerializer(many=True, allow_empty=False)


class OptionResultSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    text = serializers.CharField()
    votes = serializers.IntegerField()
    percent = serializers.FloatField()


class QuestionResultSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    text = serializers.CharField()
    type = serializers.CharField()
    options = OptionResultSerializer(many=True)


class ResultsSerializer(serializers.Serializer):
    total_responses = serializers.IntegerField()
    questions = QuestionResultSerializer(many=True)


class CommentInputSerializer(StrictSerializer):
    text = serializers.CharField(max_length=1000)
    parent_id = serializers.IntegerField(min_value=1, allow_null=True, required=False)


class CommentEditSerializer(StrictSerializer):
    text = serializers.CharField(max_length=1000)


class CommentSerializer(serializers.ModelSerializer):
    author = PublicUserSerializer()

    class Meta:
        model = Comment
        fields = ["id", "poll_id", "author", "parent_id", "text", "likes_count", "created_at", "updated_at"]


class ReportInputSerializer(StrictSerializer):
    poll_slug = serializers.CharField(max_length=8, required=False)
    comment_id = serializers.IntegerField(min_value=1, required=False)
    reason = serializers.CharField(max_length=500)

    def validate(self, attrs):
        if ("poll_slug" in attrs) == ("comment_id" in attrs):
            raise serializers.ValidationError("Укажите ровно одно поле: poll_slug или comment_id.")
        return attrs


class ReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = Report
        fields = [
            "id",
            "reporter_id",
            "poll_id",
            "comment_id",
            "reason",
            "status",
            "reviewed_by",
            "created_at",
            "reviewed_at",
        ]


class ReviewSerializer(StrictSerializer):
    status = serializers.ChoiceField(choices=["accepted", "rejected"])


class ReasonSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=500)


class BanInputSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=500, allow_blank=True, allow_null=True, required=False)


class ModerationDeleteSerializer(StrictSerializer):
    is_violation = serializers.BooleanField(default=False)
    comment = serializers.CharField(max_length=500, required=False)

    def validate(self, attrs):
        if attrs["is_violation"] and not attrs.get("comment"):
            raise serializers.ValidationError({"comment": "Обязательно при нарушении."})
        return attrs


class RoleInputSerializer(StrictSerializer):
    role = serializers.ChoiceField(choices=["user", "moderator"])


class WarningSerializer(serializers.ModelSerializer):
    class Meta:
        model = Warning
        fields = ["id", "user_id", "moderator_id", "reason", "created_at"]


class BanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ban
        fields = ["id", "user_id", "banned_by", "is_auto", "reason", "banned_at", "unbanned_at"]


class LikeResultSerializer(serializers.Serializer):
    liked = serializers.BooleanField()
    likes_count = serializers.IntegerField()


class WarningResultSerializer(serializers.Serializer):
    warnings_count = serializers.IntegerField()
    auto_banned = serializers.BooleanField()


class VoterSerializer(serializers.Serializer):
    user = PublicUserSerializer()
    answers = MyAnswerSerializer(many=True)


def page_serializer(item, name):
    return type(
        name,
        (serializers.Serializer,),
        {
            "items": item(many=True),
            "total": serializers.IntegerField(),
            "has_more": serializers.BooleanField(),
        },
    )


PollPageSerializer = page_serializer(PollSummarySerializer, "PollPage")
CommentPageSerializer = page_serializer(CommentSerializer, "CommentPage")
WarningPageSerializer = page_serializer(WarningSerializer, "WarningPage")
ReportPageSerializer = page_serializer(ReportSerializer, "ReportPage")
UserPageSerializer = page_serializer(ProfileSerializer, "UserPage")
BanPageSerializer = page_serializer(BanSerializer, "BanPage")
VoterPageSerializer = page_serializer(VoterSerializer, "VoterPage")
