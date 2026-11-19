"""Admin-sida (/admin/) gir eit ferdig grensesnitt for å redigere alle data.

Plattformadministratorar (superuser) ser alt. Administratorar i ein organisasjon ser berre det som
høyrer til organisasjonen: laga sine, og anlegga organisasjonen eig eller fordeler tid på
(eigaren, t.d. kommunen, kan overstyre alt på anlegga sine).
"""
from django.contrib import admin, messages
from django.contrib.admin import RelatedOnlyFieldListFilter as Only
from django.db.models import Q

from . import accounts
from .models import (AccountRequest, Allocation, Booking, Cancellation, Facility, Group, Organization, Season,
                     TrainingRequest, TrainingSlot, Workspace)
from .permissions import admin_facilities, admin_orgs

admin.site.site_header = "Treningstider – administrasjon"
admin.site.site_title = "Treningstider"
admin.site.site_url = "/"


def _workspaces(user):
    return Workspace.objects.filter(organizations__in=admin_orgs(user)).distinct()


class ScopedAdmin(admin.ModelAdmin):
    """Avgrensar lista og vala i skjema til det brukaren har rett til å administrere."""

    def get_changeform_initial_data(self, request):
        # Gjer det mogleg å lenkje til «legg til» med ferdig utfylte felt, t.d. ?facility=1&weekday=2
        return dict(request.GET.items())

    def scope(self, request, qs):
        return qs

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs if request.user.is_superuser else self.scope(request, qs)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if not request.user.is_superuser:
            user = request.user
            if db_field.related_model is Facility:
                kwargs["queryset"] = Facility.objects.filter(workspace__in=_workspaces(user))
            elif db_field.related_model is Group:
                kwargs["queryset"] = Group.objects.filter(
                    Q(organization__in=admin_orgs(user))
                    | Q(organization__workspace__in=admin_facilities(user).values("workspace"))).distinct()
            elif db_field.related_model is Organization:
                kwargs["queryset"] = Organization.objects.filter(workspace__in=_workspaces(user))
            elif db_field.related_model is Workspace:
                kwargs["queryset"] = _workspaces(user)
            elif db_field.related_model is Season:
                kwargs["queryset"] = Season.objects.filter(facility__in=admin_facilities(user))
            elif db_field.related_model is TrainingSlot:
                kwargs["queryset"] = self._slots(request)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if not request.user.is_superuser and db_field.related_model is Group:
            kwargs["queryset"] = Group.objects.filter(organization__in=admin_orgs(request.user))
        return super().formfield_for_manytomany(db_field, request, **kwargs)

    def _slots(self, request):
        user = request.user
        return TrainingSlot.objects.filter(Q(facility__in=admin_facilities(user))
                                           | Q(group__organization__in=admin_orgs(user))).distinct()


@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "domain"]


@admin.register(Organization)
class OrganizationAdmin(ScopedAdmin):
    list_display = ["name", "kind", "workspace", "admin_list"]
    list_filter = [("workspace", Only), "kind"]
    filter_horizontal = ["admins"]
    prepopulated_fields = {"slug": ["name"]}

    def scope(self, request, qs):
        return qs.filter(pk__in=admin_orgs(request.user))

    @admin.display(description="Administratorar")
    def admin_list(self, obj):
        return ", ".join(u.get_full_name() or u.email for u in obj.admins.all())


@admin.register(Facility)
class FacilityAdmin(ScopedAdmin):
    list_display = ["name", "workspace", "owner", "manager", "section_labels", "units", "slug", "order"]
    list_filter = [("workspace", Only)]
    prepopulated_fields = {"slug": ["name"]}

    def scope(self, request, qs):
        return qs.filter(pk__in=admin_facilities(request.user))


@admin.register(Season)
class SeasonAdmin(ScopedAdmin):
    list_display = ["name", "facility", "published", "start_date", "end_date"]
    list_filter = [("facility", Only), "published"]

    def scope(self, request, qs):
        return qs.filter(facility__in=admin_facilities(request.user))


@admin.register(Group)
class GroupAdmin(ScopedAdmin):
    list_display = ["name", "organization", "category", "leader_list"]
    list_filter = [("organization", Only), "category"]
    search_fields = ["name", "contact"]
    filter_horizontal = ["leaders"]

    def scope(self, request, qs):
        return qs.filter(organization__in=admin_orgs(request.user))

    @admin.display(description="Lagleiarar")
    def leader_list(self, obj):
        return ", ".join(u.get_full_name() or u.email for u in obj.leaders.all())


@admin.register(Allocation)
class AllocationAdmin(ScopedAdmin):
    list_display = ["organization", "facility", "weekday", "start_time", "end_time", "sections_label", "valid_from",
                    "valid_to"]
    list_filter = [("facility", Only), ("organization", Only), "weekday"]

    def scope(self, request, qs):
        return qs.filter(facility__in=admin_facilities(request.user))


@admin.register(TrainingSlot)
class TrainingSlotAdmin(ScopedAdmin):
    list_display = ["group", "facility", "weekday", "start_time", "end_time", "sections_label", "valid_from",
                    "valid_to", "season"]
    list_filter = [("facility", Only), ("season", Only), "weekday", "tentative", ("group__organization", Only), "group__category"]
    list_select_related = ["group", "facility", "season"]
    search_fields = ["group__name", "note"]
    autocomplete_fields = ["group"]

    def scope(self, request, qs):
        return qs.filter(pk__in=self._slots(request))


@admin.register(Cancellation)
class CancellationAdmin(ScopedAdmin):
    list_display = ["slot", "date", "reason", "created_by"]
    list_filter = [("slot__facility", Only), ("slot__group", Only)]
    date_hierarchy = "date"
    autocomplete_fields = ["slot"]

    def scope(self, request, qs):
        return qs.filter(slot__in=self._slots(request))


@admin.register(Booking)
class BookingAdmin(ScopedAdmin):
    list_display = ["group", "facility", "date", "start_time", "end_time", "sections_label", "status", "note",
                    "created_by"]
    list_filter = [("facility", Only), "status", ("group__organization", Only), "group__category"]
    date_hierarchy = "date"
    autocomplete_fields = ["group"]

    def scope(self, request, qs):
        user = request.user
        return qs.filter(Q(facility__in=admin_facilities(user)) | Q(group__organization__in=admin_orgs(user)))


@admin.register(TrainingRequest)
class TrainingRequestAdmin(ScopedAdmin):
    """Søknader blir handsama på /soknader/. Her kan ein sjå og rette alle."""
    list_display = ["group", "facility", "weekday", "start_time", "end_time", "valid_from", "valid_to", "status",
                    "created_at"]
    list_filter = ["status", ("facility", Only), ("group__organization", Only)]
    search_fields = ["group__name", "message"]
    autocomplete_fields = ["group"]

    def scope(self, request, qs):
        user = request.user
        return qs.filter(Q(facility__in=admin_facilities(user)) | Q(group__organization__in=admin_orgs(user)))


@admin.register(AccountRequest)
class AccountRequestAdmin(ScopedAdmin):
    list_display = ["name", "email", "group_list", "other_group", "status", "created_at"]
    list_filter = ["status"]
    search_fields = ["name", "email", "other_group"]
    filter_horizontal = ["groups"]
    readonly_fields = ["status", "created_at", "handled_at", "handled_by", "user"]
    actions = ["approve_selected", "reject_selected"]

    def scope(self, request, qs):
        return qs.filter(pk__in=accounts.visible_account_requests_any(request.user))

    @admin.display(description="Lag")
    def group_list(self, obj):
        return ", ".join(g.name for g in obj.groups.all())

    @admin.action(description="Godkjenn og send invitasjon")
    def approve_selected(self, request, queryset):
        done = 0
        for account_request in queryset.filter(status=AccountRequest.PENDING):
            accounts.approve(account_request, request.user, request)
            done += 1
        self.message_user(request, f"{done} førespurnad(er) godkjende, og invitasjon er sendt.", messages.SUCCESS)
        if queryset.filter(status=AccountRequest.APPROVED, other_group__gt="").exists():
            self.message_user(
                request, "Nokre har skrive inn «anna lag». Legg dei til som lagleiar på rett lag.", messages.WARNING
            )

    @admin.action(description="Avslå (skriv eventuelt kommentar på førespurnaden først)")
    def reject_selected(self, request, queryset):
        done = 0
        for account_request in queryset.filter(status=AccountRequest.PENDING):
            accounts.reject(account_request, request.user)
            done += 1
        self.message_user(request, f"{done} førespurnad(er) avslått.", messages.SUCCESS)
