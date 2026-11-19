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


class AccountRequestForm(forms.ModelForm):
    groups = GroupChoiceField(Group.objects.all(), label="Kva lag er du trenar eller lagleiar for?", required=False)

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
    groups = GroupChoiceField(Group.objects.all(), label="Lagleiar for", required=False)


# ---------------------------------------------------------------------------
# Avlysingar og enkelttider (steg 2)
# ---------------------------------------------------------------------------
from django.utils import timezone  # noqa: E402

from .models import Booking, Cancellation  # noqa: E402
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


class BookingForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = ["group", "date", "start_time", "end_time", "first_section", "last_section", "note"]
        widgets = {"date": DATE_INPUT, "start_time": TIME_INPUT, "end_time": TIME_INPUT}
        labels = {"group": "Lag"}

    def __init__(self, *args, user, facility, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.facility = facility
        # Delane av anlegget, t.d. 1/3, 2/3, 3/3 eller A, B
        choices = [(n, label) for n, label in facility.sections]
        self.fields["first_section"] = forms.TypedChoiceField(label="Frå del", choices=choices, coerce=int, initial=1)
        self.fields["last_section"] = forms.TypedChoiceField(label="Til del", choices=choices, coerce=int,
                                                             initial=facility.section_count)
        # Lagleiarar kan berre booke for sine eigne lag.
        self.fields["group"].queryset = managed_groups(user)
        if self.fields["group"].queryset.count() == 1:
            self.fields["group"].initial = self.fields["group"].queryset.first()

    def clean_date(self):
        return _not_in_past(self.cleaned_data["date"])
