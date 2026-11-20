from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections, connections
from django.test import TransactionTestCase, override_settings, skipUnlessDBFeature
from rest_framework.test import APIClient

from core.auth import issue_tokens
from core.models import Answer, Option, Poll, Question, Response, Role, User


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PostgreSQLConcurrencyTests(TransactionTestCase):
    def setUp(self):
        role, _ = Role.objects.get_or_create(name="user")
        self.owner = User.objects.create_user("owner@example.com", "Owner", "pass", role=role)
        self.other = User.objects.create_user("other@example.com", "Other", "pass", role=role)

    def race(self, task):
        barrier = Barrier(2)

        def run(index):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return task(index)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            return list(executor.map(run, range(2)))

    @skipUnlessDBFeature("has_select_for_update")
    def test_concurrent_votes_do_not_exceed_limit(self):
        poll = Poll.objects.create(author=self.owner, title="Poll", status="active", max_votes=1)
        q = Question.objects.create(poll=poll, text="?", type="single", position=1)
        o = Option.objects.create(question=q, text="A", position=1)
        data = {"answers": [{"question_id": q.pk, "option_ids": [o.pk]}]}

        def task(i):
            client = APIClient()
            client.force_authenticate([self.owner, self.other][i])
            return client.post(f"/api/polls/{poll.slug}/vote", data, format="json").status_code

        self.assertEqual(sorted(self.race(task)), [200, 403])
        self.assertEqual(Response.objects.count(), 1)
        self.assertEqual(Answer.objects.count(), 1)
        poll.refresh_from_db()
        self.assertEqual(poll.responses_count, 1)
        self.assertEqual(poll.status, "finished")

    @skipUnlessDBFeature("has_select_for_update")
    def test_concurrent_refresh_uses_old_token_once(self):
        pair = issue_tokens(self.owner)

        def task(i):
            return (
                APIClient().post("/api/auth/refresh", {"refresh": pair["refresh"]}, format="json").status_code
            )

        self.assertEqual(sorted(self.race(task)), [200, 401])
        self.assertEqual(self.owner.sessions.count(), 1)
