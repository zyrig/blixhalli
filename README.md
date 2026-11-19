# Blixhalli training scheduler

A web app for booking training times in Blixhalli. Teams book an area of the
hall (a court, the gym, …) for a time slot, and the app blocks double bookings.

Built with [Django](https://www.djangoproject.com/) (Python). It stores data in
SQLite, a database kept in a single file that needs no setup.

## Getting started

You need Python 3.12 or newer.

```bash
python3 -m venv .venv            # create an isolated Python environment
source .venv/bin/activate        # activate it (Windows: .venv\Scripts\activate)
pip install -r requirements.txt  # install Django
python manage.py migrate         # create the database tables
python manage.py createsuperuser # create an admin login for yourself
python manage.py runserver       # start the app
```

Then open:
- http://127.0.0.1:8000/ to see the weekly schedule
- http://127.0.0.1:8000/admin/ to add areas and teams, and manage bookings

Run the tests with `python manage.py test`.

## Where things live

| File | What it does |
|---|---|
| `bookings/models.py` | The data: Area, Team and Booking, plus the no-overlap rule |
| `bookings/views.py` | The logic behind each page |
| `bookings/templates/bookings/` | The HTML for each page |
| `bookings/urls.py` | Which URL goes to which view |
| `bookings/admin.py` | The admin panel setup |
| `bookings/tests.py` | Automated tests |
| `config/settings.py` | Project settings (time zone, database, installed apps) |

## Changing the data model

After editing `models.py`, run:

```bash
python manage.py makemigrations
python manage.py migrate
```

## Learning resources

- Official Django tutorial: https://docs.djangoproject.com/en/5.2/intro/tutorial01/
- Django Girls tutorial, written for beginners: https://tutorial.djangogirls.org/

## Possible next steps

- Recurring bookings (e.g. "every Tuesday 17–19 this season")
- Team logins, so teams can only edit their own bookings
- A grid calendar view with areas as columns
- Deploying online and switching to PostgreSQL
