"""Brukarar: opprette, invitere, godkjenne og avslå.

Brukarnamnet er e-postadressa (med små bokstavar). Nye brukarar får ikkje noko
passord. Dei får i staden ei lenkje på e-post der dei lagar passordet sjølv.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from django.db.models import Q

from .models import AccountRequest

User = get_user_model()


def find_user(email):
    return User.objects.filter(username=email.strip().lower()).first()


def create_or_update_user(name, email, groups):
    """Finn eller lag brukaren, og gjer han til lagleiar for gruppene."""
    email = email.strip().lower()
    user = find_user(email)
    if user is None:
        first, _, last = name.strip().partition(" ")
        user = User(username=email, email=email, first_name=first, last_name=last)
        user.set_unusable_password()
        user.save()
    for group in groups:
        group.leaders.add(user)
    return user


def set_password_link(user, request):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    return request.build_absolute_uri(reverse("password_reset_confirm", args=[uid, token]))


def send_invitation(user, request):
    groups = ", ".join(g.name for g in user.led_groups.all()) or "ingen lag enno"
    send_mail(
        "Du har fått brukar på Treningstider",
        f"Hei {user.first_name or user.email}!\n\n"
        f"Du har fått brukar på Treningstider, som lagleiar for: {groups}.\n\n"
        f"Lag passordet ditt her:\n{set_password_link(user, request)}\n\n"
        f"Brukarnamnet ditt er e-postadressa di: {user.email}\n"
        f"Lenkja varer i {_days()} dagar. Har ho gått ut, bruk «Gløymt passord» på innloggingssida.\n",
        None,
        [user.email],
    )


def approve(account_request, by, request):
    user = create_or_update_user(account_request.name, account_request.email, account_request.groups.all())
    account_request.status = AccountRequest.APPROVED
    account_request.user = user
    account_request.handled_by = by
    account_request.handled_at = timezone.now()
    account_request.save()
    send_invitation(user, request)
    return user


def reject(account_request, by, comment=""):
    account_request.status = AccountRequest.REJECTED
    account_request.handled_by = by
    account_request.handled_at = timezone.now()
    if comment:
        account_request.admin_comment = comment
    account_request.save()
    reason = f"\n\nKommentar: {account_request.admin_comment}" if account_request.admin_comment else ""
    send_mail(
        "Førespurnaden din om brukar på Treningstider",
        f"Hei {account_request.name}!\n\nFørespurnaden din om brukar vart dessverre ikkje godkjend.{reason}\n",
        None,
        [account_request.email],
    )


def visible_account_requests(user, workspace):
    """Førespurnader om brukar ein administrator skal handsame: dei som gjeld lag i organisasjonane
    hans, og dei som har skrive inn eit lag som ikkje finst («anna lag»)."""
    qs = AccountRequest.objects.filter(workspace=workspace)
    if user.is_superuser:
        return qs
    return qs.filter(Q(groups__organization__admins=user) | Q(other_group__gt="")).distinct()


def visible_account_requests_any(user):
    """Som visible_account_requests, men for alle områda brukaren administrerer (brukt i admin)."""
    from .models import Workspace
    from .permissions import admin_orgs
    workspaces = Workspace.objects.filter(organizations__in=admin_orgs(user)).distinct()
    qs = AccountRequest.objects.filter(workspace__in=workspaces)
    if user.is_superuser:
        return AccountRequest.objects.all()
    return qs.filter(Q(groups__organization__admins=user) | Q(other_group__gt="")).distinct()


def notify_admins_of_request(account_request, request):
    """Send e-post til administratorane for laga det gjeld (eller alle i området ved «anna lag»)."""
    from .models import Organization
    from .notify import admin_emails
    orgs = Organization.objects.filter(groups__in=account_request.groups.all()).distinct()
    if account_request.other_group or not orgs.exists():
        orgs = Organization.objects.filter(workspace=account_request.workspace)
    recipients = admin_emails(orgs)
    if not recipients:
        return
    link = request.build_absolute_uri(reverse("admin:bookings_accountrequest_change", args=[account_request.pk]))
    send_mail(
        f"Ny førespurnad om brukar: {account_request.name}",
        f"{account_request.name} <{account_request.email}> ber om brukar.\n\nSjå og godkjenn her:\n{link}\n",
        None,
        recipients,
    )


def _days():
    from django.conf import settings
    return settings.PASSWORD_RESET_TIMEOUT // 86400
