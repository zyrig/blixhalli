# Treningstider Blixhalli

Ein nettapp for å setje opp og vise treningstidene i Blixhalli. Han fungerer i
nettlesaren på både PC og mobil.

- **Vekeplan per sesong** (t.d. 2026/2027), lagt opp som rutenett slik som i reknearket.
- **Salen er delt i tre** (1/3, 2/3, 3/3). Ei treningstid brukar éin, to eller alle tre delane.
- **Kollisjonskontroll:** appen stoppar to grupper frå å få same del av salen samstundes.
- **Utkast:** ein sesong kan vere eit utkast som berre dei som er logga inn ser.
- **Tider som ikkje er avklarte** (forslag, "?") blir viste med stipla kant.
- **Mobil:** éin dag om gongen, med knappar for å byte dag. **PC:** heile veka.
- **Redigering:** gjennom administrasjonssida (`/admin/`) etter innlogging.
- **Import** av det gamle Excel-arket.

Laga med [Django](https://www.djangoproject.com/) (Python). Data blir lagra i
SQLite, ein database som ligg i éi fil og ikkje treng noko oppsett.

## Brukarar og roller

- **Alle** kan sjå vekeplanen utan å logge inn.
- **Trenarar/lagleiarar** loggar inn med e-post og passord på `/logg-inn/`, og ser laga og tidene sine under «Mine lag».
- **Administratorar** (brukarar med «staff»-tilgang) kan endre alt via `/admin/` og invitere brukarar på `/inviter/`.

Nye brukarar kan kome inn på to måtar:
1. **Administrator inviterer** på `/inviter/`. Brukaren får ein e-post med ei lenkje for å lage passord.
2. **Brukaren ber sjølv om brukar** på `/be-om-brukar/`. Administratorar får varsel på e-post og godkjenner
   eller avslår under «Førespurnader om brukar» i admin (vel førespurnaden og handlinga «Godkjenn»).

Lagleiarar for kvar gruppe blir sette under «Grupper» i admin.

E-post blir skriven ut i terminalen så lenge `EMAIL_HOST` ikkje er sett (sjå «Leggje appen ut på nett»).

## Kom i gang

Du treng Python 3.12 eller nyare.

```bash
python3 -m venv .venv            # lag eit eige Python-miljø for prosjektet
source .venv/bin/activate        # aktiver det (Windows: .venv\Scripts\activate)
pip install -r requirements.txt  # installer Django og openpyxl
python manage.py migrate         # lag tabellane i databasen
python manage.py createsuperuser # lag ein admin-brukar til deg sjølv
python manage.py runserver       # start appen
```

Opne så:
- http://127.0.0.1:8000/ for å sjå vekeplanen
- http://127.0.0.1:8000/admin/ for å leggje inn og endre sesongar, grupper og treningstider

For å teste på mobilen på same nettverk: `python manage.py runserver 0.0.0.0:8000`,
set `DJANGO_ALLOWED_HOSTS` til IP-adressa til PC-en din, og opne `http://<ip-adresse>:8000/`.

## Importere frå Excel

```bash
python manage.py import_timeplan Treningstider_26-27.xlsx
```

Kvar fane blir ein sesong. Ei fane med «utkast» i namnet blir eit utkast.
Samanslåtte celler avgjer kor lenge ei tid varer og kor mange delar av salen ho
brukar. Tekst med «?» eller «Forslag» blir merkt som *ikkje avklart*. Legg til
`--replace` for å slette tidene i sesongen før du importerer på nytt.

Etter importen bør du sjå over tidene. Merknader som «etter nyttår» blir ikkje
tolka, så set **gjeld frå / gjeld til** for hand der det trengst.

## Førehandsvising på GitHub Pages

Ein versjon av vekeplanen som berre kan lesast, ligg på
https://zyrig.github.io/blixhalli/. GitHub byggjer han på nytt kvar gong noko
blir pusha til `main` (sjå `.github/workflows/pages.yml`).

Data kjem frå `data/timeplan.json`. Pages-sida og repoet er offentlege, så
fila skal ikkje innehalde namn på personar. Slik oppdaterer du ho etter at du
har endra tider lokalt:

```bash
python manage.py dumpdata bookings --indent 2 -o data/timeplan.json
```

For å hente dataa inn i ein tom lokal database: `python manage.py loaddata data/timeplan.json`.

## Kvar ting ligg

| Fil | Kva ho gjer |
|---|---|
| `bookings/models.py` | Data: Sesong, Gruppe, Treningstid, og regelen mot kollisjonar |
| `bookings/views.py` | Lagar vekeplan-sida |
| `bookings/templates/bookings/` | HTML og CSS for sidene |
| `bookings/admin.py` | Oppsett av administrasjonssida, med godkjenning av brukarar |
| `bookings/accounts.py`, `account_views.py`, `forms.py` | Brukarar: invitasjon, førespurnader, innlogging |
| `bookings/management/commands/import_timeplan.py` | Excel-importen |
| `bookings/tests.py` | Automatiske testar |
| `config/settings.py` | Innstillingar (tidssone, språk, database) |

Køyr testane med `python manage.py test`. Dei køyrer òg automatisk på GitHub ved
kvar push (sjå fana **Actions**).

## Endre datamodellen

Etter at du har endra `models.py`:

```bash
python manage.py makemigrations
python manage.py migrate
```

## Leggje appen ut på nett

Appen les desse miljøvariablane, slik at han kan køyre trygt på ein server:

| Variabel | Døme |
|---|---|
| `DJANGO_SECRET_KEY` | ein lang, tilfeldig og hemmeleg tekst |
| `DJANGO_DEBUG` | `0` |
| `DJANGO_ALLOWED_HOSTS` | `blixhalli.example.no` |
| `DJANGO_FROM_EMAIL` | `Treningstider Blixhalli <post@example.no>` |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | SMTP-tenaren som sender e-post |

## Lære meir

- Django-tutorialen: https://docs.djangoproject.com/en/5.2/intro/tutorial01/
- Django Girls (for nybyrjarar): https://tutorial.djangogirls.org/

## Moglege neste steg

- Leggje appen ut på nett (t.d. PythonAnywhere eller Fly.io)
- Avlysingar og enkeltbookingar (kamp, cup, utleige) oppå den faste vekeplanen
- Innlogging per lag, så kvar trenar kan endre sine eigne tider
- Utskriftsvenleg versjon / eksport til PDF
