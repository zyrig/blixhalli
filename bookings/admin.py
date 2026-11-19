"""Admin-sida (/admin/) gir eit ferdig grensesnitt for å redigere alle data."""
from django.contrib import admin

from .models import Group, Season, TrainingSlot

admin.site.site_header = "Blixhalli – administrasjon"
admin.site.site_title = "Blixhalli"


@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = ["name", "published", "start_date", "end_date"]


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "contact"]
    list_filter = ["category"]
    search_fields = ["name", "contact"]


@admin.register(TrainingSlot)
class TrainingSlotAdmin(admin.ModelAdmin):
    list_display = ["group", "weekday", "start_time", "end_time", "sections_label", "tentative", "season"]
    list_filter = ["season", "weekday", "tentative", "group__category"]
    search_fields = ["group__name", "note"]
    autocomplete_fields = ["group"]

    def get_changeform_initial_data(self, request):
        # Gjer det mogleg å lenkje til "legg til" med ferdig utfylte felt, t.d. ?season=1&weekday=2
        return dict(request.GET.items())
