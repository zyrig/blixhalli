"""Automatiske testar. Køyr dei med: python manage.py test"""
import datetime
import tempfile

import openpyxl
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase

from .management.commands.import_timeplan import clean_name
from .models import Group, Season, TrainingSlot


def t(h, m=0):
    return datetime.time(h, m)


class ClashRulesTests(TestCase):
    def setUp(self):
        self.season = Season.objects.create(name="2026/2027", published=True)
        self.group = Group.objects.create(name="Handball J13")
        TrainingSlot.objects.create(season=self.season, group=self.group, weekday=0,
                                    start_time=t(17), end_time=t(18), first_section=1, last_section=2)

    def slot(self, **kw):
        data = dict(season=self.season, group=self.group, weekday=0, start_time=t(17), end_time=t(18),
                    first_section=1, last_section=3)
        data.update(kw)
        return TrainingSlot(**data)

    def test_same_section_same_time_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.slot(first_section=2, last_section=2).full_clean()

    def test_free_section_same_time_is_allowed(self):
        self.slot(first_section=3, last_section=3).full_clean()

    def test_back_to_back_is_allowed(self):
        self.slot(start_time=t(18), end_time=t(19)).full_clean()

    def test_other_weekday_is_allowed(self):
        self.slot(weekday=1).full_clean()

    def test_other_season_is_allowed(self):
        self.slot(season=Season.objects.create(name="2027/2028")).full_clean()

    def test_non_overlapping_date_ranges_are_allowed(self):
        TrainingSlot.objects.all().update(valid_to=datetime.date(2026, 12, 31))
        self.slot(valid_from=datetime.date(2027, 1, 1)).full_clean()

    def test_end_before_start_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.slot(weekday=3, start_time=t(19), end_time=t(18)).full_clean()

    def test_sections_in_wrong_order_are_rejected(self):
        with self.assertRaises(ValidationError):
            self.slot(weekday=3, first_section=3, last_section=1).full_clean()


class CategoryTests(TestCase):
    def test_first_sport_word_wins(self):
        self.assertEqual(Group.guess_category("Friidrett - turn, Fotball etter nyttår"), "friidrett")
        self.assertEqual(Group.guess_category("Trim Zumba"), "trim")
        self.assertEqual(Group.guess_category("Vik fengsel"), "anna")


class ImportTests(TestCase):
    def test_clean_name(self):
        self.assertEqual(clean_name("Trim, Zumba (?)"), ("Trim, Zumba", True))
        self.assertEqual(clean_name("Forslag: Vik Ørsta"), ("Vik Ørsta", True))
        self.assertEqual(clean_name("Handball   J11 "), ("Handball J11", False))

    def test_import_reads_merged_cells_as_duration_and_sections(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "1 utkast 2026-27"
        ws["A1"] = "Treningstider Blixhalli 2026/2027"
        ws["A3"] = "DAG/TID"
        ws["A4"] = "SAL"
        for i, label in enumerate(["17.00-17.30", "17.30-18.00", "18.00-18.30"]):
            ws.cell(5 + i, 1, label)
        ws["B5"] = "Handball J11"   # måndag, heile salen, 17:00–18:00
        ws.merge_cells("B5:D6")
        ws["F7"] = "Volleyball ?"   # tysdag, del 2, 18:00–18:30
        ws["A9"] = "Merknad om tysdag"
        with tempfile.NamedTemporaryFile(suffix=".xlsx") as f:
            wb.save(f.name)
            call_command("import_timeplan", f.name, stdout=open("/dev/null", "w"))

        season = Season.objects.get(name="2026/2027")
        self.assertFalse(season.published)
        self.assertIn("Merknad om tysdag", season.notes)
        hb = TrainingSlot.objects.get(group__name="Handball J11")
        self.assertEqual((hb.weekday, hb.start_time, hb.end_time, hb.first_section, hb.last_section),
                         (0, t(17), t(18), 1, 3))
        vb = TrainingSlot.objects.get(group__name="Volleyball")
        self.assertEqual((vb.weekday, vb.start_time, vb.end_time, vb.first_section, vb.last_section, vb.tentative),
                         (1, t(18), t(18, 30), 2, 2, True))


class PageTests(TestCase):
    def setUp(self):
        self.published = Season.objects.create(name="2025/2026", published=True)
        self.draft = Season.objects.create(name="2026/2027", published=False)
        group = Group.objects.create(name="Fotball J12", category="fotball")
        TrainingSlot.objects.create(season=self.published, group=group, weekday=4,
                                    start_time=t(17, 30), end_time=t(18, 30))

    def test_schedule_shows_published_season(self):
        r = self.client.get("/blixhalli/sesong/")
        self.assertContains(r, "Fotball J12")
        self.assertContains(r, "grid-row: 19 / 21")  # 17:30 er rad 19 når rutenettet startar 09:00

    def test_draft_hidden_from_public(self):
        self.assertEqual(self.client.get(f"/blixhalli/sesong/{self.draft.pk}/").status_code, 404)

    def test_draft_visible_to_staff(self):
        User.objects.create_user("admin", password="x", is_staff=True)
        self.client.login(username="admin", password="x")
        self.assertContains(self.client.get(f"/blixhalli/sesong/{self.draft.pk}/"), "Utkast")

    def test_empty_site(self):
        Season.objects.all().delete()
        self.assertContains(self.client.get("/blixhalli/sesong/"), "Ingen sesongar")


class StaticExportTests(TestCase):
    def test_export_writes_one_page_per_season_with_relative_links(self):
        Season.objects.create(name="2025/2026", published=True)
        Season.objects.create(name="2026/2027", published=False)
        with tempfile.TemporaryDirectory() as out:
            call_command("export_static", "--out", out, stdout=open("/dev/null", "w"))
            import os
            self.assertEqual(sorted(os.listdir(out)),
                             [".nojekyll", "blixhalli-sesong-2025-2026.html", "blixhalli.html", "index.html"])
            html = open(os.path.join(out, "index.html"), encoding="utf-8").read()
            self.assertNotIn('href="/', html)   # GitHub Pages ligg under /blixhalli/
            self.assertNotIn("Logg inn", html)


class AccountTests(TestCase):
    """Steg 1: brukarar, lagleiarar og førespurnader om brukar."""

    def setUp(self):
        self.season = Season.objects.create(name="2025/2026", published=True)
        self.j12 = Group.objects.create(name="Handball J12")
        self.g8 = Group.objects.create(name="Fotball G8")
        TrainingSlot.objects.create(season=self.season, group=self.j12, weekday=0, start_time=t(17), end_time=t(18))
        TrainingSlot.objects.create(season=self.season, group=self.g8, weekday=1, start_time=t(17), end_time=t(18))
        self.admin = User.objects.create_user("admin@example.com", "admin@example.com", "pw", is_staff=True, is_superuser=True)

    def last_link(self):
        from django.core import mail
        import re
        return re.search(r"http://testserver(/passord/ny/\S+)", mail.outbox[-1].body).group(1)

    def test_request_account_and_get_approved_then_set_password_and_log_in(self):
        from django.core import mail
        from .models import AccountRequest
        r = self.client.post("/be-om-brukar/", {"name": "Kari Nordmann", "email": "Kari@Example.com",
                                                "groups": [self.j12.pk]})
        self.assertContains(r, "Takk, Kari Nordmann")
        req = AccountRequest.objects.get()
        self.assertEqual((req.email, req.status), ("kari@example.com", "pending"))
        self.assertIn("Kari Nordmann", mail.outbox[-1].subject)  # administrator får varsel

        # Administrator godkjenner via admin-handlinga
        self.client.force_login(self.admin)
        self.client.post("/admin/bookings/accountrequest/", {"action": "approve_selected", "_selected_action": [req.pk]})
        self.client.logout()
        req.refresh_from_db()
        self.assertEqual(req.status, "approved")
        self.assertEqual(mail.outbox[-1].to, ["kari@example.com"])
        self.assertIn("Handball J12", mail.outbox[-1].body)

        # Kari lagar passord via lenkja og loggar inn
        r = self.client.get(self.last_link(), follow=True)
        self.assertContains(r, "Lag passord")
        self.client.post(r.redirect_chain[-1][0], {"new_password1": "Sterkt-passord-42", "new_password2": "Sterkt-passord-42"})
        r = self.client.post("/logg-inn/", {"username": "KARI@example.com", "password": "Sterkt-passord-42"}, follow=True)
        self.assertContains(r, "Hei, Kari")
        self.assertContains(r, "Handball J12")
        self.assertNotContains(r, "Fotball G8")  # ser berre sine eigne lag

    def test_reject_sends_email_with_comment(self):
        from django.core import mail
        from .models import AccountRequest
        req = AccountRequest.objects.create(name="Ola", email="ola@example.com", other_group="Ukjent lag",
                                            admin_comment="Ta kontakt med styret.")
        self.client.force_login(self.admin)
        self.client.post("/admin/bookings/accountrequest/", {"action": "reject_selected", "_selected_action": [req.pk]})
        req.refresh_from_db()
        self.assertEqual(req.status, "rejected")
        self.assertIn("Ta kontakt med styret.", mail.outbox[-1].body)

    def test_request_needs_a_group_and_no_duplicates(self):
        r = self.client.post("/be-om-brukar/", {"name": "Per", "email": "per@example.com"})
        self.assertContains(r, "Vel minst eitt lag")
        r = self.client.post("/be-om-brukar/", {"name": "Admin", "email": "ADMIN@example.com", "other_group": "X"})
        self.assertContains(r, "Det finst alt ein brukar")

    def test_admin_can_invite_user_and_others_cannot(self):
        from django.core import mail
        self.client.force_login(self.admin)
        r = self.client.post("/inviter/", {"name": "Lise Lagleiar", "email": "lise@example.com",
                                          "groups": [self.g8.pk]}, follow=True)
        self.assertContains(r, "Invitasjon sendt til lise@example.com")
        lise = User.objects.get(username="lise@example.com")
        self.assertFalse(lise.has_usable_password())
        self.assertEqual(list(lise.led_groups.all()), [self.g8])
        self.assertIn("/passord/ny/", mail.outbox[-1].body)

        self.client.force_login(lise)
        self.assertNotEqual(self.client.get("/inviter/").status_code, 200)

    def test_forgot_password_works_for_invited_user_without_password(self):
        from django.core import mail
        from . import accounts
        accounts.create_or_update_user("Nils", "nils@example.com", [])
        self.client.post("/passord/gloymt/", {"email": "nils@example.com"})
        self.assertEqual(mail.outbox[-1].to, ["nils@example.com"])

    def test_mine_requires_login(self):
        self.assertRedirects(self.client.get("/mine/"), "/logg-inn/?next=/mine/")


class LeaderPermissionAndWeekTests(TestCase):
    """Steg 2: lagleiarar administrerer berre sine eigne lag; avlysingar og enkelttider."""

    def setUp(self):
        from django.utils import timezone
        today = timezone.localdate()
        self.monday = today + datetime.timedelta(days=7 - today.weekday())  # neste måndag
        self.season = Season.objects.create(name="Test", published=True,
                                            start_date=datetime.date(2000, 1, 1), end_date=datetime.date(2100, 1, 1))
        self.j12 = Group.objects.create(name="Handball J12", category="handball")
        self.g8 = Group.objects.create(name="Fotball G8", category="fotball")
        self.j12_slot = TrainingSlot.objects.create(season=self.season, group=self.j12, weekday=0,
                                                    start_time=t(17), end_time=t(18))
        self.g8_slot = TrainingSlot.objects.create(season=self.season, group=self.g8, weekday=0,
                                                   start_time=t(18), end_time=t(19))
        self.kari = User.objects.create_user("kari@example.com", "kari@example.com", "pw", first_name="Kari")
        self.j12.leaders.add(self.kari)
        self.client.force_login(self.kari)

    def book(self, group, start=17, end=18, date=None):
        return self.client.post("/blixhalli/enkelttid/ny/", {
            "group": group.pk, "date": (date or self.monday).isoformat(), "start_time": f"{start:02d}:00",
            "end_time": f"{end:02d}:00", "first_section": 1, "last_section": 3, "note": "Ekstratrening"})

    def test_everyone_sees_who_has_which_time(self):
        self.client.logout()
        r = self.client.get(f"/blixhalli/veke/{self.monday.isoformat()}/")
        self.assertContains(r, "Handball J12")
        self.assertContains(r, "Fotball G8")
        self.assertNotContains(r, "/avlys/")  # men ingen lenkjer for å endre

    def test_leader_can_cancel_own_slot_but_not_other_teams(self):
        self.assertEqual(self.client.get(f"/avlys/{self.g8_slot.pk}/").status_code, 403)
        r = self.client.post(f"/avlys/{self.g8_slot.pk}/", {"date": self.monday.isoformat()})
        self.assertEqual(r.status_code, 403)
        r = self.client.post(f"/avlys/{self.j12_slot.pk}/", {"date": self.monday.isoformat(), "reason": "Cup"})
        self.assertRedirects(r, f"/blixhalli/veke/{self.monday.isoformat()}/")
        page = self.client.get(f"/blixhalli/veke/{self.monday.isoformat()}/")
        self.assertContains(page, "Avlyst: Cup")
        next_week = self.client.get(f"/blixhalli/veke/{(self.monday + datetime.timedelta(days=7)).isoformat()}/")
        self.assertContains(next_week, f"/avlys/{self.j12_slot.pk}/")      # eigen tid: lenkje
        self.assertNotContains(next_week, f"/avlys/{self.g8_slot.pk}/")    # andre sine: inga lenkje

    def test_cancel_wrong_weekday_is_rejected(self):
        r = self.client.post(f"/avlys/{self.j12_slot.pk}/", {"date": (self.monday + datetime.timedelta(days=1)).isoformat()})
        self.assertContains(r, "har ikkje denne treningstida")

    def test_booking_only_for_own_teams(self):
        r = self.book(self.g8, 20, 21)
        self.assertEqual(r.status_code, 200)  # skjemaet blir vist på nytt med feil, laget er ikkje eit gyldig val
        self.assertTrue(r.context["form"].has_error("group"))
        from .models import Booking
        self.assertFalse(Booking.objects.exists())

    def test_booking_on_taken_slot_is_rejected_until_cancelled(self):
        from .models import Booking
        r = self.book(self.j12, 18, 19)  # G8 har denne tida
        self.assertContains(r, "Opptatt")
        self.assertFalse(Booking.objects.exists())
        # G8 avlyser, og då er plassen ledig
        from .models import Cancellation
        Cancellation.objects.create(slot=self.g8_slot, date=self.monday)
        r = self.book(self.j12, 18, 19)
        self.assertRedirects(r, f"/blixhalli/veke/{self.monday.isoformat()}/")
        self.assertEqual(Booking.objects.get().status, "approved")
        self.assertContains(self.client.get(f"/blixhalli/veke/{self.monday.isoformat()}/"), "enkelttid")

    def test_double_booking_is_rejected(self):
        self.assertEqual(self.book(self.j12, 20, 21).status_code, 302)
        self.assertContains(self.book(self.j12, 20, 21), "Opptatt")

    def test_undo_cancellation_blocked_when_slot_is_taken(self):
        from .models import Cancellation
        c = Cancellation.objects.create(slot=self.j12_slot, date=self.monday)
        boss = User.objects.create_user("boss@example.com", "boss@example.com", "pw", is_staff=True)
        self.g8.leaders.add(boss)
        self.client.force_login(boss)
        self.assertEqual(self.book(self.g8, 17, 18).status_code, 302)
        self.client.force_login(self.kari)
        r = self.client.post(f"/avlysing/{c.pk}/angre/", follow=True)
        self.assertContains(r, "Kan ikkje angre")
        self.assertTrue(Cancellation.objects.filter(pk=c.pk).exists())

    def test_leader_cannot_delete_other_teams_booking(self):
        from .models import Booking
        b = Booking.objects.create(group=self.g8, date=self.monday, start_time=t(20), end_time=t(21))
        self.assertEqual(self.client.post(f"/enkelttid/{b.pk}/slett/").status_code, 403)
        self.assertTrue(Booking.objects.filter(pk=b.pk).exists())

    def test_admin_can_manage_all_teams(self):
        admin = User.objects.create_user("a@example.com", "a@example.com", "pw", is_staff=True)
        self.client.force_login(admin)
        r = self.client.post(f"/avlys/{self.g8_slot.pk}/", {"date": self.monday.isoformat()})
        self.assertEqual(r.status_code, 302)

    def test_past_dates_rejected(self):
        r = self.book(self.j12, 20, 21, date=datetime.date(2020, 1, 6))
        self.assertContains(r, "Datoen har vore")


class DeploySetupTests(TestCase):
    """Kommandoane som build.sh køyrer ved kvar deploy på Render."""

    def test_seed_if_empty_loads_once(self):
        call_command("seed_if_empty", stdout=open("/dev/null", "w"))
        count = TrainingSlot.objects.count()
        self.assertGreater(count, 0)
        call_command("seed_if_empty", stdout=open("/dev/null", "w"))
        self.assertEqual(TrainingSlot.objects.count(), count)

    def test_ensure_admin_creates_once_and_never_changes_password(self):
        import os
        from unittest import mock
        env = {"DJANGO_ADMIN_EMAIL": "Leiar@Example.com", "DJANGO_ADMIN_PASSWORD": "fyrste-passord"}
        with mock.patch.dict(os.environ, env):
            call_command("ensure_admin", stdout=open("/dev/null", "w"))
        admin = User.objects.get(username="leiar@example.com")
        self.assertTrue(admin.is_superuser and admin.is_staff)
        admin.set_password("nytt-passord")
        admin.save()
        with mock.patch.dict(os.environ, env):
            call_command("ensure_admin", stdout=open("/dev/null", "w"))
        admin.refresh_from_db()
        self.assertTrue(admin.check_password("nytt-passord"))



class FacilityTests(TestCase):
    """Fleire anlegg: hallen og fotballbanar ute, kvar med si eiga inndeling."""

    def setUp(self):
        from .models import Facility
        self.hall = Facility.objects.create(name="Blixhalli", slug="blixhalli", section_labels="1/3,2/3,3/3")
        self.pitch = Facility.objects.create(name="Kunstgraset", slug="kunstgras", kind=Facility.PITCH,
                                             section_labels="A,B", order=1)
        wide = dict(start_date=datetime.date(2000, 1, 1), end_date=datetime.date(2100, 1, 1), published=True)
        self.hall_season = Season.objects.create(facility=self.hall, name="2026/2027", **wide)
        self.pitch_season = Season.objects.create(facility=self.pitch, name="2026/2027", **wide)
        self.group = Group.objects.create(name="Fotball G12", category="fotball")
        from django.utils import timezone
        today = timezone.localdate()
        self.monday = today + datetime.timedelta(days=7 - today.weekday())

    def test_same_season_name_allowed_per_facility_and_sections_follow_facility(self):
        slot = TrainingSlot.objects.create(season=self.pitch_season, group=self.group, weekday=0,
                                           start_time=t(17), end_time=t(18), first_section=1, last_section=2)
        self.assertEqual(slot.sections_label, "Heile bana")
        slot.last_section = 1
        self.assertEqual(slot.sections_label, "A")

    def test_too_many_sections_rejected(self):
        with self.assertRaises(ValidationError):
            TrainingSlot(season=self.pitch_season, group=self.group, weekday=0, start_time=t(17), end_time=t(18),
                         first_section=1, last_section=3).full_clean()

    def test_clashes_are_per_facility(self):
        from .models import Booking
        TrainingSlot.objects.create(season=self.hall_season, group=self.group, weekday=0,
                                    start_time=t(17), end_time=t(18), first_section=1, last_section=3)
        # Same tid på bana er heilt greitt
        Booking(facility=self.pitch, group=self.group, date=self.monday, start_time=t(17), end_time=t(18),
                first_section=1, last_section=2).full_clean()
        with self.assertRaises(ValidationError):
            Booking(facility=self.hall, group=self.group, date=self.monday, start_time=t(17), end_time=t(18),
                    first_section=1, last_section=1).full_clean()

    def test_pages_per_facility_with_tabs(self):
        TrainingSlot.objects.create(season=self.pitch_season, group=self.group, weekday=0,
                                    start_time=t(17), end_time=t(18), first_section=2, last_section=2)
        self.assertRedirects(self.client.get("/"), "/blixhalli/")
        r = self.client.get(f"/kunstgras/veke/{self.monday.isoformat()}/")
        self.assertContains(r, "Fotball G12")
        self.assertContains(r, 'href="/blixhalli/"')          # fane til det andre anlegget
        self.assertContains(r, "--n: 2")                       # to kolonnar per dag
        hall = self.client.get(f"/blixhalli/veke/{self.monday.isoformat()}/")
        self.assertNotContains(hall, "Fotball G12")
        self.assertEqual(self.client.get("/finst-ikkje/").status_code, 404)

    def test_booking_form_offers_facility_sections(self):
        user = User.objects.create_user("l@example.com", "l@example.com", "pw")
        self.group.leaders.add(user)
        self.client.force_login(user)
        r = self.client.get("/kunstgras/enkelttid/ny/")
        self.assertContains(r, ">A</option>")
        self.assertNotContains(r, ">1/3</option>")
        r = self.client.post("/kunstgras/enkelttid/ny/", {
            "group": self.group.pk, "date": self.monday.isoformat(), "start_time": "17:00", "end_time": "18:00",
            "first_section": 2, "last_section": 2})
        from .models import Booking
        self.assertEqual(Booking.objects.get().facility, self.pitch)

    def test_reserved_slug_rejected(self):
        from .models import Facility
        with self.assertRaises(ValidationError):
            Facility(name="Mine", slug="mine").full_clean()
