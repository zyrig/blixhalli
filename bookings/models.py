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

RESERVED_SLUGS = {"admin", "mine", "inviter", "be-om-brukar", "logg-inn", "logg-ut", "passord", "avlys",
                  "avlysing", "enkelttid", "static", "veke", "sesong", "soknader", "soknad", "sok", "eksport"}


def validate_facility_slug(value):
    if value in RESERVED_SLUGS:
        raise ValidationError(f"«{value}» er reservert. Vel eit anna namn i adressa.")


class Workspace(models.Model):
    """Eit område med eigne anlegg og organisasjonar, t.d. «Vik». Seinare: vik.treningstider.no."""

    name = models.CharField("namn", max_length=100)
    slug = models.SlugField("kortnamn", unique=True, help_text="Brukt i adressa, t.d. «vik» → vik.treningstider.no.")
    domain = models.CharField("eige domene", max_length=200, blank=True,
                              help_text="Valfritt, t.d. treningstider.vikil.no. Må òg leggjast til hos Vercel.")

    class Meta:
        ordering = ["name"]
        verbose_name = "område"
        verbose_name_plural = "område"

    def __str__(self):
        return self.name


def default_workspace():
    """Området som blir brukt når ingenting anna er valt (det første, eller «Vik»)."""
    workspace = Workspace.objects.first()
    if workspace is None:
        workspace = Workspace.objects.create(name="Vik", slug="vik")
    return workspace


class Organization(models.Model):
    """Ein organisasjon i området: kommunen, eit idrettslag eller ein annan leigetakar (t.d. Vik fengsel)."""

    KOMMUNE, IDRETTSLAG, ANNA = "kommune", "idrettslag", "anna"
    KINDS = [(KOMMUNE, "Kommune"), (IDRETTSLAG, "Idrettslag"), (ANNA, "Anna organisasjon")]

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="organizations",
                                  verbose_name="område")
    name = models.CharField("namn", max_length=150)
    slug = models.SlugField("kortnamn")
    kind = models.CharField("type", max_length=12, choices=KINDS, default=IDRETTSLAG)
    admins = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="admin_of",
                                    verbose_name="administratorar",
                                    help_text="Kan godkjenne søknader og administrere organisasjonen sine lag og anlegg.")
    contact_email = models.EmailField("e-post", blank=True)

    class Meta:
        ordering = ["workspace", "kind", "name"]
        constraints = [models.UniqueConstraint(fields=["workspace", "slug"], name="unique_org_slug_per_workspace")]
        verbose_name = "organisasjon"
        verbose_name_plural = "organisasjonar"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.workspace_id is None:
            self.workspace = default_workspace()
        super().save(*args, **kwargs)


def default_organization(workspace=None):
    """Organisasjonen som blir brukt når ingenting anna er valt: første idrettslag, eller «Vik IL»."""
    workspace = workspace or default_workspace()
    orgs = Organization.objects.filter(workspace=workspace)
    org = orgs.filter(kind=Organization.IDRETTSLAG).first() or orgs.first()
    if org is None:
        org = Organization.objects.create(workspace=workspace, name="Vik IL", slug="vikil",
                                          kind=Organization.IDRETTSLAG)
    return org


class Facility(models.Model):
    """Eit anlegg, t.d. Blixhalli eller ei fotballbane. Kvart anlegg er delt i éin eller fleire delar."""

    HALL, PITCH = "hall", "bane"
    KINDS = [(HALL, "Hall"), (PITCH, "Bane ute")]

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="facilities",
                                  verbose_name="område")
    owner = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="owned_facilities",
                              verbose_name="eigar", help_text="Eigaren sine administratorar kan overstyre alt på anlegget.")
    manager = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="managed_facilities",
                                verbose_name="fordeler tid",
                                help_text="Organisasjonen som tildeler tid på anlegget, t.d. kommunen for hallen "
                                          "eller idrettslaget for banane.")
    name = models.CharField("namn", max_length=100)
    slug = models.SlugField("adresse", validators=[validate_facility_slug],
                            help_text="Brukt i nettadressa, t.d. «blixhalli» → /blixhalli/.")
    kind = models.CharField("type", max_length=10, choices=KINDS, default=HALL)
    section_labels = models.CharField(
        "delar", max_length=200, default="1/3,2/3,3/3",
        help_text="Namna på delane, skilde med komma, frå venstre mot høgre. "
                  "T.d. «1/3,2/3,3/3» for ein hall delt i tre, eller «A,B» for ei bane delt i to. "
                  "Ei tid kan bruke fleire delar som ligg ved sida av kvarandre.",
    )
    units = models.TextField(
        "kva som kan bookast", blank=True,
        help_text="Éi linje per storleik: «storleik: delar». Bruk bindestrek for fleire delar saman. Døme:<br>"
                  "<code>1/1: A-D</code><br><code>1/2: A-B, C-D</code><br><code>1/4: A, B, C, D</code><br>"
                  "Tomt = alle delar som ligg ved sida av kvarandre kan bookast.",
    )
    order = models.PositiveSmallIntegerField("rekkjefølgje", default=0)

    class Meta:
        ordering = ["order", "name"]
        constraints = [models.UniqueConstraint(fields=["workspace", "slug"], name="unique_facility_slug_per_workspace")]
        verbose_name = "anlegg"
        verbose_name_plural = "anlegg"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.workspace_id is None:
            self.workspace = (self.manager.workspace if self.manager_id else default_workspace())
        if self.manager_id is None:
            self.manager = self.owner if self.owner_id else default_organization(self.workspace)
        if self.owner_id is None:
            self.owner = self.manager
        super().save(*args, **kwargs)

    @property
    def labels(self):
        return [label.strip() for label in self.section_labels.split(",") if label.strip()] or ["Heile"]

    @property
    def sections(self):
        """[(1, "1/3"), (2, "2/3"), ...]"""
        return list(enumerate(self.labels, start=1))

    @property
    def section_count(self):
        return len(self.labels)

    @property
    def whole_label(self):
        return "Heile salen" if self.kind == self.HALL else "Heile bana"

    def clean(self):
        try:
            self.unit_options()
        except ValueError as e:
            raise ValidationError({"units": str(e)})

    def _parse_units(self):
        """Les «kva som kan bookast» → [("1/2", [(1, 2), (3, 4)]), ...]."""
        index = {label.lower(): n for n, label in self.sections}
        result = []
        for line in self.units.splitlines():
            if not line.strip():
                continue
            if ":" not in line:
                raise ValueError(f"Manglar kolon i linja «{line.strip()}».")
            size, items = line.split(":", 1)
            ranges = []
            for item in items.split(","):
                item = item.strip()
                if not item:
                    continue
                parts = [p.strip().lower() for p in item.split("-")]
                if any(p not in index for p in parts) or len(parts) > 2:
                    raise ValueError(f"Ukjend del i «{item}». Delane heiter: {', '.join(self.labels)}.")
                first, last = index[parts[0]], index[parts[-1]]
                if last < first:
                    raise ValueError(f"«{item}» må gå frå venstre mot høgre.")
                ranges.append((first, last))
            result.append((size.strip(), ranges))
        return result

    def unit_options(self):
        """Alt som kan bookast, gruppert etter storleik: [("1/2 bane", [(1, 2, "A + B"), ...]), ...]."""
        if self.units.strip():
            groups = self._parse_units()
        else:
            n = self.section_count
            groups = [(f"{k}/{n}" if k < n else "1/1", [(i, i + k - 1) for i in range(1, n - k + 2)])
                      for k in range(n, 0, -1)]
        noun = "sal" if self.kind == self.HALL else "bane"
        options = []
        for size, ranges in groups:
            items = []
            for first, last in ranges:
                if first == 1 and last == self.section_count:
                    label = self.whole_label
                else:
                    label = " + ".join(self.labels[first - 1:last])
                items.append((first, last, label))
            options.append((self.whole_label if size == "1/1" else f"{size} {noun}", items))
        return options

    def allows(self, first, last):
        return any((first, last) == (f, l) for _, items in self.unit_options() for f, l, _ in items)

    def sections_label(self, first, last):
        if first == 1 and last == self.section_count:
            return self.whole_label
        labels = self.labels
        parts = labels[first - 1] if first == last else f"{labels[first - 1]}–{labels[last - 1]}"
        if self.units.strip():
            for size, items in self.unit_options():
                if any((first, last) == (f, l) for f, l, _ in items):
                    return f"{size.split()[0]} ({parts})"
        return parts


def default_facility():
    """Anlegget som blir brukt når ingenting anna er valt (det første, eller Blixhalli).

    Blir brukt når ein sesong eller ei enkelttid blir lagra utan anlegg, t.d. ved import.
    """
    facility = Facility.objects.first()
    if facility is None:
        facility = Facility.objects.create(name="Blixhalli", slug="blixhalli")
    return facility.pk


def validate_sections(facility, first, last):
    if first and last and last < first:
        raise ValidationError("«Til del» kan ikkje vere før «frå del».")
    if facility and last and last > facility.section_count:
        raise ValidationError(f"{facility} har berre {facility.section_count} delar.")
    if facility and first and last and not facility.allows(first, last):
        raise ValidationError(f"Denne delen av {facility} kan ikkje bookast åleine. "
                              f"Vel mellom: {', '.join(label for _, items in facility.unit_options() for *_, label in items)}.")


def ranges_overlap(a_from, a_to, b_from, b_to):
    """Overlappar to datoperiodar? None = ope i den enden."""
    if a_to and b_from and a_to < b_from:
        return False
    if b_to and a_from and b_to < a_from:
        return False
    return True


class Season(models.Model):
    """Ein sesong, t.d. "2026/2027", med sin eigen vekeplan."""

    facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name="seasons", verbose_name="anlegg")
    name = models.CharField("namn", max_length=50)
    start_date = models.DateField("startdato", null=True, blank=True)
    end_date = models.DateField("sluttdato", null=True, blank=True)
    published = models.BooleanField(
        "publisert", default=False,
        help_text="Utkast er berre synlege for dei som er logga inn.",
    )
    notes = models.TextField("merknader", blank=True)

    class Meta:
        ordering = ["facility", "-name"]
        constraints = [models.UniqueConstraint(fields=["facility", "name"], name="unique_season_per_facility")]
        verbose_name = "sesong"
        verbose_name_plural = "sesongar"

    def __str__(self):
        return self.name if self.published else f"{self.name} (utkast)"

    def save(self, *args, **kwargs):
        if self.facility_id is None:
            self.facility_id = default_facility()
        super().save(*args, **kwargs)

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
        return f"{self.facility.slug}-sesong-{self.name.replace('/', '-')}.html"


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

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="groups",
                                     verbose_name="organisasjon")
    name = models.CharField("namn", max_length=200)
    category = models.CharField("kategori", max_length=20, choices=CATEGORIES, default="anna")
    contact = models.CharField("kontaktperson", max_length=200, blank=True)
    leaders = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="led_groups", verbose_name="lagleiarar",
        help_text="Brukarar som kan søkje om tider for denne gruppa.",
    )

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["organization", "name"], name="unique_group_name_per_org")]
        verbose_name = "lag"
        verbose_name_plural = "lag"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.organization_id is None:
            self.organization = default_organization()
        super().save(*args, **kwargs)

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
    """Ei fast treningstid kvar veke i ein periode: ei gruppe brukar ein del av eit anlegg på ein vekedag."""

    facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name="slots", verbose_name="anlegg")
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="slots", verbose_name="sesong",
                               null=True, blank=True, help_text="Valfritt. Brukt for importerte sesongplanar.")
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="slots", verbose_name="gruppe")
    weekday = models.IntegerField("vekedag", choices=WEEKDAYS)
    start_time = models.TimeField("frå")
    end_time = models.TimeField("til")
    first_section = models.PositiveSmallIntegerField("frå del", default=1, help_text="1 = delen lengst til venstre.")
    last_section = models.PositiveSmallIntegerField("til del", default=3)
    valid_from = models.DateField("gjeld frå", null=True, blank=True, help_text="Startdato. Tomt = heile sesongen.")
    valid_to = models.DateField("gjeld til", null=True, blank=True, help_text="Sluttdato. Tomt = heile sesongen.")
    tentative = models.BooleanField("ikkje avklart", default=False, help_text="Forslag eller usikker tid.")
    note = models.CharField("merknad", max_length=200, blank=True)

    class Meta:
        ordering = ["facility", "weekday", "start_time", "first_section"]
        verbose_name = "fast treningstid"
        verbose_name_plural = "faste treningstider"

    def __str__(self):
        return f"{self.group}, {self.get_weekday_display()} {self.start_time:%H:%M}–{self.end_time:%H:%M}"

    def clean_fields(self, exclude=None):
        if self.facility_id is None and self.season_id:
            self.facility_id = self.season.facility_id
        super().clean_fields(exclude=exclude)

    def save(self, *args, **kwargs):
        if self.facility_id is None and self.season_id:
            self.facility_id = self.season.facility_id
        super().save(*args, **kwargs)

    @property
    def sections_label(self):
        return self.facility.sections_label(self.first_section, self.last_section)

    def clean(self):
        """Reglar som blir sjekka før lagring (i skjema og admin)."""
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError("Sluttid må vere etter starttid.")
        validate_sections(self.facility if self.facility_id else None, self.first_section, self.last_section)
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValidationError("«Gjeld til» kan ikkje vere før «gjeld frå».")

        clash = self.find_clash()
        if clash:
            raise ValidationError(f"Kolliderer med: {clash} ({clash.sections_label})")

    def effective_range(self):
        """Perioden tida faktisk gjeld: gjeld frå/til, avgrensa av sesongen viss ho har ein."""
        start, end = self.valid_from, self.valid_to
        if self.season_id:
            s_start, s_end = self.season.date_range()
            start = max(d for d in (start, s_start) if d) if (start or s_start) else None
            end = min(d for d in (end, s_end) if d) if (end or s_end) else None
        return start, end

    def is_active_on(self, date):
        """Trenar laget på denne tida den aktuelle datoen (før avlysingar)?"""
        start, end = self.effective_range()
        return date.weekday() == self.weekday and (start is None or start <= date) and (end is None or date <= end)

    def find_clash(self):
        """Finn noko anna som brukar same del av anlegget samstundes i perioden, om det finst."""
        if not (self.facility_id and self.start_time and self.end_time and self.weekday is not None):
            return None
        start, end = self.effective_range()
        org = self.group.organization if self.group_id else None
        return find_recurring_clash(self.facility, self.weekday, self.start_time, self.end_time,
                                    self.first_section, self.last_section, start, end, exclude_slot=self.pk,
                                    organization=org)


class AccountRequest(models.Model):
    """Ein trenar eller lagleiar som ber om brukar. Administrator godkjenner."""

    PENDING, APPROVED, REJECTED = "pending", "approved", "rejected"
    STATUSES = [(PENDING, "Ventar"), (APPROVED, "Godkjend"), (REJECTED, "Avslått")]

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="account_requests",
                                  verbose_name="område")
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

    def save(self, *args, **kwargs):
        if self.workspace_id is None:
            self.workspace = default_workspace()
        super().save(*args, **kwargs)


def overlapping(queryset, start_time, end_time, first_section, last_section):
    """Avgrens til tider som overlappar i klokkeslett og del av salen."""
    return queryset.filter(
        start_time__lt=end_time, end_time__gt=start_time,
        first_section__lte=last_section, last_section__gte=first_section,
    )


def find_clash_on_date(facility, date, start_time, end_time, first_section, last_section, exclude_booking=None,
                       organization=None):
    """Finn kva som eventuelt opptek denne delen av anlegget på denne datoen.

    Ser på faste tider (som ikkje er avlyste den dagen), enkelttider, og blokker som er tildelte
    andre organisasjonar enn `organization`.
    """
    slots = overlapping(TrainingSlot.objects.filter(facility=facility, weekday=date.weekday()),
                        start_time, end_time, first_section, last_section).select_related("season", "facility", "group")
    cancelled = set(Cancellation.objects.filter(date=date).values_list("slot_id", flat=True))
    for slot in slots:
        if slot.is_active_on(date) and slot.pk not in cancelled:
            return slot
    bookings = overlapping(Booking.objects.filter(facility=facility, date=date, status__in=Booking.BLOCKING),
                           start_time, end_time, first_section, last_section)
    if exclude_booking:
        bookings = bookings.exclude(pk=exclude_booking)
    booking = bookings.select_related("group", "facility").first()
    if booking:
        return booking
    if organization is not None:
        return other_org_allocation(facility, organization, date.weekday(), start_time, end_time,
                                    first_section, last_section, date, date)
    return None


def find_recurring_clash(facility, weekday, start_time, end_time, first_section, last_section,
                         date_from, date_to, exclude_slot=None, organization=None, for_allocation=False,
                         exclude_allocation=None):
    """Finn noko som kolliderer med ei fast tid (eller ei tildelt blokk) i perioden date_from–date_to.

    - Faste tider og enkelttider kolliderer alltid. For ei blokk (for_allocation) gjeld det berre
      tider til andre organisasjonar, sidan organisasjonen sine eigne lag skal trene inne i blokka.
    - Blokker tildelte andre organisasjonar enn `organization` kolliderer.
    """
    slots = overlapping(TrainingSlot.objects.filter(facility=facility, weekday=weekday),
                        start_time, end_time, first_section, last_section).select_related("season", "group", "facility")
    if exclude_slot:
        slots = slots.exclude(pk=exclude_slot)
    if for_allocation and organization is not None:
        slots = slots.exclude(group__organization=organization)
    for other in slots:
        if ranges_overlap(date_from, date_to, *other.effective_range()):
            return other
    bookings = overlapping(Booking.objects.filter(facility=facility, status__in=Booking.BLOCKING),
                           start_time, end_time, first_section, last_section).select_related("group", "facility")
    if for_allocation and organization is not None:
        bookings = bookings.exclude(group__organization=organization)
    if date_from:
        bookings = bookings.filter(date__gte=date_from)
    if date_to:
        bookings = bookings.filter(date__lte=date_to)
    for b in bookings:
        if b.date.weekday() == weekday:
            return b
    if organization is not None:
        return other_org_allocation(facility, organization, weekday, start_time, end_time, first_section,
                                    last_section, date_from, date_to, exclude=exclude_allocation)
    return None


def other_org_allocation(facility, organization, weekday, start_time, end_time, first_section, last_section,
                         date_from, date_to, exclude=None):
    """Ei blokk som er tildelt ein annan organisasjon og overlappar, om det finst."""
    allocations = overlapping(Allocation.objects.filter(facility=facility, weekday=weekday),
                              start_time, end_time, first_section, last_section).exclude(organization=organization)
    if exclude:
        allocations = allocations.exclude(pk=exclude)
    for a in allocations.select_related("organization", "facility"):
        if ranges_overlap(date_from, date_to, a.valid_from, a.valid_to):
            return a
    return None


class Allocation(models.Model):
    """Ei blokk som anlegget sin fordelar tildeler ein organisasjon, t.d. kommunen gir Vik IL
    «måndag 17–21, heile salen». Organisasjonen fordeler så blokka vidare til laga sine."""

    facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name="allocations",
                                 verbose_name="anlegg")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="allocations",
                                     verbose_name="tildelt")
    weekday = models.IntegerField("vekedag", choices=WEEKDAYS)
    start_time = models.TimeField("frå")
    end_time = models.TimeField("til")
    first_section = models.PositiveSmallIntegerField("frå del", default=1)
    last_section = models.PositiveSmallIntegerField("til del", default=1)
    valid_from = models.DateField("gjeld frå", null=True, blank=True)
    valid_to = models.DateField("gjeld til", null=True, blank=True)
    note = models.CharField("merknad", max_length=200, blank=True)

    class Meta:
        ordering = ["facility", "weekday", "start_time"]
        verbose_name = "tildelt blokk"
        verbose_name_plural = "tildelte blokker"

    def __str__(self):
        return (f"{self.organization}: {self.get_weekday_display()} {self.start_time:%H:%M}–{self.end_time:%H:%M}"
                f" ({self.facility} {self.sections_label})")

    @property
    def sections_label(self):
        return self.facility.sections_label(self.first_section, self.last_section)

    def is_active_on(self, date):
        return (date.weekday() == self.weekday and (self.valid_from is None or self.valid_from <= date)
                and (self.valid_to is None or date <= self.valid_to))

    def covers(self, weekday, start_time, end_time, first_section, last_section, date_from, date_to):
        """Ligg heile tida inne i blokka?"""
        return (weekday == self.weekday and self.start_time <= start_time and end_time <= self.end_time
                and self.first_section <= first_section and last_section <= self.last_section
                and (self.valid_from is None or (date_from is not None and self.valid_from <= date_from))
                and (self.valid_to is None or (date_to is not None and date_to <= self.valid_to)))

    def clean(self):
        validate_period(self.start_time, self.end_time, self.valid_from, self.valid_to)
        if self.facility_id:
            if self.last_section and self.last_section > self.facility.section_count:
                raise ValidationError(f"{self.facility} har berre {self.facility.section_count} delar.")
            if self.first_section and self.last_section and self.last_section < self.first_section:
                raise ValidationError("«Til del» kan ikkje vere før «frå del».")
        if self.facility_id and self.organization_id and self.start_time and self.end_time:
            clash = find_recurring_clash(self.facility, self.weekday, self.start_time, self.end_time,
                                         self.first_section, self.last_section, self.valid_from, self.valid_to,
                                         organization=self.organization, for_allocation=True,
                                         exclude_allocation=self.pk)
            if clash:
                raise ValidationError(f"Kolliderer med: {clash}")


def find_covering_allocation(organization, facility, weekday, start_time, end_time, first_section, last_section,
                             date_from, date_to):
    for a in Allocation.objects.filter(organization=organization, facility=facility, weekday=weekday):
        if a.covers(weekday, start_time, end_time, first_section, last_section, date_from, date_to):
            return a
    return None


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
        return overlapping(Booking.objects.filter(facility=s.facility, date=self.date,
                                                  status__in=Booking.BLOCKING),
                           s.start_time, s.end_time, s.first_section, s.last_section).first()


class Booking(models.Model):
    """Ei enkelttid på ein bestemt dato, t.d. ekstratrening, kamp eller utleige."""

    PENDING, APPROVED, REJECTED = "pending", "approved", "rejected"
    STATUSES = [(PENDING, "Ventar"), (APPROVED, "Godkjend"), (REJECTED, "Avslått")]
    BLOCKING = [PENDING, APPROVED]  # desse opptek plassen

    facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name="bookings", verbose_name="anlegg")
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="bookings", verbose_name="gruppe")
    date = models.DateField("dato")
    start_time = models.TimeField("frå")
    end_time = models.TimeField("til")
    first_section = models.PositiveSmallIntegerField("frå del", default=1)
    last_section = models.PositiveSmallIntegerField("til del", default=3)
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

    @property
    def sections_label(self):
        return self.facility.sections_label(self.first_section, self.last_section)

    def save(self, *args, **kwargs):
        if self.facility_id is None:
            self.facility_id = default_facility()
        super().save(*args, **kwargs)

    def clean(self):
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError("Sluttid må vere etter starttid.")
        validate_sections(self.facility if self.facility_id else None, self.first_section, self.last_section)
        if self.facility_id and self.date and self.start_time and self.end_time and self.status in self.BLOCKING:
            clash = find_clash_on_date(self.facility, self.date, self.start_time, self.end_time,
                                       self.first_section, self.last_section, exclude_booking=self.pk,
                                       organization=self.group.organization if self.group_id else None)
            if clash:
                raise ValidationError(f"Opptatt: {clash} ({clash.sections_label}).")


class TrainingRequest(models.Model):
    """Ein lagleiar søkjer om ei fast treningstid. Administrator godkjenner, avslår eller føreslår anna tid."""

    PENDING, PROPOSED, APPROVED, REJECTED, DECLINED, WITHDRAWN = (
        "pending", "proposed", "approved", "rejected", "declined", "withdrawn")
    STATUSES = [
        (PENDING, "Ventar på administrator"),
        (PROPOSED, "Administrator har føreslått anna tid"),
        (APPROVED, "Godkjend"),
        (REJECTED, "Avslått"),
        (DECLINED, "Forslaget vart ikkje godteke"),
        (WITHDRAWN, "Trekt"),
    ]
    OPEN = [PENDING, PROPOSED]

    facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name="requests", verbose_name="anlegg")
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="requests", verbose_name="lag")
    weekday = models.IntegerField("vekedag", choices=WEEKDAYS)
    start_time = models.TimeField("frå klokka")
    end_time = models.TimeField("til klokka")
    first_section = models.PositiveSmallIntegerField("frå del", default=1)
    last_section = models.PositiveSmallIntegerField("til del", default=1)
    valid_from = models.DateField("startdato")
    valid_to = models.DateField("sluttdato")
    message = models.TextField("melding til administrator", blank=True)
    status = models.CharField("status", max_length=10, choices=STATUSES, default=PENDING)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
                                   related_name="training_requests", verbose_name="søkt av")
    created_at = models.DateTimeField("søkt", auto_now_add=True)
    handled_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+", verbose_name="handsama av")
    handled_at = models.DateTimeField("handsama", null=True, blank=True)
    admin_comment = models.TextField("kommentar frå administrator", blank=True)
    slot = models.ForeignKey(TrainingSlot, null=True, blank=True, on_delete=models.SET_NULL,
                             related_name="requests", verbose_name="fast tid")
    # Forslag frå administrator (når status er «proposed»)
    proposed_weekday = models.IntegerField("føreslått vekedag", choices=WEEKDAYS, null=True, blank=True)
    proposed_start_time = models.TimeField("føreslått frå", null=True, blank=True)
    proposed_end_time = models.TimeField("føreslått til", null=True, blank=True)
    proposed_first_section = models.PositiveSmallIntegerField(null=True, blank=True)
    proposed_last_section = models.PositiveSmallIntegerField(null=True, blank=True)
    proposed_valid_from = models.DateField("føreslått startdato", null=True, blank=True)
    proposed_valid_to = models.DateField("føreslått sluttdato", null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "søknad om fast tid"
        verbose_name_plural = "søknader om faste tider"

    def __str__(self):
        return f"{self.group}: {self.summary()}"

    def summary(self, proposed=False):
        d = self.proposal() if proposed else self.wanted()
        return (f"{dict(WEEKDAYS)[d['weekday']]} {d['start_time']:%H:%M}–{d['end_time']:%H:%M}, "
                f"{self.facility} {self.facility.sections_label(d['first_section'], d['last_section'])}, "
                f"{d['valid_from']:%d.%m.%Y}–{d['valid_to']:%d.%m.%Y}")

    @property
    def summary_proposed(self):
        return self.summary(proposed=True) if self.proposed_weekday is not None else ""

    def wanted(self):
        return {f: getattr(self, f) for f in ("weekday", "start_time", "end_time", "first_section",
                                              "last_section", "valid_from", "valid_to")}

    def proposal(self):
        return {f: getattr(self, "proposed_" + f) for f in ("weekday", "start_time", "end_time", "first_section",
                                                            "last_section", "valid_from", "valid_to")}

    @property
    def sections_label(self):
        return self.facility.sections_label(self.first_section, self.last_section)

    def clean(self):
        validate_period(self.start_time, self.end_time, self.valid_from, self.valid_to)
        validate_sections(self.facility if self.facility_id else None, self.first_section, self.last_section)

    def find_clash(self, proposed=False):
        d = self.proposal() if proposed else self.wanted()
        return find_recurring_clash(self.facility, d["weekday"], d["start_time"], d["end_time"],
                                    d["first_section"], d["last_section"], d["valid_from"], d["valid_to"],
                                    organization=self.group.organization)

    def build_slot(self, proposed=False):
        d = self.proposal() if proposed else self.wanted()
        return TrainingSlot(facility=self.facility, group=self.group, note="", **d)


def validate_period(start_time, end_time, valid_from, valid_to):
    if start_time and end_time and end_time <= start_time:
        raise ValidationError("Sluttid må vere etter starttid.")
    if valid_from and valid_to and valid_to < valid_from:
        raise ValidationError("Sluttdato kan ikkje vere før startdato.")
