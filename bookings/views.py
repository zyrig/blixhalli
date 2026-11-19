"""Views: Python-funksjonar som lagar sidene."""
from django.shortcuts import get_object_or_404, render

from .models import SECTIONS, WEEKDAYS, Season

SLOT_MINUTES = 30


def _minutes(t):
    return t.hour * 60 + t.minute


def visible_seasons(user):
    seasons = Season.objects.all()
    if not (user and user.is_staff):
        seasons = seasons.filter(published=True)
    return seasons


def default_season(seasons):
    return seasons.filter(published=True).first() or seasons.first()


def schedule(request, season_id=None):
    """Vekeplanen for ein sesong, lagt opp som rutenett slik som i reknearket."""
    seasons = visible_seasons(request.user)
    if season_id is not None:
        season = get_object_or_404(seasons, pk=season_id)
    else:
        season = default_season(seasons)
    return render(request, "bookings/schedule.html", schedule_context(season, seasons))


def schedule_context(season, seasons, static_export=False):
    """Alt malen treng for å teikne vekeplanen. Blir òg brukt av export_static."""
    context = {"season": season, "seasons": seasons, "static_export": static_export}
    if season is None:
        return context

    slots = list(season.slots.select_related("group"))

    # Rutenettet går frå første til siste heile time som er i bruk (minst 09–22).
    first = min([_minutes(s.start_time) for s in slots] + [9 * 60]) // 60 * 60
    last = -(-max([_minutes(s.end_time) for s in slots] + [22 * 60]) // 60) * 60

    times = []
    for i, m in enumerate(range(first, last, SLOT_MINUTES)):
        times.append({"label": f"{m // 60:02d}:{m % 60:02d}", "row": i + 2, "full_hour": m % 60 == 0})

    days = []
    for number, name in WEEKDAYS:
        day_slots = []
        for s in slots:
            if s.weekday != number:
                continue
            day_slots.append({
                "slot": s,
                # CSS grid: rad 1 er overskrifta, kolonne 1 er klokkeslett.
                "row_start": (_minutes(s.start_time) - first) // SLOT_MINUTES + 2,
                "row_end": -(-(_minutes(s.end_time) - first) // SLOT_MINUTES) + 2,
                "col_start": s.first_section + 1,
                "col_end": s.last_section + 2,
            })
        days.append({"number": number, "name": name, "slots": day_slots})

    context.update({"days": days, "times": times, "sections": SECTIONS})
    return context
