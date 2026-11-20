import asyncio
from http.cookies import SimpleCookie

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth.models import AnonymousUser
from django.http import HttpRequest
from rest_framework.exceptions import APIException
from rest_framework.request import Request

from .auth import authenticate_access
from .models import Poll
from .services import require_results, results


class ResultsConsumer(AsyncJsonWebsocketConsumer):
    """Authenticate with subprotocols ['polls', 'bearer.<access>']; never log JWT in URLs."""

    @database_sync_to_async
    def authorized_poll(self):
        if self.access:
            user, _ = authenticate_access(self.access)
        else:
            user = AnonymousUser()
        cookies = SimpleCookie()
        cookies.load(dict(self.scope.get("headers", [])).get(b"cookie", b"").decode("latin1"))
        raw = HttpRequest()
        raw.method = "GET"
        raw.COOKIES = {key: value.value for key, value in cookies.items()}
        request = Request(raw)
        request.user = user
        poll = Poll.objects.get(slug=self.scope["url_route"]["kwargs"]["slug"])
        require_results(poll, request)
        return poll

    async def connect(self):
        self.poll_id = None
        self.guard_task = None
        self.access = next(
            (
                p.removeprefix("bearer.")
                for p in self.scope.get("subprotocols", [])
                if p.startswith("bearer.")
            ),
            None,
        )
        try:
            poll = await self.authorized_poll()
        except (APIException, Poll.DoesNotExist):
            await self.close(code=4403)
            return
        self.poll_id = poll.pk
        await self.channel_layer.group_add(f"poll.{poll.pk}", self.channel_name)
        await self.accept(subprotocol="polls" if "polls" in self.scope.get("subprotocols", []) else None)
        self.guard_task = asyncio.create_task(self.guard())

    async def guard(self):
        try:
            while True:
                await asyncio.sleep(10)
                try:
                    await self.authorized_poll()
                except (APIException, Poll.DoesNotExist):
                    await self.close(code=4403)
                    return
        except asyncio.CancelledError:
            return

    async def disconnect(self, code):
        if self.guard_task:
            self.guard_task.cancel()
        if self.poll_id:
            await self.channel_layer.group_discard(f"poll.{self.poll_id}", self.channel_name)

    async def poll_event(self, message):
        try:
            poll = await self.authorized_poll()
        except (APIException, Poll.DoesNotExist):
            await self.close(code=4403)
            return
        event = message["event"]
        if event == "results_updated":
            data = await database_sync_to_async(results)(poll)
        elif event == "status_changed":
            data = {
                "status": poll.status,
                "finished_at": poll.finished_at.isoformat() if poll.finished_at else None,
            }
        else:
            return
        await self.send_json({"event": event, "data": data})
