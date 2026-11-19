#!/usr/bin/env bash
# Køyrer på Vercel ved kvar utrulling, etter at pakkane er installerte.
# Vercel samlar statiske filer (collectstatic) sjølv.
set -o errexit

# Berre produksjon oppdaterer databasen. Førehandsversjonar (t.d. frå andre greiner) skal ikkje
# endre den ekte databasen.
if [ "$VERCEL_ENV" = "production" ]; then
  python manage.py migrate --no-input
  python manage.py seed_if_empty
  python manage.py ensure_facilities
  python manage.py ensure_admin
else
  echo "Ikkje produksjon ($VERCEL_ENV): hoppar over databaseoppdatering."
fi
