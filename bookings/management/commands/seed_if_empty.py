"""Fyll ein heilt ny database med tidene frå data/timeplan.json.

Gjer ingenting viss det alt finst sesongar, så han er trygg å køyre ved kvar deploy.
"""
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand

from bookings.models import Season


class Command(BaseCommand):
    help = "Last inn data/timeplan.json viss databasen er tom."

    def handle(self, **options):
        if Season.objects.exists():
            self.stdout.write("Databasen har alt data. Hoppar over.")
            return
        fixture = Path(settings.BASE_DIR) / "data" / "timeplan.json"
        if fixture.exists():
            call_command("loaddata", str(fixture))
            self.stdout.write(self.style.SUCCESS("Lasta inn startdata frå data/timeplan.json."))
