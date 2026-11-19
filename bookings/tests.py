"""Automated tests. Run them with: python manage.py test"""
import datetime

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from .models import Area, Booking, Team


def at(hour):
    return timezone.make_aware(datetime.datetime(2026, 12, 1, hour, 0))


class BookingRulesTests(TestCase):
    def setUp(self):
        self.court = Area.objects.create(name="Court 1")
        self.team = Team.objects.create(name="Juniors")
        Booking.objects.create(area=self.court, team=self.team, start=at(17), end=at(19))

    def test_overlapping_booking_is_rejected(self):
        b = Booking(area=self.court, team=self.team, start=at(18), end=at(20))
        with self.assertRaises(ValidationError):
            b.full_clean()

    def test_back_to_back_booking_is_allowed(self):
        Booking(area=self.court, team=self.team, start=at(19), end=at(20)).full_clean()

    def test_other_area_same_time_is_allowed(self):
        gym = Area.objects.create(name="Gym")
        Booking(area=gym, team=self.team, start=at(17), end=at(19)).full_clean()

    def test_end_before_start_is_rejected(self):
        with self.assertRaises(ValidationError):
            Booking(area=self.court, team=self.team, start=at(20), end=at(19)).full_clean()


class PageTests(TestCase):
    def test_schedule_page_loads(self):
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_new_booking_page_loads(self):
        self.assertEqual(self.client.get("/new/").status_code, 200)
