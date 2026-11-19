"""Datamodellar: det vi lagrar i databasen.

Kvar klasse blir ein tabell i databasen. Django lagar og oppdaterer tabellane
via "migrasjonar" (python manage.py makemigrations / migrate).
"""
from django.core.exceptions import ValidationError
from django.db import models

WEEKDAYS = [
    (0, "Måndag"),
    (1, "Tysdag"),
    (2, "Onsdag"),
    (3, "Torsdag"),
    (4, "Fredag"),
    (5, "Laurdag"),
    (6, "Sundag"),
]

# Salen er delt i tre. Ei treningstid brukar éin eller fleire delar ved sida av kvarandre.
SECTIONS = [(1, "1/3"), (2, "2/3"), (3, "3/3")]


class Season(models.Model):
    """Ein sesong, t.d. "2026/2027", med sin eigen vekeplan."""

    name = models.CharField("namn", max_length=50, unique=True)
    start_date = models.DateField("startdato", null=True, blank=True)
    end_date = models.DateField("sluttdato", null=True, blank=True)
    published = models.BooleanField(
        "publisert", default=False,
        help_text="Utkast er berre synlege for dei som er logga inn.",
    )
    notes = models.TextField("merknader", blank=True)

    class Meta:
        ordering = ["-name"]
        verbose_name = "sesong"
        verbose_name_plural = "sesongar"

    def __str__(self):
        return self.name if self.published else f"{self.name} (utkast)"


class Group(models.Model):
    """Ei gruppe som trenar i hallen, t.d. "Handball J13"."""

    CATEGORIES = [
        ("fotball", "Fotball"),
        ("handball", "Handball"),
        ("friidrett", "Friidrett/turn"),
        ("trim", "Trim"),
        ("volleyball", "Volleyball"),
        ("badminton", "Badminton"),
        ("anna", "Anna"),
    ]

    name = models.CharField("namn", max_length=200, unique=True)
    category = models.CharField("kategori", max_length=20, choices=CATEGORIES, default="anna")
    contact = models.CharField("kontaktperson", max_length=200, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "gruppe"
        verbose_name_plural = "grupper"

    def __str__(self):
        return self.name

    @staticmethod
    def guess_category(name):
        """Gjett kategori ut frå det første sportsordet i namnet."""
        keywords = {
            "fotball": "fotball", "handball": "handball", "friidrett": "friidrett", "turn": "friidrett",
            "volleyball": "volleyball", "badminton": "badminton", "trim": "trim", "zumba": "trim",
        }
        lower = name.lower()
        found = [(lower.index(k), cat) for k, cat in keywords.items() if k in lower]
        return min(found)[1] if found else "anna"


class TrainingSlot(models.Model):
    """Ei fast treningstid kvar veke: ei gruppe brukar ein del av salen på ein vekedag."""

    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="slots", verbose_name="sesong")
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="slots", verbose_name="gruppe")
    weekday = models.IntegerField("vekedag", choices=WEEKDAYS)
    start_time = models.TimeField("frå")
    end_time = models.TimeField("til")
    first_section = models.IntegerField("frå del", choices=SECTIONS, default=1)
    last_section = models.IntegerField("til del", choices=SECTIONS, default=3)
    valid_from = models.DateField("gjeld frå", null=True, blank=True, help_text="Tomt = heile sesongen.")
    valid_to = models.DateField("gjeld til", null=True, blank=True, help_text="Tomt = heile sesongen.")
    tentative = models.BooleanField("ikkje avklart", default=False, help_text="Forslag eller usikker tid.")
    note = models.CharField("merknad", max_length=200, blank=True)

    class Meta:
        ordering = ["season", "weekday", "start_time", "first_section"]
        verbose_name = "treningstid"
        verbose_name_plural = "treningstider"

    def __str__(self):
        return f"{self.group}, {self.get_weekday_display()} {self.start_time:%H:%M}–{self.end_time:%H:%M}"

    @property
    def sections_label(self):
        if self.first_section == 1 and self.last_section == 3:
            return "Heile salen"
        if self.first_section == self.last_section:
            return f"{self.first_section}/3"
        return f"{self.first_section}/3–{self.last_section}/3"

    def clean(self):
        """Reglar som blir sjekka før lagring (i skjema og admin)."""
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError("Sluttid må vere etter starttid.")
        if self.first_section and self.last_section and self.last_section < self.first_section:
            raise ValidationError("«Til del» kan ikkje vere før «frå del».")
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValidationError("«Gjeld til» kan ikkje vere før «gjeld frå».")

        clash = self.find_clash()
        if clash:
            raise ValidationError(f"Kolliderer med: {clash} ({clash.sections_label})")

    def find_clash(self):
        """Finn ei anna tid som brukar same del av salen samstundes, om det finst."""
        if not (self.season_id and self.start_time and self.end_time):
            return None
        candidates = TrainingSlot.objects.filter(
            season_id=self.season_id,
            weekday=self.weekday,
            start_time__lt=self.end_time,
            end_time__gt=self.start_time,
            first_section__lte=self.last_section,
            last_section__gte=self.first_section,
        ).exclude(pk=self.pk)
        for other in candidates:
            if self._dates_overlap(other):
                return other
        return None

    def _dates_overlap(self, other):
        a_from, a_to = self.valid_from, self.valid_to
        b_from, b_to = other.valid_from, other.valid_to
        if a_to and b_from and a_to < b_from:
            return False
        if b_to and a_from and b_to < a_from:
            return False
        return True
