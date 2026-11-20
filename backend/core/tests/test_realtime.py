from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.core import signing
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient

from config.asgi import application
from core.auth import issue_tokens
from core.models import Option, Poll, Question, Response, Role, User


@override_settings(
    ALLOWED_HOSTS=["localhost", "testserver"],
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}},
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class RealtimeTests(TransactionTestCase):
    def setUp(self):
        role, _ = Role.objects.get_or_create(name="user")
        self.owner = User.objects.create_user("owner@example.com", "Owner", "pass", role=role)
        self.member = User.objects.create_user("member@example.com", "Member", "pass", role=role)
        self.tokens = issue_tokens(self.owner)
        self.member_tokens = issue_tokens(self.member)
        self.poll = Poll.objects.create(author=self.owner, title="Опрос", status="active")
        q = Question.objects.create(poll=self.poll, text="Вопрос", type="single", position=1)
        Option.objects.create(question=q, text="A", position=1)
        Option.objects.create(question=q, text="B", position=2)

    def ws(self, token=None, origin=b"http://localhost:5173", cookie=None):
        headers = [(b"origin", origin)]
        if cookie:
            headers.append((b"cookie", cookie.encode()))
        return WebsocketCommunicator(
            application,
            f"/ws/polls/{self.poll.slug}/",
            headers=headers,
            subprotocols=["polls", "bearer." + token] if token else [],
        )

    def test_owner_receives_results_event(self):
        async def scenario():
            ws = self.ws(self.tokens["access"])
            connected, protocol = await ws.connect()
            self.assertTrue(connected)
            self.assertEqual(protocol, "polls")
            await get_channel_layer().group_send(
                f"poll.{self.poll.pk}", {"type": "poll.event", "event": "results_updated"}
            )
            message = await ws.receive_json_from()
            self.assertEqual(message["event"], "results_updated")
            self.assertEqual(message["data"]["total_responses"], 0)
            await ws.disconnect()

        async_to_sync(scenario)()

    def test_nonparticipant_and_guest_rejected(self):
        async def scenario():
            for token in [None, self.member_tokens["access"]]:
                ws = self.ws(token)
                self.assertFalse((await ws.connect())[0])
                await ws.disconnect()

        async_to_sync(scenario)()

    def test_guest_participant_cookie_authorizes_connection(self):
        import uuid

        token = uuid.uuid4()
        Response.objects.create(poll=self.poll, voter_token=token)
        signed = signing.dumps(str(token), salt="polls-guest")

        async def scenario():
            ws = self.ws(cookie="voter_token=" + signed)
            self.assertTrue((await ws.connect())[0])
            await ws.disconnect()

        async_to_sync(scenario)()

    def test_untrusted_origin_rejected(self):
        async def scenario():
            ws = self.ws(self.tokens["access"], origin=b"https://other.example")
            self.assertFalse((await ws.connect())[0])
            await ws.disconnect()

        async_to_sync(scenario)()

    def test_revoked_session_disconnects_before_next_event(self):
        async def scenario():
            ws = self.ws(self.tokens["access"])
            self.assertTrue((await ws.connect())[0])
            await database_sync_to_async(self.owner.sessions.all().delete)()
            await get_channel_layer().group_send(
                f"poll.{self.poll.pk}", {"type": "poll.event", "event": "results_updated"}
            )
            message = await ws.receive_output()
            self.assertEqual(message["type"], "websocket.close")
            self.assertEqual(message["code"], 4403)
            await ws.disconnect()

        async_to_sync(scenario)()

    def test_http_vote_emits_websocket_event_after_commit(self):
        q = self.poll.questions.get()
        data = {"answers": [{"question_id": q.pk, "option_ids": [q.options.first().pk]}]}

        def cast_vote():
            client = APIClient()
            client.force_authenticate(self.member)
            return client.post(f"/api/polls/{self.poll.slug}/vote", data, format="json").status_code

        async def scenario():
            ws = self.ws(self.tokens["access"])
            self.assertTrue((await ws.connect())[0])
            self.assertEqual(await database_sync_to_async(cast_vote)(), 200)
            message = await ws.receive_json_from()
            self.assertEqual(message["data"]["total_responses"], 1)
            await ws.disconnect()

        async_to_sync(scenario)()
