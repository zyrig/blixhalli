"""Views: Python-funksjonar som lagar sidene."""
import datetime

from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone

from .models import SECTIONS, WEEKDAYS, Booking, Cancellation, Season, TrainingSlot
from .permissions import can_manage

SLOT_MINUTES = 30
MONTHS = ["jan.", "feb.", "mars", "apr.", "mai", "juni", "juli", "aug.", "sep.", "okt.", "nov.", "des."]


def _minutes(t):
    return t.hour * 60 + t.minute


def visible_seasons(user):
    seasons = Season.objects.all()
    if not (user and user.is_staff):
        seasons = seasons.filter(published=True)
    return seasons


def default_season(seasons):
    return seasons.filter(published=True).first() or seasons.first()


# ---------------------------------------------------------------------------
# Rutenettet: same teikning for sesongplanen og for ei bestemt veke.
# Kvar "entry" er ein rute i rutenettet (ei fast tid, ei avlyst tid eller ei enkelttid).
# ---------------------------------------------------------------------------

def _entry(obj, kind, extra_meta=(), link=None):
    meta = [f"{obj.start_time:%H:%M}–{obj.end_time:%H:%M}", obj.sections_label]
    if getattr(obj, "tentative", False):
        meta.append("ikkje avklart")
    if obj.note:
        meta.append(obj.note)
    meta.extend(extra_meta)
    return {
        "title": obj.group.name, "category": obj.group.category, "kind": kind,
        "start": obj.start_time, "end": obj.end_time,
        "first": obj.first_section, "last": obj.last_section,
        "tentative": getattr(obj, "tentative", False),
        "meta": " · ".join(meta), "link": link,
    }


def _validity(slot):
    parts = []
    if slot.valid_from:
        parts.append(f"frå {slot.valid_from:%-d.%-m.}")
    if slot.valid_to:
        parts.append(f"til {slot.valid_to:%-d.%-m.}")
    return [" ".join(parts)] if parts else []


def build_grid(days):
    """Rekn ut rader og kolonnar i CSS-rutenettet for alle entries."""
    entries = [e for d in days for e in d["entries"]]
    # Rutenettet går frå første til siste heile time som er i bruk (minst 09–22).
    first = min([_minutes(e["start"]) for e in entries] + [9 * 60]) // 60 * 60
    last = -(-max([_minutes(e["end"]) for e in entries] + [22 * 60]) // 60) * 60
    times = [
        {"label": f"{m // 60:02d}:{m % 60:02d}", "row": i + 2, "full_hour": m % 60 == 0}
        for i, m in enumerate(range(first, last, SLOT_MINUTES))
    ]
    for e in entries:
        # Rad 1 er overskrifta, kolonne 1 er klokkeslett.
        e["row_start"] = (_minutes(e["start"]) - first) // SLOT_MINUTES + 2
        e["row_end"] = -(-(_minutes(e["end"]) - first) // SLOT_MINUTES) + 2
        e["col_start"] = e["first"] + 1
        e["col_end"] = e["last"] + 2
    return {"days": days, "times": times, "sections": SECTIONS}


# ---------------------------------------------------------------------------
# Sesongplanen: den faste vekeplanen for ein sesong.
# ---------------------------------------------------------------------------

def season_view(request, season_id=None):
    seasons = visible_seasons(request.user)
    season = get_object_or_404(seasons, pk=season_id) if season_id else default_season(seasons)
    return render(request, "bookings/schedule.html", schedule_context(season, seasons, user=request.user))


def schedule_context(season, seasons, static_export=False, user=None):
    """Alt malen treng for å teikne sesongplanen. Blir òg brukt av export_static."""
    context = {"mode": "season", "season": season, "seasons": seasons, "static_export": static_export}
    if season is None:
        return context
    show_admin_links = user is not None and user.is_staff and not static_export
    days = []
    for number, name in WEEKDAYS:
        entries = [
            _entry(s, "fast", _validity(s),
                   reverse("admin:bookings_trainingslot_change", args=[s.pk]) if show_admin_links else None)
            for s in season.slots.select_related("group") if s.weekday == number
        ]
        days.append({"number": number, "name": name, "entries": entries})
    context.update(build_grid(days))
    return context


# ---------------------------------------------------------------------------
# Vekevisinga: kva som faktisk skjer ei bestemt veke.
# ---------------------------------------------------------------------------

def week_view(request, day=None):
    if day:
        try:
            date = datetime.date.fromisoformat(day)
        except ValueError:
            raise Http404("Ugyldig dato")
    else:
        date = timezone.localdate()
    monday = date - datetime.timedelta(days=date.weekday())
    dates = [monday + datetime.timedelta(days=i) for i in range(7)]
    sunday = dates[-1]
    user = request.user

    seasons = [s for s in visible_seasons(user) if s.covers(monday) or s.covers(sunday)]
    slots = list(TrainingSlot.objects.filter(season__in=seasons).select_related("group", "season"))
    cancellations = {(c.slot_id, c.date): c for c in Cancellation.objects.filter(date__range=(monday, sunday))}
    bookings = list(Booking.objects.filter(date__range=(monday, sunday), status=Booking.APPROVED).select_related("group"))

    days = []
    for d in dates:
        entries = []
        for s in slots:
            if not s.is_active_on(d):
                continue
            cancellation = cancellations.get((s.pk, d))
            manage = can_manage(user, s.group) and d >= timezone.localdate()
            if cancellation:
                e = _entry(s, "avlyst", [f"Avlyst{': ' + cancellation.reason if cancellation.reason else ''}"],
                           reverse("mine") if manage else None)
            else:
                e = _entry(s, "fast", [],
                           reverse("cancel_slot", args=[s.pk]) + f"?dato={d.isoformat()}" if manage else None)
            entries.append(e)
        for b in bookings:
            if b.date == d:
                entries.append(_entry(b, "enkel", ["enkelttid"], reverse("mine") if can_manage(user, b.group) else None))
        days.append({
            "number": d.weekday(), "name": f"{WEEKDAYS[d.weekday()][1]} {d.day}.{d.month}.",
            "short": f"{WEEKDAYS[d.weekday()][1][:3]} {d.day}.", "entries": entries,
            "today": d == timezone.localdate(),
        })

    iso_week = monday.isocalendar().week
    if monday.month == sunday.month:
        span = f"{monday.day}.–{sunday.day}. {MONTHS[sunday.month - 1]} {sunday.year}"
    else:
        span = f"{monday.day}. {MONTHS[monday.month - 1]} – {sunday.day}. {MONTHS[sunday.month - 1]} {sunday.year}"
    context = {
        "mode": "week", "week_title": f"Veke {iso_week}", "week_span": span,
        "prev_week": (monday - datetime.timedelta(days=7)).isoformat(),
        "next_week": (monday + datetime.timedelta(days=7)).isoformat(),
        "is_current_week": monday <= timezone.localdate() <= sunday,
        "drafts": [s for s in seasons if not s.published],
        "no_season": not seasons,
    }
    context.update(build_grid(days))
    return render(request, "bookings/schedule.html", context)
