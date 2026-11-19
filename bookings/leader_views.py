"""Sider der lagleiarar (og administratorar) endrar tider.

Lagleiarar kan berre endre tider for sine eigne lag. Det blir sjekka med
permissions.can_manage() i kvar view, ikkje berre ved at knappane er skjulte.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import BookingForm, CancellationForm
from .models import Booking, Cancellation, Facility, TrainingSlot
from .permissions import can_manage


def _require_manage(user, group):
    if not can_manage(user, group):
        raise PermissionDenied("Du kan berre endre tider for dine eigne lag.")


@login_required
def cancel_slot(request, slot_id):
    slot = get_object_or_404(TrainingSlot.objects.select_related("group", "season__facility"), pk=slot_id)
    _require_manage(request.user, slot.group)
    form = CancellationForm(request.POST or None, slot=slot, initial={"date": request.GET.get("dato")})
    if request.method == "POST" and form.is_valid():
        cancellation = form.save(commit=False)
        cancellation.created_by = request.user
        cancellation.save()
        messages.success(request, f"{slot.group} er avlyst {cancellation.date:%d.%m.%Y}. Plassen er no ledig for andre.")
        return redirect("week", slot.facility.slug, cancellation.date.isoformat())
    return render(request, "bookings/cancel.html", {"slot": slot, "form": form})


@login_required
@require_POST
def undo_cancellation(request, pk):
    cancellation = get_object_or_404(Cancellation.objects.select_related("slot__group"), pk=pk)
    _require_manage(request.user, cancellation.slot.group)
    taken = cancellation.blocking_booking()
    if taken:
        messages.error(request, f"Kan ikkje angre: plassen er alt booka av {taken.group}.")
    else:
        cancellation.delete()
        messages.success(request, f"Avlysinga er angra. {cancellation.slot.group} har tida si {cancellation.date:%d.%m.%Y}.")
    return redirect("mine")


@login_required
def new_booking(request, facility):
    facility = get_object_or_404(Facility, slug=facility)
    form = BookingForm(request.POST or None, user=request.user, facility=facility,
                       initial={k: v for k, v in request.GET.items() if k in ("date", "start_time", "end_time")})
    if not form.fields["group"].queryset.exists():
        messages.error(request, "Du er ikkje lagleiar for noko lag enno.")
        return redirect("mine")
    if request.method == "POST" and form.is_valid():
        booking = form.save(commit=False)
        _require_manage(request.user, booking.group)  # ekstra sikring
        booking.facility = facility
        booking.created_by = request.user
        booking.status = Booking.APPROVED  # enkelttider på ledig plass blir godkjende automatisk
        booking.save()
        messages.success(request, f"Booka: {booking}.")
        return redirect("week", facility.slug, booking.date.isoformat())
    return render(request, "bookings/booking_form.html", {"form": form, "facility": facility})


@login_required
@require_POST
def delete_booking(request, pk):
    booking = get_object_or_404(Booking.objects.select_related("group", "facility"), pk=pk)
    _require_manage(request.user, booking.group)
    booking.delete()
    messages.success(request, f"Enkelttida er sletta: {booking}.")
    return redirect("mine")


def upcoming_for(groups):
    today = timezone.localdate()
    return {
        "cancellations": Cancellation.objects.filter(slot__group__in=groups, date__gte=today)
                         .select_related("slot__group", "slot__season__facility"),
        "bookings": Booking.objects.filter(group__in=groups, date__gte=today).select_related("group", "facility"),
        "facilities": Facility.objects.all(),
    }
