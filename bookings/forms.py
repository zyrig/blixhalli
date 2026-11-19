from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm

from .models import AccountRequest, Group

User = get_user_model()


class EmailLoginForm(AuthenticationForm):
    """Innlogging med e-post i staden for brukarnamn."""

    username = forms.CharField(label="E-post", widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}))

    def clean_username(self):
        return self.cleaned_data["username"].strip().lower()


class ResetPasswordForm(PasswordResetForm):
    """Som Django sitt, men fungerer òg for inviterte brukarar som ikkje har laga passord enno."""

    def get_users(self, email):
        return User.objects.filter(email__iexact=email.strip(), is_active=True)


class GroupChoiceField(forms.ModelMultipleChoiceField):
    widget = forms.CheckboxSelectMultiple

    def label_from_instance(self, obj):
        return f"{obj.name} ({obj.organization})"


class AccountRequestForm(forms.ModelForm):
    groups = GroupChoiceField(Group.objects.none(), label="Kva lag er du trenar eller lagleiar for?", required=False)

    def __init__(self, *args, workspace=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["groups"].queryset = Group.objects.filter(organization__workspace=workspace).select_related(
            "organization").order_by("organization__name", "name")

    class Meta:
        model = AccountRequest
        fields = ["name", "email", "phone", "groups", "other_group", "message"]
        widgets = {"message": forms.Textarea(attrs={"rows": 3})}

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(username=email).exists():
            raise forms.ValidationError("Det finst alt ein brukar med denne e-posten. Prøv «Gløymt passord».")
        if AccountRequest.objects.filter(email__iexact=email, status=AccountRequest.PENDING).exists():
            raise forms.ValidationError("Du har alt ein førespurnad som ventar på godkjenning.")
        return email

    def clean(self):
        data = super().clean()
        if not data.get("groups") and not data.get("other_group"):
            raise forms.ValidationError("Vel minst eitt lag, eller skriv namnet på laget under «Anna lag».")
        return data


class InviteForm(forms.Form):
    name = forms.CharField(label="Namn", max_length=200)
    email = forms.EmailField(label="E-post")
    groups = GroupChoiceField(Group.objects.none(), label="Lagleiar for", required=False)

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        from .permissions import managed_groups
        self.fields["groups"].queryset = managed_groups(user).select_related("organization").order_by(
            "organization__name", "name")


# ---------------------------------------------------------------------------
# Avlysingar og enkelttider (steg 2)
# ---------------------------------------------------------------------------
from django.utils import timezone  # noqa: E402

from .models import Booking, Cancellation, TrainingRequest  # noqa: E402
from .permissions import managed_groups  # noqa: E402

DATE_INPUT = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
TIME_INPUT = forms.TimeInput(attrs={"type": "time", "step": 1800}, format="%H:%M")


def _not_in_past(date):
    if date and date < timezone.localdate():
        raise forms.ValidationError("Datoen har vore.")
    return date


class CancellationForm(forms.ModelForm):
    class Meta:
        model = Cancellation
        fields = ["date", "reason"]
        widgets = {"date": DATE_INPUT}
        labels = {"reason": "Grunn (valfritt)"}

    def __init__(self, *args, slot, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.slot = slot

    def clean_date(self):
        date = _not_in_past(self.cleaned_data["date"])
        if Cancellation.objects.filter(slot=self.instance.slot, date=date).exists():
            raise forms.ValidationError("Tida er alt avlyst denne datoen.")
        return date


def unit_field(facility, initial=None):
    """Val av kor stor del av anlegget, gruppert etter storleik, t.d. «1/2 bane» → «A + B»."""
    choices = [(size, [(f"{f}-{l}", label) for f, l, label in items]) for size, items in facility.unit_options()]
    if len(choices) == 1 and len(choices[0][1]) == 1:  # anlegg utan inndeling
        choices = choices[0][1]
    return forms.ChoiceField(label="Kor stor del", choices=choices, initial=initial)


class UnitMixin:
    """Gjer om valet «2-3» til first_section=2, last_section=3 på objektet."""

    def apply_unit(self, prefix=""):
        value = self.cleaned_data.get("unit")
        if value:
            first, last = (int(x) for x in value.split("-"))
            setattr(self.instance, prefix + "first_section", first)
            setattr(self.instance, prefix + "last_section", last)


class OwnGroupsMixin:
    def limit_groups(self, user):
        # Lagleiarar kan berre velje sine eigne lag.
        self.fields["group"].queryset = managed_groups(user)
        if self.fields["group"].queryset.count() == 1:
            self.fields["group"].initial = self.fields["group"].queryset.first()


class BookingForm(UnitMixin, OwnGroupsMixin, forms.ModelForm):
    class Meta:
        model = Booking
        fields = ["group", "date", "start_time", "end_time", "note"]
        widgets = {"date": DATE_INPUT, "start_time": TIME_INPUT, "end_time": TIME_INPUT}
        labels = {"group": "Lag"}

    def __init__(self, *args, user, facility, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.facility = facility
        self.fields["unit"] = unit_field(facility)
        self.order_fields(["group", "date", "start_time", "end_time", "unit", "note"])
        self.limit_groups(user)

    def clean_date(self):
        return _not_in_past(self.cleaned_data["date"])

    def clean(self):
        data = super().clean()
        self.apply_unit()
        return data


class TrainingRequestForm(UnitMixin, OwnGroupsMixin, forms.ModelForm):
    class Meta:
        model = TrainingRequest
        fields = ["group", "weekday", "start_time", "end_time", "valid_from", "valid_to", "message"]
        widgets = {"start_time": TIME_INPUT, "end_time": TIME_INPUT, "valid_from": DATE_INPUT,
                   "valid_to": DATE_INPUT, "message": forms.Textarea(attrs={"rows": 3})}
        labels = {"group": "Lag"}
        help_texts = {"valid_from": "Første dato tida skal gjelde.", "valid_to": "Siste dato tida skal gjelde."}

    def __init__(self, *args, user, facility, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.facility = facility
        self.fields["unit"] = unit_field(facility)
        self.order_fields(["group", "weekday", "start_time", "end_time", "unit", "valid_from", "valid_to", "message"])
        self.limit_groups(user)

    def clean_valid_from(self):
        return _not_in_past(self.cleaned_data["valid_from"])

    def clean(self):
        data = super().clean()
        self.apply_unit()
        return data


class ProposalForm(UnitMixin, forms.ModelForm):
    """Administrator føreslår ei anna tid. Feltet startar med det laget søkte om."""

    class Meta:
        model = TrainingRequest
        fields = ["proposed_weekday", "proposed_start_time", "proposed_end_time", "proposed_valid_from",
                  "proposed_valid_to", "admin_comment"]
        widgets = {"proposed_start_time": TIME_INPUT, "proposed_end_time": TIME_INPUT,
                   "proposed_valid_from": DATE_INPUT, "proposed_valid_to": DATE_INPUT,
                   "admin_comment": forms.Textarea(attrs={"rows": 3})}
        labels = {"proposed_weekday": "Vekedag", "proposed_start_time": "Frå klokka",
                  "proposed_end_time": "Til klokka", "proposed_valid_from": "Startdato",
                  "proposed_valid_to": "Sluttdato", "admin_comment": "Kommentar til laget"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        r = self.instance
        for f in ("weekday", "start_time", "end_time", "valid_from", "valid_to"):
            self.fields["proposed_" + f].required = True
            if getattr(r, "proposed_" + f) is None:
                self.initial["proposed_" + f] = getattr(r, f)
        self.fields["unit"] = unit_field(r.facility, initial=f"{r.first_section}-{r.last_section}")
        self.order_fields(["proposed_weekday", "proposed_start_time", "proposed_end_time", "unit",
                           "proposed_valid_from", "proposed_valid_to", "admin_comment"])

    def clean(self):
        data = super().clean()
        self.apply_unit(prefix="proposed_")
        from .models import validate_period
        validate_period(data.get("proposed_start_time"), data.get("proposed_end_time"),
                        data.get("proposed_valid_from"), data.get("proposed_valid_to"))
        r = self.instance
        for f in ("weekday", "start_time", "end_time", "valid_from", "valid_to"):
            setattr(r, "proposed_" + f, data.get("proposed_" + f))
        if None not in r.proposal().values():
            clash = r.find_clash(proposed=True)
            if clash:
                raise forms.ValidationError(f"Det føreslåtte kolliderer òg: {clash} ({clash.sections_label}).")
        return data


class RejectForm(forms.Form):
    comment = forms.CharField(label="Grunn (blir send til laget)", required=False,
                              widget=forms.Textarea(attrs={"rows": 2}))
