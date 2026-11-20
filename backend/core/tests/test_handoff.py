import io

from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APITestCase

from core.management.commands.seed_demo import ACCOUNTS
from core.models import Poll, Role, User
from core.tests.test_api import PASSWORD


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class IntegrationContractTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("handoff@example.test", "HandoffUser", PASSWORD)
        self.client.force_authenticate(self.user)

    def test_incomplete_nested_patch_returns_field_errors_without_changing_poll(self):
        poll = self.client.post(
            "/api/polls",
            {
                "title": "Before",
                "questions": [
                    {
                        "text": "Question",
                        "type": "single",
                        "options": [{"text": "A"}, {"text": "B"}],
                    }
                ],
            },
        ).data
        for invalid in [
            {"type": "single", "options": [{"text": "A"}, {"text": "B"}]},
            {"text": "Question", "options": [{"text": "A"}, {"text": "B"}]},
            {"text": "Question", "type": "single", "options": [{}, {"text": "B"}]},
        ]:
            response = self.client.patch(
                f"/api/polls/{poll['slug']}", {"title": "After", "questions": [invalid]}
            )
            self.assertEqual(response.status_code, 400, response.data)
            self.assertIn("questions", response.data)
        obj = Poll.objects.get(slug=poll["slug"])
        self.assertEqual(obj.title, "Before")
        self.assertEqual(obj.questions.get().text, "Question")

    def test_weak_new_password_error_uses_the_actual_form_field(self):
        response = self.client.post(
            "/api/users/me/password",
            {
                "old_password": PASSWORD,
                "new_password": "123",
                "new_password_confirm": "123",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("new_password", response.data)
        self.assertNotIn("password", response.data)

    def test_schema_describes_nested_answers_security_and_errors(self):
        schema = self.client.get("/api/schema", HTTP_ACCEPT="application/json").data
        security = schema["paths"]["/api/polls"]["post"]["security"]
        self.assertNotIn({}, security)
        self.assertIn("400", schema["paths"]["/api/polls"]["post"]["responses"])
        self.assertIn("409", schema["paths"]["/api/polls/{slug}/vote"]["post"]["responses"])
        answers = schema["components"]["schemas"]["PollDetail"]["properties"]["my_answers"]
        self.assertEqual(answers["items"]["$ref"], "#/components/schemas/MyAnswer")

    def test_frontend_cors_preflight_and_exposed_filename(self):
        response = self.client.options(
            "/api/polls",
            HTTP_ORIGIN="http://localhost:5173",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization,content-type",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Access-Control-Allow-Origin"], "http://localhost:5173")
        self.assertEqual(response["Access-Control-Allow-Credentials"], "true")
        response = self.client.get("/api/health", HTTP_ORIGIN="http://localhost:5173")
        self.assertIn("content-disposition", response["Access-Control-Expose-Headers"].lower())

    def test_download_accept_headers_work_for_generated_clients_and_swagger(self):
        poll = self.client.post(
            "/api/polls",
            {
                "title": "Download",
                "questions": [
                    {
                        "text": "Question",
                        "type": "single",
                        "options": [{"text": "A"}, {"text": "B"}],
                    }
                ],
            },
        ).data
        for format, mime in [
            ("csv", "text/csv"),
            ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ("pdf", "application/pdf"),
        ]:
            response = self.client.get(f"/api/polls/{poll['slug']}/export?format={format}", HTTP_ACCEPT=mime)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response["Content-Type"].startswith(mime))
        self.client.force_authenticate(User.objects.create_user("other@example.test", "Another", PASSWORD))
        response = self.client.get(
            f"/api/polls/{poll['slug']}/export?format=pdf", HTTP_ACCEPT="application/pdf"
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(response["Content-Type"].startswith("application/json"))


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DemoDataTests(TestCase):
    @override_settings(DEBUG=True)
    def test_demo_is_repeatable_and_login_accounts_have_expected_roles(self):
        call_command("seed_demo", stdout=io.StringIO())
        counts = (User.objects.count(), Poll.objects.count())
        call_command("seed_demo", stdout=io.StringIO())
        self.assertEqual(counts, (User.objects.count(), Poll.objects.count()))
        self.assertEqual(counts, (5, 6))
        for email, nickname, role in ACCOUNTS.values():
            user = User.objects.get(email=email)
            self.assertEqual(user.nickname, nickname)
            self.assertEqual(user.role.name, role)
            self.assertTrue(user.check_password("Demo-Polls-2026!"))

    @override_settings(DEBUG=False)
    def test_demo_is_disabled_in_production(self):
        with self.assertRaises(CommandError):
            call_command("seed_demo", stdout=io.StringIO())
        self.assertEqual(User.objects.count(), 0)

    @override_settings(DEBUG=True)
    def test_demo_does_not_reset_existing_passwords(self):
        call_command("seed_demo", stdout=io.StringIO())
        owner = User.objects.get(email=ACCOUNTS["owner"][0])
        owner.set_password("Changed-by-tester-2031!")
        owner.save(update_fields=["password"])
        call_command("seed_demo", stdout=io.StringIO())
        owner.refresh_from_db()
        self.assertTrue(owner.check_password("Changed-by-tester-2031!"))

    @override_settings(DEBUG=True)
    def test_demo_collision_rolls_back(self):
        role, _ = Role.objects.get_or_create(name="user")
        User.objects.create_user(ACCOUNTS["owner"][0], "ExistingRealUser", PASSWORD, role=role)
        with self.assertRaises(CommandError):
            call_command("seed_demo", stdout=io.StringIO())
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(Poll.objects.count(), 0)
