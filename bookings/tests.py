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
        admin = User.objects.create_user("admin", password="x")
        self.draft.facility.manager.admins.add(admin)
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
            "end_time": f"{end:02d}:00", "unit": "1-3", "note": "Ekstratrening"})

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
        admin = User.objects.create_user("a@example.com", "a@example.com", "pw")
        self.j12_slot.facility.owner.admins.add(admin)  # eigaren av anlegget (t.d. kommunen) kan overstyre
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
            "unit": "2-2"})
        from .models import Booking
        self.assertEqual(Booking.objects.get().facility, self.pitch)

    def test_reserved_slug_rejected(self):
        from .models import Facility
        with self.assertRaises(ValidationError):
            Facility(name="Mine", slug="mine").full_clean()



class UnitsAndRequestsTests(TestCase):
    """Delar som kan bookast per anlegg, og søknader om faste tider med godkjenning."""

    def setUp(self):
        from django.utils import timezone
        call_command("ensure_facilities", stdout=open("/dev/null", "w"))
        from .models import Facility
        self.f11 = Facility.objects.get(slug="kunstgras-11")
        self.f7 = Facility.objects.get(slug="kunstgras-7")
        self.gras = Facility.objects.get(slug="grasbane")
        self.g12 = Group.objects.create(name="Fotball G12", category="fotball")
        self.j14 = Group.objects.create(name="Fotball J14", category="fotball")
        self.kari = User.objects.create_user("kari@example.com", "kari@example.com", "pw", first_name="Kari")
        self.g12.leaders.add(self.kari)
        self.admin = User.objects.create_user("admin@example.com", "admin@example.com", "pw")
        from .models import Organization
        Organization.objects.get(slug="vikil").admins.add(self.admin)  # Vik IL fordeler tida på banane
        today = timezone.localdate()
        self.monday = today + datetime.timedelta(days=7 - today.weekday())
        self.end = self.monday + datetime.timedelta(days=60)

    def request_data(self, **kw):
        data = {"group": self.g12.pk, "weekday": 0, "start_time": "17:00", "end_time": "18:30", "unit": "1-2",
                "valid_from": self.monday.isoformat(), "valid_to": self.end.isoformat(), "message": "Takk"}
        data.update(kw)
        return data

    # --- delar ---

    def test_units_per_facility(self):
        sizes = {size: [label for *_, label in items] for size, items in self.f11.unit_options()}
        self.assertEqual(sizes, {"Heile bana": ["Heile bana"], "1/2 bane": ["A + B", "C + D"],
                                 "1/4 bane": ["A", "B", "C", "D"]})
        self.assertTrue(self.f11.allows(1, 2))
        self.assertFalse(self.f11.allows(2, 3))  # B + C er ikkje ein halvdel
        self.assertEqual(self.f11.sections_label(3, 4), "1/2 (C–D)")
        self.assertEqual(self.f11.sections_label(2, 2), "1/4 (B)")
        self.assertEqual([size for size, _ in self.gras.unit_options()], ["Heile bana", "1/2 bane"])
        self.assertEqual(self.f7.unit_options(), [("Heile bana", [(1, 1, "Heile bana")])])

    def test_invalid_units_config_rejected(self):
        from .models import Facility
        f = Facility(name="X", slug="x", section_labels="A,B", units="1/2: A, Q")
        with self.assertRaises(ValidationError):
            f.full_clean()

    def test_half_pitch_that_is_not_a_half_is_rejected(self):
        self.client.force_login(self.kari)
        r = self.client.post("/kunstgras-11/sok/", self.request_data(unit="2-3"))
        self.assertTrue(r.context["form"].has_error("unit"))

    def test_seven_a_side_has_no_division_choice(self):
        self.client.force_login(self.kari)
        r = self.client.get("/kunstgras-7/sok/")
        self.assertContains(r, ">Heile bana</option>")
        self.assertNotContains(r, "<optgroup")

    # --- søknader ---

    def test_request_approve_flow(self):
        from django.core import mail
        from .models import TrainingRequest
        self.client.force_login(self.kari)
        r = self.client.post("/kunstgras-11/sok/", self.request_data())
        self.assertRedirects(r, "/mine/")
        req = TrainingRequest.objects.get()
        self.assertEqual((req.status, req.facility, req.first_section, req.last_section),
                         ("pending", self.f11, 1, 2))
        self.assertIn("admin@example.com", mail.outbox[-1].to)
        # Ikkje synleg i vekeplanen før godkjenning
        week = f"/kunstgras-11/veke/{self.monday.isoformat()}/"
        self.assertNotContains(self.client.get(week), "Fotball G12")

        self.client.force_login(self.admin)
        self.assertContains(self.client.get("/soknader/"), "Fotball G12")
        self.client.post(f"/soknader/{req.pk}/godkjenn/")
        req.refresh_from_db()
        self.assertEqual(req.status, "approved")
        self.assertEqual((req.slot.valid_from, req.slot.valid_to, req.slot.facility), (self.monday, self.end, self.f11))
        self.assertIn("kari@example.com", mail.outbox[-1].to)
        self.assertContains(self.client.get(week), "Fotball G12")
        # Utanfor perioden blir tida ikkje vist
        after = self.end + datetime.timedelta(days=7)
        self.assertNotContains(self.client.get(f"/kunstgras-11/veke/{after.isoformat()}/"), "Fotball G12")

    def test_other_half_is_free_but_same_half_clashes(self):
        from .models import TrainingSlot
        TrainingSlot.objects.create(facility=self.f11, group=self.j14, weekday=0, start_time=t(17), end_time=t(18),
                                    first_section=1, last_section=2, valid_from=self.monday, valid_to=self.end)
        self.client.force_login(self.kari)
        self.client.post("/kunstgras-11/sok/", self.request_data(unit="3-4"))
        self.client.post("/kunstgras-11/sok/", self.request_data(unit="2-2"))
        from .models import TrainingRequest
        free, taken = TrainingRequest.objects.order_by("pk")
        self.assertIsNone(free.find_clash())
        self.assertIsNotNone(taken.find_clash())
        self.client.force_login(self.admin)
        self.client.post(f"/soknader/{taken.pk}/godkjenn/")
        taken.refresh_from_db()
        self.assertEqual(taken.status, "pending")  # kan ikkje godkjennast når tida er oppteken

    def test_clash_only_when_periods_overlap(self):
        from .models import TrainingSlot
        before_end = self.monday - datetime.timedelta(days=1)
        TrainingSlot.objects.create(facility=self.f11, group=self.j14, weekday=0, start_time=t(17), end_time=t(18),
                                    first_section=1, last_section=4, valid_from=datetime.date(2026, 1, 1),
                                    valid_to=before_end)
        self.client.force_login(self.kari)
        self.client.post("/kunstgras-11/sok/", self.request_data())
        from .models import TrainingRequest
        self.assertIsNone(TrainingRequest.objects.get().find_clash())

    def test_propose_and_accept(self):
        from django.core import mail
        from .models import TrainingRequest, TrainingSlot
        TrainingSlot.objects.create(facility=self.f11, group=self.j14, weekday=0, start_time=t(17), end_time=t(18),
                                    first_section=1, last_section=2, valid_from=self.monday, valid_to=self.end)
        self.client.force_login(self.kari)
        self.client.post("/kunstgras-11/sok/", self.request_data())
        req = TrainingRequest.objects.get()
        self.client.force_login(self.admin)
        r = self.client.post(f"/soknader/{req.pk}/foresla/", {
            "proposed_weekday": 0, "proposed_start_time": "17:00", "proposed_end_time": "18:30", "unit": "3-4",
            "proposed_valid_from": self.monday.isoformat(), "proposed_valid_to": self.end.isoformat(),
            "admin_comment": "A+B er opptekne, de kan få C+D."})
        self.assertRedirects(r, "/soknader/")
        req.refresh_from_db()
        self.assertEqual(req.status, "proposed")
        self.assertIn("C+D", mail.outbox[-1].body)
        self.client.force_login(self.kari)
        self.assertContains(self.client.get("/mine/"), "Godta forslaget")
        self.client.post(f"/soknad/{req.pk}/svar/", {"answer": "accept"})
        req.refresh_from_db()
        self.assertEqual(req.status, "approved")
        self.assertEqual((req.slot.first_section, req.slot.last_section), (3, 4))

    def test_proposal_that_also_clashes_is_rejected(self):
        from .models import TrainingRequest, TrainingSlot
        TrainingSlot.objects.create(facility=self.f11, group=self.j14, weekday=0, start_time=t(17), end_time=t(18),
                                    first_section=1, last_section=4, valid_from=self.monday, valid_to=self.end)
        self.client.force_login(self.kari)
        self.client.post("/kunstgras-11/sok/", self.request_data())
        req = TrainingRequest.objects.get()
        self.client.force_login(self.admin)
        r = self.client.post(f"/soknader/{req.pk}/foresla/", {
            "proposed_weekday": 0, "proposed_start_time": "17:00", "proposed_end_time": "18:30", "unit": "3-4",
            "proposed_valid_from": self.monday.isoformat(), "proposed_valid_to": self.end.isoformat()})
        self.assertContains(r, "kolliderer òg")

    def test_reject_and_withdraw(self):
        from .models import TrainingRequest
        self.client.force_login(self.kari)
        self.client.post("/kunstgras-11/sok/", self.request_data())
        self.client.post("/kunstgras-11/sok/", self.request_data(weekday=2))
        first, second = TrainingRequest.objects.order_by("pk")
        self.client.post(f"/soknad/{second.pk}/trekk/")
        second.refresh_from_db()
        self.assertEqual(second.status, "withdrawn")
        self.client.force_login(self.admin)
        self.client.post(f"/soknader/{first.pk}/avsla/", {"comment": "Fullt"})
        first.refresh_from_db()
        self.assertEqual((first.status, first.admin_comment), ("rejected", "Fullt"))

    def test_leader_can_only_request_for_own_team_and_not_manage_others(self):
        from .models import TrainingRequest
        self.client.force_login(self.kari)
        r = self.client.post("/kunstgras-11/sok/", self.request_data(group=self.j14.pk))
        self.assertTrue(r.context["form"].has_error("group"))
        other = TrainingRequest.objects.create(facility=self.f11, group=self.j14, weekday=0, start_time=t(17),
                                               end_time=t(18), valid_from=self.monday, valid_to=self.end)
        self.assertEqual(self.client.post(f"/soknad/{other.pk}/trekk/").status_code, 403)
        self.assertNotEqual(self.client.get("/soknader/").status_code, 200)  # berre administratorar

    def test_request_dates_must_be_valid(self):
        self.client.force_login(self.kari)
        r = self.client.post("/kunstgras-11/sok/", self.request_data(valid_to=(self.monday - datetime.timedelta(days=1)).isoformat()))
        self.assertContains(r, "Sluttdato kan ikkje vere før startdato")

    def test_ensure_facilities_is_idempotent_and_keeps_admin_changes(self):
        from .models import Facility
        self.f11.units = "1/2: A-B, C-D"
        self.f11.save()
        call_command("ensure_facilities", stdout=open("/dev/null", "w"))
        self.assertEqual(Facility.objects.count(), 4)
        self.f11.refresh_from_db()
        self.assertEqual(self.f11.units, "1/2: A-B, C-D")


class OrganizationTests(TestCase):
    """Fleire organisasjonar: kommunen eig anlegga og fordeler hallen, Vik IL fordeler banane og
    fordeler vidare blokker dei har fått i hallen. Andre organisasjonar (t.d. Vik fengsel) må godkjennast av
    den som fordeler tida på anlegget."""

    def setUp(self):
        from django.utils import timezone
        from .models import Facility, Organization
        call_command("ensure_facilities", stdout=open("/dev/null", "w"))
        self.kommune = Organization.objects.get(slug="vik-kommune")
        self.vikil = Organization.objects.get(slug="vikil")
        self.fengsel = Organization.objects.create(workspace=self.vikil.workspace, name="Vik fengsel",
                                                   slug="vik-fengsel", kind="anna")
        self.hall = Facility.objects.get(slug="blixhalli")
        self.f11 = Facility.objects.get(slug="kunstgras-11")
        self.g12 = Group.objects.create(organization=self.vikil, name="Fotball G12", category="fotball")
        self.fengsel_group = Group.objects.create(organization=self.fengsel, name="Vik fengsel")
        mk = lambda name: User.objects.create_user(f"{name}@example.com", f"{name}@example.com", "pw")  # noqa: E731
        self.kommune_admin, self.vikil_admin, self.leader, self.fengsel_leader = (
            mk("kommune"), mk("vikil"), mk("leiar"), mk("fengsel"))
        self.kommune.admins.add(self.kommune_admin)
        self.vikil.admins.add(self.vikil_admin)
        self.g12.leaders.add(self.leader)
        self.fengsel_group.leaders.add(self.fengsel_leader)
        today = timezone.localdate()
        self.monday = today + datetime.timedelta(days=7 - today.weekday())
        self.end = self.monday + datetime.timedelta(days=60)

    def allocate_vikil_monday(self):
        from .models import Allocation
        a = Allocation(facility=self.hall, organization=self.vikil, weekday=0, start_time=t(17), end_time=t(21),
                       first_section=1, last_section=3)
        a.full_clean()
        a.save()
        return a

    def request(self, user, facility, group, start=18, end=19, unit="1-3"):
        self.client.force_login(user)
        self.client.post(f"/{facility.slug}/sok/", {
            "group": group.pk, "weekday": 0, "start_time": f"{start}:00", "end_time": f"{end}:00", "unit": unit,
            "valid_from": self.monday.isoformat(), "valid_to": self.end.isoformat()})
        from .models import TrainingRequest
        return TrainingRequest.objects.latest("pk")

    def book(self, user, facility, group, start=18, end=19, unit="1-1"):
        self.client.force_login(user)
        self.client.post(f"/{facility.slug}/enkelttid/ny/", {
            "group": group.pk, "date": self.monday.isoformat(), "start_time": f"{start}:00",
            "end_time": f"{end}:00", "unit": unit})
        from .models import Booking
        return Booking.objects.latest("pk")

    # --- godkjenning hos rett organisasjon ---

    def test_hall_request_outside_allocation_goes_to_kommune(self):
        r = self.request(self.leader, self.hall, self.g12)
        from .permissions import can_approve_request
        self.assertFalse(can_approve_request(self.vikil_admin, r))
        self.assertTrue(can_approve_request(self.kommune_admin, r))
        self.client.force_login(self.vikil_admin)
        self.assertEqual(self.client.post(f"/soknader/{r.pk}/godkjenn/").status_code, 403)
        self.assertNotContains(self.client.get("/soknader/"), "Fotball G12")
        self.client.force_login(self.kommune_admin)
        self.client.post(f"/soknader/{r.pk}/godkjenn/")
        r.refresh_from_db()
        self.assertEqual(r.status, "approved")

    def test_vikil_admin_distributes_own_block(self):
        self.allocate_vikil_monday()
        r = self.request(self.leader, self.hall, self.g12)
        self.client.force_login(self.vikil_admin)
        self.assertContains(self.client.get("/soknader/"), "Fotball G12")
        self.client.post(f"/soknader/{r.pk}/godkjenn/")
        r.refresh_from_db()
        self.assertEqual(r.status, "approved")

    def test_other_organization_cannot_get_time_in_vikil_block(self):
        self.allocate_vikil_monday()
        r = self.request(self.fengsel_leader, self.hall, self.fengsel_group)
        self.assertIsNotNone(r.find_clash())  # blokka er Vik IL sin
        from .permissions import can_approve_request
        self.assertFalse(can_approve_request(self.vikil_admin, r))
        self.assertTrue(can_approve_request(self.kommune_admin, r))

    def test_allocation_cannot_overlap_another_organizations_time(self):
        self.allocate_vikil_monday()
        from .models import Allocation
        with self.assertRaises(ValidationError):
            Allocation(facility=self.hall, organization=self.fengsel, weekday=0, start_time=t(20), end_time=t(22),
                       first_section=1, last_section=1).full_clean()
        # Vik IL sine eigne lag kan trene inne i blokka
        TrainingSlot(facility=self.hall, group=self.g12, weekday=0, start_time=t(18), end_time=t(19),
                     first_section=1, last_section=3).full_clean()

    # --- enkelttider ---

    def test_booking_inside_own_block_is_approved_at_once(self):
        self.allocate_vikil_monday()
        self.assertEqual(self.book(self.leader, self.hall, self.g12, unit="1-3").status, "approved")

    def test_booking_outside_block_waits_for_kommune(self):
        b = self.book(self.leader, self.hall, self.g12, start=10, end=11, unit="1-3")
        self.assertEqual(b.status, "pending")
        self.client.force_login(self.vikil_admin)
        self.assertEqual(self.client.post(f"/soknader/enkelttid/{b.pk}/", {"answer": "approve"}).status_code, 403)
        self.client.force_login(self.kommune_admin)
        self.client.post(f"/soknader/enkelttid/{b.pk}/", {"answer": "approve"})
        b.refresh_from_db()
        self.assertEqual(b.status, "approved")

    def test_pitch_bookings(self):
        # Vik IL fordeler banane: eige lag får tida med ein gong, andre må godkjennast av Vik IL
        self.assertEqual(self.book(self.leader, self.f11, self.g12).status, "approved")
        b = self.book(self.fengsel_leader, self.f11, self.fengsel_group, start=20, end=21)
        self.assertEqual(b.status, "pending")
        self.client.force_login(self.vikil_admin)
        self.client.post(f"/soknader/enkelttid/{b.pk}/", {"answer": "approve"})
        b.refresh_from_db()
        self.assertEqual(b.status, "approved")

    def test_kommune_can_override_on_pitches(self):
        slot = TrainingSlot.objects.create(facility=self.f11, group=self.g12, weekday=0, start_time=t(17),
                                           end_time=t(18), first_section=1, last_section=4)
        self.client.force_login(self.fengsel_leader)
        self.assertEqual(self.client.get(f"/avlys/{slot.pk}/").status_code, 403)
        self.client.force_login(self.kommune_admin)  # eigar av bana
        r = self.client.post(f"/avlys/{slot.pk}/", {"date": self.monday.isoformat(), "reason": "Kommunalt arr."})
        self.assertEqual(r.status_code, 302)

    # --- admin ---

    def test_org_admins_get_scoped_admin_access(self):
        self.vikil_admin.refresh_from_db()
        self.assertTrue(self.vikil_admin.is_staff)
        self.client.force_login(self.vikil_admin)
        r = self.client.get("/admin/bookings/group/")
        self.assertContains(r, "Fotball G12")
        self.assertNotContains(r, "Vik fengsel</a>")
        self.assertNotEqual(self.client.get(f"/admin/bookings/group/{self.fengsel_group.pk}/change/").status_code, 200)
        # Kommunen ser hallen den fordeler, Vik IL ser banane
        self.assertNotContains(self.client.get("/admin/bookings/facility/"), "Blixhalli")
        self.client.force_login(User.objects.get(pk=self.kommune_admin.pk))
        self.assertContains(self.client.get("/admin/bookings/facility/"), "Blixhalli")

    # --- område ---

    def test_workspace_from_host(self):
        import os
        from unittest import mock
        from django.test import override_settings
        from .models import Facility, Organization, Workspace
        other = Workspace.objects.create(name="Anna", slug="anna", domain="treningstider.annaklubb.no")
        org = Organization.objects.create(workspace=other, name="Anna IL", slug="annail")
        Facility.objects.create(workspace=other, owner=org, manager=org, name="Annahallen", slug="blixhalli")
        with override_settings(ALLOWED_HOSTS=[".treningstider.no", "treningstider.annaklubb.no", "testserver"]), \
                mock.patch.dict(os.environ, {"BASE_DOMAIN": "treningstider.no"}):
            self.assertContains(self.client.get("/blixhalli/", HTTP_HOST="anna.treningstider.no"), "Annahallen")
            self.assertContains(self.client.get("/blixhalli/", HTTP_HOST="treningstider.annaklubb.no"), "Annahallen")
            r = self.client.get("/blixhalli/", HTTP_HOST="vik.treningstider.no")
            self.assertContains(r, "Kunstgras 11")
            self.assertNotContains(r, "Annahallen")

    # --- Excel ---

    def test_excel_export(self):
        import io
        import openpyxl
        TrainingSlot.objects.create(facility=self.hall, group=self.g12, weekday=0, start_time=t(17),
                                    end_time=t(18, 30), first_section=1, last_section=2)
        r = self.client.get(f"/eksport/?dato={self.monday.isoformat()}")
        self.assertEqual(r.status_code, 200)
        self.assertIn("attachment", r["Content-Disposition"])
        wb = openpyxl.load_workbook(io.BytesIO(r.content))
        self.assertEqual(wb.sheetnames[:2], ["Liste", "Blixhalli"])
        ws = wb["Blixhalli"]
        cells = {c.value: c.coordinate for row in ws.iter_rows() for c in row if c.value}
        self.assertIn("Fotball G12 (Vik IL)", cells)
        merged = [str(m) for m in ws.merged_cells.ranges if str(m).startswith(cells["Fotball G12 (Vik IL)"])]
        self.assertTrue(merged)  # samanslått over 1/3–2/3 og tre halvtimar
        rows = [[c.value for c in row] for row in wb["Liste"].iter_rows(min_row=4)]
        self.assertIn(["Blixhalli", "Måndag", "17:00", "18:30", "1/3–2/3", "Fotball G12", "Vik IL", None, None], rows)
