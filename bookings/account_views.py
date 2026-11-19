"""Sider for brukarar: be om brukar, mine lag og invitasjon."""
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import redirect, render
from django.utils import timezone

from . import accounts
from .forms import AccountRequestForm, InviteForm
from .models import AccountRequest, TrainingSlot


def request_account(request):
    if request.user.is_authenticated:
        return redirect("mine")
    form = AccountRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        account_request = form.save()
        accounts.notify_admins_of_request(account_request, request)
        return render(request, "bookings/request_account_done.html", {"account_request": account_request})
    return render(request, "bookings/request_account.html", {"form": form})


@login_required
def mine(request):
    groups = request.user.led_groups.all()
    slots = TrainingSlot.objects.filter(group__in=groups).select_related("group", "facility", "season")
    if not request.user.is_staff:
        # utkast er berre synlege for administratorar
        slots = slots.filter(Q(season__isnull=True) | Q(season__published=True))
    today = timezone.localdate()
    slots = [s for s in slots.order_by("facility", "weekday", "start_time")
             if s.effective_range()[1] is None or s.effective_range()[1] >= today]
    from .leader_views import upcoming_for
    from .models import TrainingRequest
    context = {"groups": groups, "slots": slots, **upcoming_for(groups),
               "requests": TrainingRequest.objects.filter(group__in=groups).select_related("group", "facility")[:30]}
    if request.user.is_staff:
        context["pending_requests"] = AccountRequest.objects.filter(status=AccountRequest.PENDING).count()
    return render(request, "bookings/mine.html", context)


@staff_member_required
def invite(request):
    form = InviteForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        user = accounts.create_or_update_user(data["name"], data["email"], data["groups"])
        accounts.send_invitation(user, request)
        messages.success(request, f"Invitasjon sendt til {user.email}.")
        return redirect("invite")
    return render(request, "bookings/invite.html", {"form": form})
