"""Søknader om faste treningstider.

- Lagleiarar søkjer for sine eigne lag, og kan trekkje søknaden eller svare på motforslag.
- Administratorar godkjenner, avslår eller føreslår anna tid.
"""
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import notify
from .forms import ProposalForm, RejectForm, TrainingRequestForm
from .models import Facility, TrainingRequest
from .permissions import can_manage


def _get(pk):
    return get_object_or_404(TrainingRequest.objects.select_related("group", "facility", "created_by"), pk=pk)


@login_required
def new_request(request, facility):
    facility = get_object_or_404(Facility, slug=facility)
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
            messages.success(request, "Søknaden er sendt. Du får e-post når administrator har handsama han.")
        return redirect("mine")
    return render(request, "bookings/request_form.html", {"form": form, "facility": facility})


@login_required
@require_POST
def withdraw(request, pk):
    r = _get(pk)
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
    r = _get(pk)
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

@staff_member_required
def request_admin(request):
    open_requests = list(TrainingRequest.objects.filter(status__in=TrainingRequest.OPEN)
                         .select_related("group", "facility", "created_by").order_by("created_at"))
    for r in open_requests:
        r.clash = r.find_clash(proposed=r.status == r.PROPOSED)
    recent = (TrainingRequest.objects.exclude(status__in=TrainingRequest.OPEN)
              .select_related("group", "facility", "handled_by").order_by("-handled_at", "-created_at")[:15])
    return render(request, "bookings/request_admin.html", {
        "open_requests": open_requests, "recent": recent, "reject_form": RejectForm()})


def _handled(r, user):
    r.handled_by = user
    r.handled_at = timezone.now()


@staff_member_required
@require_POST
def approve(request, pk):
    r = _get(pk)
    if r.status != r.PENDING:
        return redirect("request_admin")
    with transaction.atomic():
        clash = r.find_clash()
        if clash:
            messages.error(request, f"Kan ikkje godkjenne: kolliderer med {clash} ({clash.sections_label}). "
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


@staff_member_required
@require_POST
def reject(request, pk):
    r = _get(pk)
    form = RejectForm(request.POST)
    if r.status in r.OPEN and form.is_valid():
        r.status = r.REJECTED
        r.admin_comment = form.cleaned_data["comment"]
        _handled(r, request.user)
        r.save()
        notify.decided(r, request)
        messages.success(request, f"Avslått: {r}.")
    return redirect("request_admin")


@staff_member_required
def propose(request, pk):
    r = _get(pk)
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
