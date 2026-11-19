"""Views: Python functions that turn a web request into a page."""
import datetime

from django.shortcuts import redirect, render
from django.utils import timezone

from .forms import BookingForm
from .models import Area, Booking


def week_schedule(request):
    """Show all bookings for one week (?week=YYYY-MM-DD picks the week)."""
    try:
        day = datetime.date.fromisoformat(request.GET.get("week", ""))
    except ValueError:
        day = timezone.localdate()
    monday = day - datetime.timedelta(days=day.weekday())
    days = [monday + datetime.timedelta(days=i) for i in range(7)]

    tz = timezone.get_current_timezone()
    week_start = datetime.datetime.combine(monday, datetime.time.min, tzinfo=tz)
    week_end = week_start + datetime.timedelta(days=7)
    bookings = Booking.objects.filter(start__lt=week_end, end__gt=week_start).select_related("area", "team")

    schedule = [
        {"date": d, "bookings": [b for b in bookings if timezone.localtime(b.start).date() == d]}
        for d in days
    ]
    return render(request, "bookings/week.html", {
        "schedule": schedule,
        "areas": Area.objects.all(),
        "prev_week": monday - datetime.timedelta(days=7),
        "next_week": monday + datetime.timedelta(days=7),
        "monday": monday,
    })


def new_booking(request):
    form = BookingForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        booking = form.save()
        return redirect(f"/?week={timezone.localtime(booking.start).date()}")
    return render(request, "bookings/new.html", {"form": form})
