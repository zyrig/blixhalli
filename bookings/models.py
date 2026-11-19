"""Data models: what we store in the database.

Each class below becomes a database table. Django creates and updates the
tables for you via "migrations" (python manage.py makemigrations / migrate).
"""
from django.core.exceptions import ValidationError
from django.db import models


class Area(models.Model):
    """A bookable part of the hall, e.g. "Court 1" or "Gym"."""

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Team(models.Model):
    """A group that trains in the hall, e.g. a club team."""

    name = models.CharField(max_length=100, unique=True)
    contact_email = models.EmailField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Booking(models.Model):
    """One training time: a team uses an area from start to end."""

    area = models.ForeignKey(Area, on_delete=models.CASCADE, related_name="bookings")
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="bookings")
    start = models.DateTimeField()
    end = models.DateTimeField()
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["start"]

    def __str__(self):
        return f"{self.team} @ {self.area} {self.start:%Y-%m-%d %H:%M}"

    def clean(self):
        """Validation rules, run by forms and the admin before saving."""
        if self.start and self.end and self.end <= self.start:
            raise ValidationError("End time must be after start time.")

        if self.start and self.end and self.area_id:
            overlapping = Booking.objects.filter(
                area_id=self.area_id,
                start__lt=self.end,
                end__gt=self.start,
            ).exclude(pk=self.pk)
            if overlapping.exists():
                raise ValidationError(
                    f"{self.area} is already booked at that time: {overlapping.first()}"
                )
