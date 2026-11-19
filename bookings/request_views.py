"""Søknader om faste treningstider, og enkelttider som må godkjennast.

- Lagleiarar søkjer for sine eigne lag, og kan trekkje søknaden eller svare på motforslag.
- Administratorar godkjenner, avslår eller føreslår anna tid, men berre der dei har rett til det
  (sjå permissions.approver_orgs): fordelaren og eigaren av anlegget, og organisasjonen sjølv
  innanfor blokker han har fått tildelt.
"""
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import notify
from .forms import ProposalForm, RejectForm, TrainingRequestForm
from .models import Booking, TrainingRequest
from .permissions import can_approve_booking, can_approve_request, can_manage, is_any_admin
from .views import get_facility


def admin_required(view):
    @login_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not is_any_admin(request.user):
            raise PermissionDenied("Berre for administratorar.")
        return view(request, *args, **kwargs)
    return wrapper


def _get(request, pk):
    return get_object_or_404(TrainingRequest.objects.select_related("group__organization", "facility__owner",
                                                                    "facility__manager", "created_by"),
                             pk=pk, facility__workspace=request.workspace)


def _require_approver(request, r):
    if not can_approve_request(request.user, r):
        raise PermissionDenied("Du kan ikkje godkjenne denne søknaden.")


@login_required
def new_request(request, facility):
    facility = get_facility(request, facility)
    form = TrainingRequestForm(request.POST or None, user=request.user, facility=facility)
    if not form.fields["group"].queryset.exists():
        messages.error(request, "Du er ikkje lagleiar for noko lag enno.")
        return redirect("mine")
    if request.method == "POST" and form.is_valid():
        r = form.save(commit=False)
        if not can_manage(request.user, r.group):
            raise PermissionDenied
        r.created_by = request.user
        r.save()
        notify.new_request(r, request)
        clash = r.find_clash()
        if clash:
            messages.warning(request, f"Søknaden er sendt, men tida kolliderer med {clash}. "
                                      "Administrator vil vurdere han, og kan føreslå ei anna tid.")
        else:
            messages.success(request, "Søknaden er sendt. Du får e-post når han er handsama.")
        return redirect("mine")
    return render(request, "bookings/request_form.html", {"form": form, "facility": facility})


@login_required
@require_POST
def withdraw(request, pk):
    r = _get(request, pk)
    if not can_manage(request.user, r.group):
        raise PermissionDenied
    if r.status in r.OPEN:
        r.status = r.WITHDRAWN
        r.save()
        messages.success(request, "Søknaden er trekt.")
    return redirect("mine")


@login_required
@require_POST
def answer_proposal(request, pk):
    r = _get(request, pk)
    if not can_manage(request.user, r.group):
        raise PermissionDenied
    if r.status != r.PROPOSED:
        return redirect("mine")
    if request.POST.get("answer") == "accept":
        with transaction.atomic():
            clash = r.find_clash(proposed=True)
            if clash:
                messages.error(request, f"Tida er dessverre ikkje ledig lenger ({clash}). Ta kontakt med administrator.")
                return redirect("mine")
            r.slot = r.build_slot(proposed=True)
            r.slot.save()
            r.status = r.APPROVED
            r.save()
        messages.success(request, "Forslaget er godteke, og tida er lagt inn.")
    else:
        r.status = r.DECLINED
        r.save()
        messages.success(request, "Forslaget er avslått. Du kan sende ein ny søknad.")
    notify.proposal_answered(r, request)
    return redirect("mine")


# ---------------------------------------------------------------------------
# Administrator
# ---------------------------------------------------------------------------

def open_items_for(user, workspace):
    """Søknader og enkelttider som ventar, og som brukaren kan godkjenne."""
    requests = [r for r in TrainingRequest.objects.filter(status__in=TrainingRequest.OPEN, facility__workspace=workspace)
                .select_related("group__organization", "facility__owner", "facility__manager", "created_by")
                .order_by("created_at") if can_approve_request(user, r)]
    bookings = [b for b in Booking.objects.filter(status=Booking.PENDING, facility__workspace=workspace)
                .select_related("group__organization", "facility__owner", "facility__manager", "created_by")
                .order_by("date") if can_approve_booking(user, b)]
    return requests, bookings


@admin_required
def request_admin(request):
    open_requests, pending_bookings = open_items_for(request.user, request.workspace)
    for r in open_requests:
        r.clash = r.find_clash(proposed=r.status == r.PROPOSED)
    for b in pending_bookings:
        b.clash = None
        try:
            b.full_clean()
        except Exception as e:  # noqa: BLE001
            b.clash = "; ".join(getattr(e, "messages", [str(e)]))
    recent = [r for r in TrainingRequest.objects.exclude(status__in=TrainingRequest.OPEN)
              .filter(facility__workspace=request.workspace)
              .select_related("group__organization", "facility__owner", "facility__manager", "handled_by")
              .order_by("-handled_at", "-created_at")[:30] if can_approve_request(request.user, r)][:15]
    return render(request, "bookings/request_admin.html", {
        "open_requests": open_requests, "pending_bookings": pending_bookings, "recent": recent,
        "reject_form": RejectForm()})


def _handled(r, user):
    r.handled_by = user
    r.handled_at = timezone.now()


@admin_required
@require_POST
def approve(request, pk):
    r = _get(request, pk)
    _require_approver(request, r)
    if r.status != r.PENDING:
        return redirect("request_admin")
    with transaction.atomic():
        clash = r.find_clash()
        if clash:
            messages.error(request, f"Kan ikkje godkjenne: kolliderer med {clash}. "
                                    "Føreslå ei anna tid eller avslå.")
            return redirect("request_admin")
        r.slot = r.build_slot()
        r.slot.save()
        r.status = r.APPROVED
        _handled(r, request.user)
        r.save()
    notify.decided(r, request)
    messages.success(request, f"Godkjend: {r}.")
    return redirect("request_admin")


@admin_required
@require_POST
def reject(request, pk):
    r = _get(request, pk)
    _require_approver(request, r)
    form = RejectForm(request.POST)
    if r.status in r.OPEN and form.is_valid():
        r.status = r.REJECTED
        r.admin_comment = form.cleaned_data["comment"]
        _handled(r, request.user)
        r.save()
        notify.decided(r, request)
        messages.success(request, f"Avslått: {r}.")
    return redirect("request_admin")


@admin_required
def propose(request, pk):
    r = _get(request, pk)
    _require_approver(request, r)
    if r.status != r.PENDING:
        return redirect("request_admin")
    form = ProposalForm(request.POST or None, instance=r)
    if request.method == "POST" and form.is_valid():
        r = form.save(commit=False)
        r.status = r.PROPOSED
        _handled(r, request.user)
        r.save()
        notify.decided(r, request)
        messages.success(request, f"Forslaget er sendt til {r.group}.")
        return redirect("request_admin")
    return render(request, "bookings/propose.html", {"form": form, "r": r, "clash": r.find_clash()})


@admin_required
@require_POST
def decide_booking(request, pk):
    b = get_object_or_404(Booking.objects.select_related("group__organization", "facility__owner", "facility__manager"),
                          pk=pk, facility__workspace=request.workspace, status=Booking.PENDING)
    if not can_approve_booking(request.user, b):
        raise PermissionDenied
    if request.POST.get("answer") == "approve":
        b.status = Booking.APPROVED
        try:
            b.full_clean()
        except Exception as e:  # noqa: BLE001
            messages.error(request, f"Kan ikkje godkjenne: {'; '.join(getattr(e, 'messages', [str(e)]))}")
            return redirect("request_admin")
        b.save()
        messages.success(request, f"Godkjend: {b}.")
    else:
        b.status = Booking.REJECTED
        b.save()
        messages.success(request, f"Avslått: {b}.")
    notify.booking_decided(b, request)
    return redirect("request_admin")
