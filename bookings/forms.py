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
