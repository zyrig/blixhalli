"""Opprett området, organisasjonane og anlegga i data/oppsett.json viss dei ikkje finst.

Endrar aldri noko som alt finst, så endringar gjort i admin blir ikkje overskrivne.
Trygg å køyre ved kvar deploy.
"""
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from bookings.models import Facility, Organization, Workspace


class Command(BaseCommand):
    help = "Opprett området, organisasjonane og anlegga i data/oppsett.json som manglar."

    def handle(self, **options):
        spec = json.loads((Path(settings.BASE_DIR) / "data" / "oppsett.json").read_text(encoding="utf-8"))
        ws = spec["workspace"]
        workspace, created = Workspace.objects.get_or_create(slug=ws["slug"], defaults={"name": ws["name"]})
        if created:
            self.stdout.write(self.style.SUCCESS(f"Oppretta området {workspace}."))
        orgs = {}
        for o in spec["organizations"]:
            orgs[o["slug"]], created = Organization.objects.get_or_create(
                workspace=workspace, slug=o["slug"], defaults={"name": o["name"], "kind": o["kind"]})
            if created:
                self.stdout.write(self.style.SUCCESS(f"Oppretta organisasjonen {orgs[o['slug']]}."))
        for f in spec["facilities"]:
            f = dict(f)
            slug, owner, manager = f.pop("slug"), orgs[f.pop("owner")], orgs[f.pop("manager")]
            facility, created = Facility.objects.get_or_create(
                workspace=workspace, slug=slug, defaults={**f, "owner": owner, "manager": manager})
            if created:
                self.stdout.write(self.style.SUCCESS(f"Oppretta anlegget {facility}."))
