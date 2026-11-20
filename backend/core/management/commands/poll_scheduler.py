import time
import logging

from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone

from core.models import RefreshToken
from core.services import sync_due_polls


class Command(BaseCommand):
    help = "Publish scheduled polls, close expired polls, and remove expired sessions."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        while True:
            close_old_connections()
            try:
                sync_due_polls()
                RefreshToken.objects.filter(expires_at__lte=timezone.now()).delete()
            except Exception:
                if options["once"]:
                    raise
                logging.getLogger(__name__).exception("Scheduler iteration failed")
            if options["once"]:
                return
            time.sleep(1)
