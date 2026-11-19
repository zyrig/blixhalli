"""E-postvarsel om søknader. Utan e-postoppsett blir dei skrivne til loggen."""
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.urls import reverse


def _admins():
    User = get_user_model()
    return list(User.objects.filter(is_staff=True, is_active=True).exclude(email="").values_list("email", flat=True))


def _leaders(training_request):
    emails = set(training_request.group.leaders.exclude(email="").values_list("email", flat=True))
    if training_request.created_by and training_request.created_by.email:
        emails.add(training_request.created_by.email)
    return sorted(emails)


def _send(subject, body, recipients):
    if recipients:
        send_mail(subject, body, None, recipients)


def new_request(training_request, request):
    link = request.build_absolute_uri(reverse("request_admin"))
    clash = training_request.find_clash()
    warning = f"\nMerk: kolliderer med {clash} ({clash.sections_label}).\n" if clash else ""
    _send(f"Ny søknad om fast tid: {training_request.group}",
          f"{training_request.group} søkjer om:\n{training_request.summary()}\n"
          f"{warning}\nMelding: {training_request.message or '–'}\n\nHandsam søknaden her:\n{link}\n",
          _admins())


def decided(training_request, request):
    link = request.build_absolute_uri(reverse("mine"))
    r = training_request
    if r.status == r.APPROVED:
        text = f"Søknaden er godkjend, og tida er lagt inn:\n{r.summary()}"
    elif r.status == r.PROPOSED:
        text = (f"Administrator har føreslått ei anna tid:\n{r.summary(proposed=True)}\n\n"
                f"Du søkte om:\n{r.summary()}\n\nGodta eller avslå forslaget under «Mine lag»:\n{link}")
    else:
        text = f"Søknaden vart dessverre ikkje godkjend:\n{r.summary()}"
    if r.admin_comment:
        text += f"\n\nKommentar: {r.admin_comment}"
    _send(f"Søknad om fast tid for {r.group}: {r.get_status_display().lower()}", text + "\n", _leaders(r))


def proposal_answered(training_request, request):
    r = training_request
    answer = "godteke" if r.status == r.APPROVED else "ikkje godteke"
    _send(f"{r.group} har {answer} forslaget",
          f"{r.group} har {answer} forslaget om:\n{r.summary(proposed=True)}\n", _admins())
