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
        r = self.client.get("/")
        self.assertContains(r, "Fotball J12")
        self.assertContains(r, "grid-row: 19 / 21")  # 17:30 er rad 19 når rutenettet startar 09:00

    def test_draft_hidden_from_public(self):
        self.assertEqual(self.client.get(f"/sesong/{self.draft.pk}/").status_code, 404)

    def test_draft_visible_to_staff(self):
        User.objects.create_user("admin", password="x", is_staff=True)
        self.client.login(username="admin", password="x")
        self.assertContains(self.client.get(f"/sesong/{self.draft.pk}/"), "Utkast")

    def test_empty_site(self):
        Season.objects.all().delete()
        self.assertContains(self.client.get("/"), "Ingen sesongar")


class StaticExportTests(TestCase):
    def test_export_writes_one_page_per_season_with_relative_links(self):
        Season.objects.create(name="2025/2026", published=True)
        Season.objects.create(name="2026/2027", published=False)
        with tempfile.TemporaryDirectory() as out:
            call_command("export_static", "--out", out, stdout=open("/dev/null", "w"))
            import os
            self.assertEqual(sorted(os.listdir(out)), [".nojekyll", "index.html", "sesong-2025-2026.html"])
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
