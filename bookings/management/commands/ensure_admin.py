"""Lag den første administratoren frå miljøvariablar, viss han ikkje finst.

Brukar DJANGO_ADMIN_EMAIL og DJANGO_ADMIN_PASSWORD. Endrar aldri ein brukar som
alt finst, så passordet kan trygt endrast i appen etterpå.
"""
import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Lag første administrator frå DJANGO_ADMIN_EMAIL og DJANGO_ADMIN_PASSWORD."

    def handle(self, **options):
        email = os.environ.get("DJANGO_ADMIN_EMAIL", "").strip().lower()
        password = os.environ.get("DJANGO_ADMIN_PASSWORD", "")
        if not email or not password:
            self.stdout.write("DJANGO_ADMIN_EMAIL/DJANGO_ADMIN_PASSWORD er ikkje sette. Hoppar over.")
            return
        User = get_user_model()
        if User.objects.filter(username=email).exists():
            self.stdout.write(f"Administratoren {email} finst alt.")
            return
        User.objects.create_superuser(username=email, email=email, password=password)
        self.stdout.write(self.style.SUCCESS(f"Laga administrator {email}."))
