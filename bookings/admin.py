"""Admin-sida (/admin/) gir eit ferdig grensesnitt for å redigere alle data."""
from django.contrib import admin, messages

from . import accounts
from .models import AccountRequest, Booking, Cancellation, Facility, Group, Season, TrainingRequest, TrainingSlot

admin.site.site_header = "Treningstider – administrasjon"
admin.site.site_title = "Treningstider"
admin.site.site_url = "/"


@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):
    list_display = ["name", "kind", "section_labels", "units", "slug", "order"]
    prepopulated_fields = {"slug": ["name"]}


@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = ["name", "facility", "published", "start_date", "end_date"]
    list_filter = ["facility", "published"]

    def get_changeform_initial_data(self, request):
        return dict(request.GET.items())


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "leader_list"]
    list_filter = ["category"]
    search_fields = ["name", "contact"]
    filter_horizontal = ["leaders"]

    @admin.display(description="Lagleiarar")
    def leader_list(self, obj):
        return ", ".join(u.get_full_name() or u.email for u in obj.leaders.all())


@admin.register(TrainingSlot)
class TrainingSlotAdmin(admin.ModelAdmin):
    list_display = ["group", "weekday", "start_time", "end_time", "sections_label", "tentative", "season"]
    list_display = ["group", "facility", "weekday", "start_time", "end_time", "sections_label", "valid_from",
                    "valid_to", "season"]
    list_filter = ["facility", "season", "weekday", "tentative", "group__category"]
    list_select_related = ["group", "facility", "season"]
    search_fields = ["group__name", "note"]
    autocomplete_fields = ["group"]

    def get_changeform_initial_data(self, request):
        # Gjer det mogleg å lenkje til "legg til" med ferdig utfylte felt, t.d. ?season=1&weekday=2
        return dict(request.GET.items())


@admin.register(AccountRequest)
class AccountRequestAdmin(admin.ModelAdmin):
    list_display = ["name", "email", "group_list", "other_group", "status", "created_at"]
    list_filter = ["status"]
    search_fields = ["name", "email", "other_group"]
    filter_horizontal = ["groups"]
    readonly_fields = ["status", "created_at", "handled_at", "handled_by", "user"]
    actions = ["approve_selected", "reject_selected"]

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
                request, "Nokre har skrive inn «anna lag». Legg dei til som lagleiar på rett gruppe.", messages.WARNING
            )

    @admin.action(description="Avslå (skriv eventuelt kommentar på førespurnaden først)")
    def reject_selected(self, request, queryset):
        done = 0
        for account_request in queryset.filter(status=AccountRequest.PENDING):
            accounts.reject(account_request, request.user)
            done += 1
        self.message_user(request, f"{done} førespurnad(er) avslått.", messages.SUCCESS)


@admin.register(Cancellation)
class CancellationAdmin(admin.ModelAdmin):
    list_display = ["slot", "date", "reason", "created_by"]
    list_filter = ["slot__group"]
    date_hierarchy = "date"
    autocomplete_fields = ["slot"]


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ["group", "facility", "date", "start_time", "end_time", "sections_label", "status", "note", "created_by"]
    list_filter = ["facility", "status", "group__category"]
    date_hierarchy = "date"
    autocomplete_fields = ["group"]


@admin.register(TrainingRequest)
class TrainingRequestAdmin(admin.ModelAdmin):
    """Søknader blir handsama på /soknader/. Her kan ein sjå og rette alle."""
    list_display = ["group", "facility", "weekday", "start_time", "end_time", "valid_from", "valid_to", "status",
                    "created_at"]
    list_filter = ["status", "facility"]
    search_fields = ["group__name", "message"]
    autocomplete_fields = ["group"]
