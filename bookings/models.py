"""Datamodellar: det vi lagrar i databasen.

Kvar klasse blir ein tabell i databasen. Django lagar og oppdaterer tabellane
via "migrasjonar" (python manage.py makemigrations / migrate).
"""
import datetime
import re

from django.conf import settings
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

    def date_range(self):
        """Perioden sesongen gjeld. Utan datoar: 1. august–31. juli ut frå namnet («2025/2026»)."""
        start, end = self.start_date, self.end_date
        m = re.match(r"(\d{4})/(\d{4})", self.name)
        if m:
            start = start or datetime.date(int(m[1]), 8, 1)
            end = end or datetime.date(int(m[2]), 7, 31)
        return start, end

    def covers(self, date):
        start, end = self.date_range()
        return (start is None or start <= date) and (end is None or date <= end)

    @property
    def static_filename(self):
        """Filnamn i den statiske versjonen (GitHub Pages)."""
        return f"sesong-{self.name.replace('/', '-')}.html"


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
    leaders = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="led_groups", verbose_name="lagleiarar",
        help_text="Brukarar som kan søkje om tider for denne gruppa.",
    )

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

    def is_active_on(self, date):
        """Trenar laget på denne tida den aktuelle datoen (før avlysingar)?"""
        return (
            date.weekday() == self.weekday
            and self.season.covers(date)
            and (self.valid_from is None or self.valid_from <= date)
            and (self.valid_to is None or date <= self.valid_to)
        )

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


class AccountRequest(models.Model):
    """Ein trenar eller lagleiar som ber om brukar. Administrator godkjenner."""

    PENDING, APPROVED, REJECTED = "pending", "approved", "rejected"
    STATUSES = [(PENDING, "Ventar"), (APPROVED, "Godkjend"), (REJECTED, "Avslått")]

    name = models.CharField("namn", max_length=200)
    email = models.EmailField("e-post")
    phone = models.CharField("telefon", max_length=30, blank=True)
    groups = models.ManyToManyField(Group, blank=True, verbose_name="lag")
    other_group = models.CharField(
        "anna lag", max_length=200, blank=True, help_text="Viss laget ditt ikkje står i lista."
    )
    message = models.TextField("melding", blank=True)
    status = models.CharField("status", max_length=10, choices=STATUSES, default=PENDING)
    created_at = models.DateTimeField("motteke", auto_now_add=True)
    handled_at = models.DateTimeField("handsama", null=True, blank=True)
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", verbose_name="handsama av",
    )
    admin_comment = models.TextField("kommentar frå administrator", blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="account_requests", verbose_name="brukar",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "førespurnad om brukar"
        verbose_name_plural = "førespurnader om brukar"

    def __str__(self):
        return f"{self.name} <{self.email}>"


def overlapping(queryset, start_time, end_time, first_section, last_section):
    """Avgrens til tider som overlappar i klokkeslett og del av salen."""
    return queryset.filter(
        start_time__lt=end_time, end_time__gt=start_time,
        first_section__lte=last_section, last_section__gte=first_section,
    )


def find_clash_on_date(date, start_time, end_time, first_section, last_section, exclude_booking=None):
    """Finn kva som eventuelt opptek denne delen av salen på denne datoen.

    Ser på faste tider (som ikkje er avlyste den dagen) og enkelttider.
    """
    slots = overlapping(TrainingSlot.objects.filter(weekday=date.weekday()), start_time, end_time,
                        first_section, last_section).select_related("season", "group")
    cancelled = set(Cancellation.objects.filter(date=date).values_list("slot_id", flat=True))
    for slot in slots:
        if slot.is_active_on(date) and slot.pk not in cancelled:
            return slot
    bookings = overlapping(Booking.objects.filter(date=date, status__in=Booking.BLOCKING), start_time, end_time,
                           first_section, last_section)
    if exclude_booking:
        bookings = bookings.exclude(pk=exclude_booking)
    return bookings.select_related("group").first()


class Cancellation(models.Model):
    """Ei fast treningstid som ikkje blir brukt ein bestemt dato. Plassen blir då ledig."""

    slot = models.ForeignKey(TrainingSlot, on_delete=models.CASCADE, related_name="cancellations",
                             verbose_name="treningstid")
    date = models.DateField("dato")
    reason = models.CharField("grunn", max_length=200, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+", verbose_name="registrert av")
    created_at = models.DateTimeField("registrert", auto_now_add=True)

    class Meta:
        ordering = ["date", "slot__start_time"]
        constraints = [models.UniqueConstraint(fields=["slot", "date"], name="unique_cancellation")]
        verbose_name = "avlysing"
        verbose_name_plural = "avlysingar"

    def __str__(self):
        return f"{self.slot.group} avlyst {self.date:%d.%m.%Y}"

    def clean(self):
        if self.slot_id and self.date and not self.slot.is_active_on(self.date):
            raise ValidationError(f"{self.slot.group} har ikkje denne treningstida {self.date:%d.%m.%Y}.")

    def blocking_booking(self):
        """Ei enkelttid som har teke plassen etter avlysinga. Då kan avlysinga ikkje angrast."""
        s = self.slot
        return overlapping(Booking.objects.filter(date=self.date, status__in=Booking.BLOCKING),
                           s.start_time, s.end_time, s.first_section, s.last_section).first()


class Booking(models.Model):
    """Ei enkelttid på ein bestemt dato, t.d. ekstratrening, kamp eller utleige."""

    PENDING, APPROVED, REJECTED = "pending", "approved", "rejected"
    STATUSES = [(PENDING, "Ventar"), (APPROVED, "Godkjend"), (REJECTED, "Avslått")]
    BLOCKING = [PENDING, APPROVED]  # desse opptek plassen

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="bookings", verbose_name="gruppe")
    date = models.DateField("dato")
    start_time = models.TimeField("frå")
    end_time = models.TimeField("til")
    first_section = models.IntegerField("frå del", choices=SECTIONS, default=1)
    last_section = models.IntegerField("til del", choices=SECTIONS, default=3)
    note = models.CharField("merknad", max_length=200, blank=True, help_text="T.d. «Kamp mot Sogndal».")
    status = models.CharField("status", max_length=10, choices=STATUSES, default=APPROVED)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+", verbose_name="booka av")
    created_at = models.DateTimeField("booka", auto_now_add=True)

    class Meta:
        ordering = ["date", "start_time"]
        verbose_name = "enkelttid"
        verbose_name_plural = "enkelttider"

    def __str__(self):
        return f"{self.group}, {self.date:%d.%m.%Y} {self.start_time:%H:%M}–{self.end_time:%H:%M}"

    sections_label = TrainingSlot.sections_label

    def clean(self):
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError("Sluttid må vere etter starttid.")
        if self.first_section and self.last_section and self.last_section < self.first_section:
            raise ValidationError("«Til del» kan ikkje vere før «frå del».")
        if self.date and self.start_time and self.end_time and self.status in self.BLOCKING:
            clash = find_clash_on_date(self.date, self.start_time, self.end_time,
                                       self.first_section, self.last_section, exclude_booking=self.pk)
            if clash:
                raise ValidationError(f"Opptatt: {clash} ({clash.sections_label}).")
