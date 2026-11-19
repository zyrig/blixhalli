"""The admin site (/admin/) gives you a ready-made UI to manage all data."""
from django.contrib import admin

from .models import Area, Booking, Team

admin.site.register(Area)
admin.site.register(Team)


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ["team", "area", "start", "end", "notes"]
    list_filter = ["area", "team"]
    date_hierarchy = "start"
