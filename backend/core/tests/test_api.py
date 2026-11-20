import io
import uuid
from datetime import timedelta

from django.core import signing
from django.core.cache import cache
from django.db import IntegrityError, connection, transaction
from django.test import override_settings
from django.utils import timezone
from openpyxl import load_workbook
from PIL import Image
from rest_framework.test import APIClient, APITestCase

from core.auth import digest, issue_tokens
from core.models import (
    Answer,
    Comment,
    CommentLike,
    Option,
    Poll,
    Question,
    Report,
    Response,
    Role,
    User,
    Warning,
)
from core.services import sync_due_polls


PASSWORD = "Polls-Strong-Password-294!"


@override_settings(
    COOKIE_SECURE=False,
    MEDIA_ROOT="test-media",
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class ProjectAPITests(APITestCase):
    def setUp(self):
        cache.clear()
        for name in ["user", "moderator", "admin"]:
            Role.objects.get_or_create(name=name)
        self.owner = User.objects.create_user("owner@example.com", "Owner", PASSWORD)
        self.member = User.objects.create_user("member@example.com", "Member", PASSWORD)
        self.mod = User.objects.create_user(
            "mod@example.com", "Moderator", PASSWORD, role=Role.objects.get(name="moderator")
        )
        self.admin = User.objects.create_user(
            "admin@example.com", "Administrator", PASSWORD, role=Role.objects.get(name="admin")
        )
        self.client.force_authenticate(self.owner)

    def create_poll(self, **extra):
        data = {
            "title": "Какой вариант?",
            "questions": [
                {"text": "Выберите", "type": "single", "options": [{"text": "Первый"}, {"text": "Второй"}]}
            ],
            **extra,
        }
        response = self.client.post("/api/polls", data)
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def publish(self, poll):
        response = self.client.post(f"/api/polls/{poll['slug']}/publish", {})
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def ballot(self, poll):
        return {
            "answers": [
                {"question_id": q["id"], "option_ids": [q["options"][0]["id"]]} for q in poll["questions"]
            ]
        }

    def endpoint(self, poll, tail=""):
        return f"/api/polls/{poll['slug']}" + ("/" + tail if tail else "")

    def test_register_hashes_password_and_refresh(self):
        self.client.force_authenticate(None)
        response = self.client.post(
            "/api/auth/register",
            {
                "email": "new@example.com",
                "nickname": "New",
                "password": PASSWORD,
                "password_confirm": PASSWORD,
            },
        )
        self.assertEqual(response.status_code, 201, response.data)
        user = User.objects.get(email="new@example.com")
        self.assertTrue(user.check_password(PASSWORD))
        self.assertNotEqual(user.password, PASSWORD)
        session = user.sessions.get()
        self.assertEqual(session.token_hash, digest(response.data["refresh"]))
        self.assertEqual(len(session.token_hash), 64)
        self.assertAlmostEqual((session.expires_at - session.created_at).total_seconds(), 30 * 86400, delta=5)

    def test_duplicate_nickname_ignores_case(self):
        response = self.client.post(
            "/api/auth/register",
            {
                "email": "other@example.com",
                "nickname": "owner",
                "password": PASSWORD,
                "password_confirm": PASSWORD,
            },
        )
        self.assertEqual(response.status_code, 409)
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user("x@example.com", "oWnEr", PASSWORD)

    def test_register_rejects_password_mismatch_and_weak_password(self):
        base = {"email": "x@example.com", "nickname": "New", "password": "123", "password_confirm": "123"}
        self.assertEqual(self.client.post("/api/auth/register", base).status_code, 400)
        base["password_confirm"] = "different"
        self.assertEqual(self.client.post("/api/auth/register", base).status_code, 400)

    def test_token_rotation_revokes_old_refresh_and_access(self):
        self.client.force_authenticate(None)
        login = self.client.post("/api/auth/login", {"email": self.owner.email, "password": PASSWORD})
        self.assertEqual(login.status_code, 200)
        old = login.data
        renewed = self.client.post("/api/auth/refresh", {"refresh": old["refresh"]})
        self.assertEqual(renewed.status_code, 200)
        self.assertEqual(self.client.post("/api/auth/refresh", {"refresh": old["refresh"]}).status_code, 401)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + old["access"])
        self.assertEqual(self.client.get("/api/users/me").status_code, 401)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + renewed.data["access"])
        self.assertEqual(self.client.get("/api/users/me").status_code, 200)

    def test_logout_revokes_session(self):
        pair = issue_tokens(self.owner)
        self.client.force_authenticate(None)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + pair["access"])
        self.assertEqual(self.client.post("/api/auth/logout", {"refresh": pair["refresh"]}).status_code, 204)
        self.assertEqual(self.client.get("/api/users/me").status_code, 401)

    def test_change_password_revokes_all_old_sessions(self):
        pairs = [issue_tokens(self.owner) for _ in range(2)]
        changed = self.client.post(
            "/api/users/me/password",
            {
                "old_password": PASSWORD,
                "new_password": PASSWORD + "changed",
                "new_password_confirm": PASSWORD + "changed",
            },
        )
        self.assertEqual(changed.status_code, 200, changed.data)
        self.assertEqual(self.owner.sessions.count(), 1)
        self.client.force_authenticate(None)
        for pair in pairs:
            self.client.credentials(HTTP_AUTHORIZATION="Bearer " + pair["access"])
            self.assertEqual(self.client.get("/api/users/me").status_code, 401)

    def test_public_profile_does_not_expose_email_or_password(self):
        response = self.client.get(f"/api/users/{self.member.pk}")
        self.assertEqual(set(response.data), {"id", "nickname", "avatar_url", "created_at"})

    def test_nickname_patch_and_private_profile(self):
        self.assertEqual(self.client.patch("/api/users/me", {"nickname": "Renamed"}).status_code, 200)
        self.assertEqual(self.client.patch("/api/users/me", {"nickname": "member"}).status_code, 409)
        profile = self.client.get("/api/users/me")
        self.assertEqual(profile.data["role"], "user")
        self.assertNotIn("password", profile.data)

    def test_draft_hidden_and_only_owner_can_edit(self):
        poll = self.create_poll()
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get(self.endpoint(poll)).status_code, 403)
        self.assertEqual(self.client.patch(self.endpoint(poll), {"title": "Stolen"}).status_code, 403)
        self.assertEqual(self.client.delete(self.endpoint(poll)).status_code, 403)
        self.assertEqual(self.client.get("/api/polls").data["total"], 0)

    def test_active_and_finished_edit_restrictions(self):
        poll = self.publish(self.create_poll())
        self.assertEqual(self.client.patch(self.endpoint(poll), {"title": "Changed"}).status_code, 400)
        self.assertEqual(self.client.patch(self.endpoint(poll), {"comments_enabled": False}).status_code, 200)
        self.assertEqual(self.client.post(self.endpoint(poll, "close"), {}).status_code, 200)
        self.assertEqual(self.client.patch(self.endpoint(poll), {"max_votes": 5}).status_code, 403)

    def test_draft_questions_replaced_atomically(self):
        poll = self.create_poll()
        data = {"questions": [{"text": "New?", "type": "single", "options": [{"text": "A"}, {"text": "B"}]}]}
        response = self.client.patch(self.endpoint(poll), data)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["questions"][0]["text"], "New?")
        self.assertFalse(Question.objects.filter(pk=poll["questions"][0]["id"]).exists())

    def test_scale_options_are_generated(self):
        poll = self.create_poll(questions=[{"text": "Оценка", "type": "scale"}])
        self.assertEqual([o["text"] for o in poll["questions"][0]["options"]], ["1", "2", "3", "4", "5"])

    def test_invalid_question_limits_and_unknown_fields_rejected(self):
        invalid = {
            "title": "Poll",
            "questions": [
                {
                    "text": "?",
                    "type": "multiple",
                    "min_choices": 2,
                    "max_choices": 1,
                    "options": [{"text": "A"}, {"text": "B"}],
                }
            ],
        }
        self.assertEqual(self.client.post("/api/polls", invalid).status_code, 400)
        invalid["role"] = "admin"
        self.assertEqual(self.client.post("/api/polls", invalid).status_code, 400)

    def test_guest_vote_sets_cookie_and_repeat_is_conflict(self):
        poll = self.publish(self.create_poll())
        guest = APIClient()
        first = guest.post(self.endpoint(poll, "vote"), self.ballot(poll), format="json")
        self.assertEqual(first.status_code, 200, first.data)
        self.assertTrue(first.cookies["voter_token"]["httponly"])
        token = uuid.UUID(signing.loads(first.cookies["voter_token"].value, salt="polls-guest"))
        self.assertEqual(Response.objects.get(poll__slug=poll["slug"]).voter_token, token)
        self.assertEqual(
            guest.post(self.endpoint(poll, "vote"), self.ballot(poll), format="json").status_code, 409
        )
        self.assertEqual(guest.get(self.endpoint(poll, "results")).status_code, 200)

    def test_revote_replaces_answers_without_new_response(self):
        poll = self.publish(self.create_poll(allow_revote=True))
        self.client.force_authenticate(self.member)
        first = self.client.post(self.endpoint(poll, "vote"), self.ballot(poll))
        self.assertEqual(first.status_code, 200)
        ballot = self.ballot(poll)
        ballot["answers"][0]["option_ids"] = [poll["questions"][0]["options"][1]["id"]]
        second = self.client.post(self.endpoint(poll, "vote"), ballot)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(Response.objects.count(), 1)
        self.assertEqual(Answer.objects.count(), 1)
        self.assertEqual(second.data["questions"][0]["options"][0]["votes"], 0)
        self.assertEqual(Poll.objects.get(slug=poll["slug"]).responses_count, 1)

    def test_cross_poll_option_and_duplicate_answers_rejected(self):
        poll = self.publish(self.create_poll())
        other = self.create_poll()
        ballot = self.ballot(poll)
        ballot["answers"][0]["option_ids"] = [other["questions"][0]["options"][0]["id"]]
        self.assertEqual(self.client.post(self.endpoint(poll, "vote"), ballot).status_code, 400)
        ballot = self.ballot(poll)
        ballot["answers"] *= 2
        self.assertEqual(self.client.post(self.endpoint(poll, "vote"), ballot).status_code, 400)
        self.assertEqual(Response.objects.count(), 0)

    def test_multiple_choice_bounds_and_results(self):
        poll = self.publish(
            self.create_poll(
                questions=[
                    {
                        "text": "?",
                        "type": "multiple",
                        "min_choices": 2,
                        "max_choices": 2,
                        "options": [{"text": "A"}, {"text": "B"}, {"text": "C"}],
                    }
                ]
            )
        )
        ballot = self.ballot(poll)
        self.assertEqual(self.client.post(self.endpoint(poll, "vote"), ballot).status_code, 400)
        ballot["answers"][0]["option_ids"] = [o["id"] for o in poll["questions"][0]["options"][:2]]
        response = self.client.post(self.endpoint(poll, "vote"), ballot)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["questions"][0]["options"][1]["percent"], 100)

    def test_registered_poll_rejects_guest(self):
        poll = self.publish(self.create_poll(access_mode="registered"))
        guest = APIClient()
        self.assertEqual(guest.get(self.endpoint(poll)).status_code, 401)
        self.assertEqual(
            guest.post(self.endpoint(poll, "vote"), self.ballot(poll), format="json").status_code, 401
        )

    def test_results_author_and_participants_only(self):
        poll = self.publish(self.create_poll())
        self.assertEqual(self.client.get(self.endpoint(poll, "results")).status_code, 200)
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get(self.endpoint(poll, "results")).status_code, 403)
        self.client.post(self.endpoint(poll, "vote"), self.ballot(poll))
        self.assertEqual(self.client.get(self.endpoint(poll, "results")).status_code, 200)

    def test_anonymous_voters_hidden_even_from_author(self):
        poll = self.publish(self.create_poll())
        self.client.force_authenticate(self.member)
        self.client.post(self.endpoint(poll, "vote"), self.ballot(poll))
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.get(self.endpoint(poll, "voters")).status_code, 403)
        for fmt in ["csv", "xlsx", "pdf"]:
            response = self.client.get(self.endpoint(poll, "export") + "?format=" + fmt)
            self.assertEqual(response.status_code, 200)
            if fmt == "csv":
                self.assertNotIn(self.member.nickname.encode(), response.content)
            if fmt == "xlsx":
                workbook = load_workbook(io.BytesIO(response.content))
                self.assertNotIn(self.member.nickname, str(list(workbook.active.values)))
            if fmt == "pdf":
                self.assertTrue(response.content.startswith(b"%PDF"))

    def test_registered_voters_author_only(self):
        poll = self.publish(self.create_poll(access_mode="registered"))
        self.client.force_authenticate(self.member)
        self.client.post(self.endpoint(poll, "vote"), self.ballot(poll))
        self.assertEqual(self.client.get(self.endpoint(poll, "voters")).status_code, 403)
        self.client.force_authenticate(self.owner)
        response = self.client.get(self.endpoint(poll, "voters"))
        self.assertEqual(response.data["items"][0]["user"]["nickname"], self.member.nickname)

    def test_limit_closes_poll_and_rejects_next_vote(self):
        poll = self.publish(self.create_poll(max_votes=1))
        self.assertEqual(self.client.post(self.endpoint(poll, "vote"), self.ballot(poll)).status_code, 200)
        obj = Poll.objects.get(slug=poll["slug"])
        self.assertEqual(obj.status, "finished")
        self.assertIsNotNone(obj.finished_at)
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.post(self.endpoint(poll, "vote"), self.ballot(poll)).status_code, 403)

    def test_scheduler_publishes_and_closes(self):
        poll = self.create_poll()
        Poll.objects.filter(slug=poll["slug"]).update(starts_at=timezone.now() - timedelta(seconds=2))
        sync_due_polls()
        obj = Poll.objects.get(slug=poll["slug"])
        self.assertEqual(obj.status, "active")
        self.assertIsNotNone(obj.published_at)
        Poll.objects.filter(pk=obj.pk).update(ends_at=timezone.now() - timedelta(seconds=1))
        sync_due_polls()
        obj.refresh_from_db()
        self.assertEqual(obj.status, "finished")

    def test_vote_in_draft_or_expired_poll_rejected(self):
        poll = self.create_poll()
        self.assertEqual(self.client.post(self.endpoint(poll, "vote"), self.ballot(poll)).status_code, 403)
        poll = self.publish(poll)
        Poll.objects.filter(slug=poll["slug"]).update(ends_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.post(self.endpoint(poll, "vote"), self.ballot(poll)).status_code, 403)
        self.assertEqual(Poll.objects.get(slug=poll["slug"]).status, "finished")

    def test_catalog_hides_link_polls_and_supports_pagination(self):
        self.publish(self.create_poll(visibility="link"))
        self.publish(self.create_poll())
        response = self.client.get("/api/polls?limit=1")
        self.assertEqual(response.data["total"], 1)
        self.assertEqual(self.client.get("/api/polls?limit=0").status_code, 400)
        self.assertEqual(self.client.get("/api/polls?sort=bad").status_code, 400)

    def test_comments_likes_and_cascade(self):
        poll = self.publish(self.create_poll())
        comment = self.client.post(self.endpoint(poll, "comments"), {"text": "Комментарий"})
        self.assertEqual(comment.status_code, 201)
        pk = comment.data["id"]
        self.assertEqual(self.client.post(f"/api/comments/{pk}/like", {}).status_code, 400)
        self.client.force_authenticate(self.member)
        reply = self.client.post(self.endpoint(poll, "comments"), {"text": "Ответ", "parent_id": pk})
        self.assertEqual(reply.status_code, 201)
        for _ in range(2):
            self.assertEqual(self.client.post(f"/api/comments/{pk}/like", {}).data["likes_count"], 1)
        self.assertEqual(CommentLike.objects.count(), 1)
        self.assertEqual(self.client.delete(f"/api/comments/{pk}/like").data["likes_count"], 0)
        self.assertEqual(self.client.patch(f"/api/comments/{pk}", {"text": "stolen"}).status_code, 403)
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.delete(f"/api/comments/{pk}").status_code, 204)
        self.assertEqual(Comment.objects.count(), 0)

    def test_comments_disabled_and_cross_poll_parent_rejected(self):
        poll = self.publish(self.create_poll())
        comment = self.client.post(self.endpoint(poll, "comments"), {"text": "Parent"}).data
        other = self.publish(self.create_poll())
        self.assertEqual(
            self.client.post(
                self.endpoint(other, "comments"), {"text": "Reply", "parent_id": comment["id"]}
            ).status_code,
            404,
        )
        self.client.patch(self.endpoint(poll), {"comments_enabled": False})
        self.assertEqual(
            self.client.post(self.endpoint(poll, "comments"), {"text": "Blocked"}).status_code, 403
        )

    def test_reports_xor_and_review_permissions(self):
        poll = self.publish(self.create_poll())
        response = self.client.post("/api/reports", {"poll_slug": poll["slug"], "reason": "Нарушение"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.client.post("/api/reports", {"reason": "No target"}).status_code, 400)
        self.assertEqual(self.client.get("/api/moderation/reports").status_code, 403)
        self.client.force_authenticate(self.mod)
        review = self.client.patch(f"/api/moderation/reports/{response.data['id']}", {"status": "accepted"})
        self.assertEqual(review.status_code, 200)
        self.assertEqual(review.data["reviewed_by"], self.mod.pk)
        self.assertIsNotNone(review.data["reviewed_at"])

    def test_three_warnings_ban_and_unban_resets_count(self):
        pair = issue_tokens(self.member)
        self.client.force_authenticate(self.mod)
        for i in range(3):
            response = self.client.post(
                f"/api/moderation/users/{self.member.pk}/warnings", {"reason": f"Reason {i}"}
            )
            self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["auto_banned"])
        self.member.refresh_from_db()
        self.assertTrue(self.member.is_banned)
        self.assertEqual(self.member.sessions.count(), 0)
        ban = self.member.bans.get()
        self.assertTrue(ban.is_auto)
        self.assertIsNone(ban.banned_by_id)
        self.client.force_authenticate(None)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + pair["access"])
        self.assertEqual(self.client.get("/api/users/me").status_code, 401)
        self.client.credentials()
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post(f"/api/admin/users/{self.member.pk}/unban", {}).status_code, 200)
        self.client.force_authenticate(self.mod)
        response = self.client.post(
            f"/api/moderation/users/{self.member.pk}/warnings", {"reason": "After unban"}
        )
        self.assertEqual(response.data["warnings_count"], 1)
        self.assertFalse(response.data["auto_banned"])

    def test_manual_ban_and_role_permissions(self):
        self.assertEqual(
            self.client.patch(f"/api/admin/users/{self.member.pk}/role", {"role": "moderator"}).status_code,
            403,
        )
        self.client.force_authenticate(self.admin)
        self.assertEqual(
            self.client.patch(f"/api/admin/users/{self.member.pk}/role", {"role": "moderator"}).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(f"/api/admin/users/{self.member.pk}/ban", {"reason": "Ban"}).status_code, 200
        )
        self.assertEqual(self.client.get(f"/api/admin/users/{self.member.pk}/bans").data["total"], 1)

    def test_moderator_deletion_preserves_warning(self):
        warning = Warning.objects.create(user=self.member, moderator=self.mod, reason="Reason")
        self.mod.delete()
        warning.refresh_from_db()
        self.assertIsNone(warning.moderator_id)

    def test_moderation_delete_requires_reason_and_warns_author(self):
        poll = self.publish(self.create_poll())
        self.client.force_authenticate(self.mod)
        endpoint = f"/api/moderation/polls/{poll['slug']}/delete"
        self.assertEqual(self.client.post(endpoint, {"is_violation": True}).status_code, 400)
        self.assertEqual(
            self.client.post(endpoint, {"is_violation": True, "comment": "Violation"}).status_code, 204
        )
        self.assertEqual(self.owner.warnings.count(), 1)

    def test_delete_poll_cascades_every_dependent_table(self):
        poll = self.publish(self.create_poll())
        self.client.post(self.endpoint(poll, "vote"), self.ballot(poll))
        comment = self.client.post(self.endpoint(poll, "comments"), {"text": "Text"}).data
        self.client.force_authenticate(self.member)
        self.client.post(f"/api/comments/{comment['id']}/like", {})
        self.client.post("/api/reports", {"poll_slug": poll["slug"], "reason": "Reason"})
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.delete(self.endpoint(poll)).status_code, 204)
        for model in [Poll, Question, Option, Response, Answer, Comment, CommentLike, Report]:
            self.assertEqual(model.objects.count(), 0, model.__name__)

    def test_database_constraints(self):
        poll = self.create_poll()
        obj = Poll.objects.get(slug=poll["slug"])
        for kwargs in [{"max_votes": 0}, {"status": "bad"}, {"visibility": "bad"}]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                Poll.objects.filter(pk=obj.pk).update(**kwargs)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Response.objects.create(poll=obj)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Report.objects.create(reporter=self.owner, reason="Missing target")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Response.objects.create(poll_id=99999, user=self.owner)
            connection.check_constraints()

    def test_comment_likes_has_true_composite_pk(self):
        self.assertEqual(CommentLike._meta.pk.field_names, ("user_id", "comment_id"))
        self.assertNotIn("id", [f.name for f in CommentLike._meta.local_fields])

    def test_schema_contains_all_44_rest_operations(self):
        self.client.force_authenticate(None)
        response = self.client.get("/api/schema", HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 200)
        paths = response.data["paths"]
        count = sum(
            method in {"get", "post", "patch", "delete"}
            for path, operations in paths.items()
            if path not in {"/api/health"}
            for method in operations
        )
        self.assertEqual(count, 44)
        self.assertEqual(self.client.get("/api/docs").status_code, 200)

    def test_no_user_escalation_through_profile_or_registration(self):
        self.assertEqual(
            self.client.patch("/api/users/me", {"nickname": "NewName", "role": "admin"}).status_code, 400
        )

    def test_export_formula_injection_is_neutralized(self):
        poll = self.publish(
            self.create_poll(
                questions=[
                    {"text": "=1+1", "type": "single", "options": [{"text": "@bad"}, {"text": "Safe"}]}
                ]
            )
        )
        response = self.client.get(self.endpoint(poll, "export") + "?format=csv")
        self.assertIn(b"'=1+1", response.content)
        workbook = load_workbook(
            io.BytesIO(self.client.get(self.endpoint(poll, "export") + "?format=xlsx").content)
        )
        self.assertEqual(workbook.active["A2"].data_type, "s")

    def test_avatar_upload_and_removal(self):
        image = io.BytesIO()
        Image.new("RGB", (10, 10), "blue").save(image, "PNG")
        image.seek(0)
        image.name = "avatar.png"
        response = self.client.post("/api/users/me/avatar", {"avatar": image}, format="multipart")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["avatar_url"].startswith("/media/avatars/"))
        self.assertEqual(self.client.delete("/api/users/me/avatar").status_code, 204)
