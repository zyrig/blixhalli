"""Lag ein statisk versjon av vekeplanen (berre lesing), t.d. for GitHub Pages.

Bruk:  python manage.py export_static --out site
       python manage.py export_static --out site --include-drafts

Lagar index.html (standardsesongen) og éi side per sesong.
"""
from pathlib import Path

from django.core.management.base import BaseCommand
from django.template.loader import render_to_string

from bookings.models import Facility
from bookings.views import default_season, schedule_context


class Command(BaseCommand):
    help = "Eksporter vekeplanen til statiske HTML-filer."

    def add_arguments(self, parser):
        parser.add_argument("--out", default="site")
        parser.add_argument("--include-drafts", action="store_true", help="Ta med utkast-sesongar.")

    def handle(self, out, include_drafts, **options):
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        pages = 0
        for i, facility in enumerate(Facility.objects.all()):
            seasons = facility.seasons.all() if include_drafts else facility.seasons.filter(published=True)

            def render(season):
                return render_to_string("bookings/schedule.html",
                                        schedule_context(facility, season, seasons, static_export=True))

            for season in seasons:
                (out / season.static_filename).write_text(render(season), encoding="utf-8")
                pages += 1
            front = render(default_season(seasons))
            (out / f"{facility.slug}.html").write_text(front, encoding="utf-8")
            if i == 0:
                (out / "index.html").write_text(front, encoding="utf-8")
        (out / ".nojekyll").write_text("")
        self.stdout.write(self.style.SUCCESS(f"Eksporterte {pages} sesongplan(ar) til {out}/"))
