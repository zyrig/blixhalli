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
        "Du har fått brukar på Treningstider Blixhalli",
        f"Hei {user.first_name or user.email}!\n\n"
        f"Du har fått brukar på Treningstider Blixhalli, som lagleiar for: {groups}.\n\n"
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
        "Førespurnaden din om brukar på Treningstider Blixhalli",
        f"Hei {account_request.name}!\n\nFørespurnaden din om brukar vart dessverre ikkje godkjend.{reason}\n",
        None,
        [account_request.email],
    )


def notify_admins_of_request(account_request, request):
    """Send e-post til alle administratorar med e-postadresse."""
    recipients = list(User.objects.filter(is_staff=True, is_active=True).exclude(email="").values_list("email", flat=True))
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
