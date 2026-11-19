"""Importer treningstider frå Excel-arket som har vore brukt til no.

Bruk:  python manage.py import_timeplan Treningstider.xlsx
       python manage.py import_timeplan Treningstider.xlsx --replace   (slettar tidene i sesongen først)

Kvar fane blir ein sesong. Forventa oppsett: rad med "DAG/TID", vekedagar med tre
kolonnar kvar (1/3, 2/3, 3/3), og klokkeslett i kolonne A. Samanslåtte celler
avgjer kor lenge ei tid varer og kor mange delar av salen ho brukar.
"""
import datetime
import re

import openpyxl
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from bookings.models import Facility, Group, Season, TrainingSlot, default_facility

TIME_RE = re.compile(r"^\s*(\d{1,2})(?:[.:](\d{2}))?\s*-\s*(\d{1,2})(?:[.:](\d{2}))?\s*$")
FIRST_DAY_COL = 2  # kolonne B


def parse_time_range(text):
    m = TIME_RE.match(str(text or ""))
    if not m:
        return None
    h1, m1, h2, m2 = m.groups()
    return datetime.time(int(h1), int(m1 or 0)), datetime.time(int(h2), int(m2 or 0))


def clean_name(text):
    text = " ".join(str(text).split())
    tentative = "?" in text or text.lower().startswith("forslag")
    text = re.sub(r"^forslag:\s*", "", text, flags=re.I)
    text = re.sub(r"\(\s*\?\s*\)", "", text).replace("?", "").strip(" -")
    return " ".join(text.split()), tentative


class Command(BaseCommand):
    help = "Importer treningstider frå Excel-fil (ei fane per sesong)."

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--replace", action="store_true", help="Slett eksisterande tider i sesongane først.")
        parser.add_argument("--anlegg", help="Adressa (slug) til anlegget, t.d. blixhalli. Standard: første anlegg.")

    @transaction.atomic
    def handle(self, path, replace, anlegg=None, **options):
        if anlegg:
            try:
                self.facility = Facility.objects.get(slug=anlegg)
            except Facility.DoesNotExist:
                raise CommandError(f"Fann ikkje anlegget «{anlegg}».")
        else:
            self.facility = Facility.objects.get(pk=default_facility())
        try:
            wb = openpyxl.load_workbook(path)
        except Exception as e:  # noqa: BLE001
            raise CommandError(f"Kunne ikkje opne {path}: {e}")
        for ws in wb.worksheets:
            self.import_sheet(ws, replace)

    def import_sheet(self, ws, replace):
        title = str(ws["A1"].value or ws.title)
        m = re.search(r"\d{4}\s*/\s*\d{4}", title)
        season_name = m.group(0).replace(" ", "") if m else ws.title
        draft = "utkast" in ws.title.lower()

        times = {}  # rad -> (start, slutt)
        header_row = None
        notes = []
        for row in range(1, ws.max_row + 1):
            a = ws.cell(row, 1).value
            if a and str(a).strip().upper() == "DAG/TID":
                header_row = row
            parsed = parse_time_range(a)
            if parsed and header_row:
                times[row] = parsed
            elif a and times and row > max(times):
                notes.append(" ".join(str(a).split()))
        if not times:
            self.stdout.write(self.style.WARNING(f"Fana «{ws.title}»: fann ingen klokkeslett, hoppar over."))
            return

        season, created = Season.objects.get_or_create(facility=self.facility, name=season_name,
                                                       defaults={"published": not draft})
        if notes and not season.notes:
            season.notes = "\n".join(notes)
            season.save()
        if replace:
            season.slots.all().delete()

        merged = {(r.min_row, r.min_col): r for r in ws.merged_cells.ranges}
        last_time_row = max(times)
        count = 0
        for row in sorted(times):
            for col in range(FIRST_DAY_COL, FIRST_DAY_COL + 21):
                value = ws.cell(row, col).value
                if not value or not str(value).strip():
                    continue
                rng = merged.get((row, col))
                r1, r2, c1, c2 = (rng.min_row, rng.max_row, rng.min_col, rng.max_col) if rng else (row, row, col, col)
                r2 = min(r2, last_time_row)
                weekday = (c1 - FIRST_DAY_COL) // 3
                first_section = (c1 - FIRST_DAY_COL) % 3 + 1
                # Ei celle kan ikkje strekkje seg over i neste dag.
                last_section = min((c2 - FIRST_DAY_COL) - weekday * 3 + 1, 3)

                name, tentative = clean_name(value)
                group, _ = Group.objects.get_or_create(name=name, defaults={"category": Group.guess_category(name)})
                slot = TrainingSlot(
                    season=season, group=group, weekday=weekday,
                    start_time=times[r1][0], end_time=times[r2][1],
                    first_section=first_section, last_section=last_section, tentative=tentative,
                )
                clash = slot.find_clash()
                if clash:
                    self.stdout.write(self.style.WARNING(f"  Kollisjon, lagra likevel: {slot} ↔ {clash}"))
                slot.save()
                count += 1
        status = "utkast" if not season.published else "publisert"
        self.stdout.write(self.style.SUCCESS(
            f"{self.facility}, sesong {season.name} ({status}): {count} treningstider importert."))
