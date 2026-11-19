"""Opprett anlegga i data/anlegg.json viss dei ikkje finst.

Endrar aldri eit anlegg som alt finst, så endringar gjort i admin blir ikkje overskrivne.
Trygg å køyre ved kvar deploy.
"""
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from bookings.models import Facility


class Command(BaseCommand):
    help = "Opprett anlegga i data/anlegg.json som manglar."

    def handle(self, **options):
        path = Path(settings.BASE_DIR) / "data" / "anlegg.json"
        for spec in json.loads(path.read_text(encoding="utf-8")):
            slug = spec.pop("slug")
            facility, created = Facility.objects.get_or_create(slug=slug, defaults=spec)
            if created:
                self.stdout.write(self.style.SUCCESS(f"Oppretta anlegget {facility}."))
