"""E-postvarsel om søknader. Utan e-postoppsett blir dei skrivne til loggen."""
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.urls import reverse

from .permissions import booking_approver_orgs, request_approver_orgs


def admin_emails(orgs):
    """Administratorane i organisasjonane. Har ingen av dei e-post, går varselet til plattformadministratorane."""
    User = get_user_model()
    emails = set(User.objects.filter(admin_of__in=orgs, is_active=True).exclude(email="")
                 .values_list("email", flat=True))
    if not emails:
        emails = set(User.objects.filter(is_superuser=True, is_active=True).exclude(email="")
                     .values_list("email", flat=True))
    return sorted(emails)


def _leaders(group, created_by=None):
    emails = set(group.leaders.exclude(email="").values_list("email", flat=True))
    if created_by and created_by.email:
        emails.add(created_by.email)
    return sorted(emails)


def _send(subject, body, recipients):
    if recipients:
        send_mail(subject, body, None, recipients)


def new_request(training_request, request):
    r = training_request
    link = request.build_absolute_uri(reverse("request_admin"))
    clash = r.find_clash()
    warning = f"\nMerk: kolliderer med {clash}.\n" if clash else ""
    _send(f"Ny søknad om fast tid: {r.group} ({r.group.organization})",
          f"{r.group} ({r.group.organization}) søkjer om:\n{r.summary()}\n"
          f"{warning}\nMelding: {r.message or '–'}\n\nHandsam søknaden her:\n{link}\n",
          admin_emails(request_approver_orgs(r)))


def new_booking(booking, request):
    b = booking
    link = request.build_absolute_uri(reverse("request_admin"))
    _send(f"Førespurnad om enkelttid: {b.group} ({b.group.organization})",
          f"{b.group} ({b.group.organization}) ber om:\n{b} på {b.facility} {b.sections_label}\n"
          f"Merknad: {b.note or '–'}\n\nHandsam førespurnaden her:\n{link}\n",
          admin_emails(booking_approver_orgs(b)))


def booking_decided(booking, request):
    b = booking
    word = "godkjend" if b.status == b.APPROVED else "ikkje godkjend"
    _send(f"Enkelttid for {b.group}: {word}", f"Førespurnaden om {b} på {b.facility} er {word}.\n",
          _leaders(b.group, b.created_by))


def decided(training_request, request):
    link = request.build_absolute_uri(reverse("mine"))
    r = training_request
    if r.status == r.APPROVED:
        text = f"Søknaden er godkjend, og tida er lagt inn:\n{r.summary()}"
    elif r.status == r.PROPOSED:
        text = (f"Det er føreslått ei anna tid:\n{r.summary(proposed=True)}\n\n"
                f"Du søkte om:\n{r.summary()}\n\nGodta eller avslå forslaget under «Mine lag»:\n{link}")
    else:
        text = f"Søknaden vart dessverre ikkje godkjend:\n{r.summary()}"
    if r.admin_comment:
        text += f"\n\nKommentar: {r.admin_comment}"
    _send(f"Søknad om fast tid for {r.group}: {r.get_status_display().lower()}", text + "\n",
          _leaders(r.group, r.created_by))


def proposal_answered(training_request, request):
    r = training_request
    answer = "godteke" if r.status == r.APPROVED else "ikkje godteke"
    _send(f"{r.group} har {answer} forslaget",
          f"{r.group} har {answer} forslaget om:\n{r.summary(proposed=True)}\n",
          admin_emails(request_approver_orgs(r, proposed=True)))
