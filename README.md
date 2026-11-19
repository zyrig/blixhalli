# Treningstider

Ein nettapp for å setje opp og vise treningstidene i Blixhalli, og seinare på fotballbanane ute.
Han fungerer i nettlesaren på både PC og mobil.

- **Fleire anlegg** med faner øvst: Blixhalli, Kunstgras 11'ar, Kunstgras 7'ar og Grasbane (sjå `data/anlegg.json`).
  Kvart anlegg har eiga inndeling og eigne reglar for kva som kan bookast, t.d. 1/4 eller 1/2 bane.
- **Søknad om fast tid:** lagleiaren vel anlegg, lag, vekedag, klokkeslett, kor stor del, og start- og sluttdato.
  Administrator godkjenner, avslår eller føreslår ei anna tid på `/soknader/`, og laget kan godta forslaget med eitt trykk.

- **Vekevising** (framsida) for ei bestemt veke: faste tider, avlysingar og enkelttider.
- **Avlysingar:** ei fast tid kan avlysast ein dato, og plassen blir ledig for andre.
- **Enkelttider** (ekstratrening, kamp) blir godkjende automatisk når plassen er ledig.
- **Sesongplan** (`/sesong/`) (t.d. 2026/2027), lagt opp som rutenett slik som i reknearket.
- **Delar:** Blixhalli er delt i tre (1/3, 2/3, 3/3). Ei treningstid brukar éin eller fleire delar ved sida av kvarandre.
- **Kollisjonskontroll:** appen stoppar to grupper frå å få same del av salen samstundes.
- **Utkast:** ein sesong kan vere eit utkast som berre dei som er logga inn ser.
- **Tider som ikkje er avklarte** (forslag, "?") blir viste med stipla kant.
- **Mobil:** éin dag om gongen, med knappar for å byte dag. **PC:** heile veka.
- **Redigering:** gjennom administrasjonssida (`/admin/`) etter innlogging.
- **Import** av det gamle Excel-arket.

Laga med [Django](https://www.djangoproject.com/) (Python). Data blir lagra i
SQLite, ein database som ligg i éi fil og ikkje treng noko oppsett.

## Anlegg og kva som kan bookast

Anlegga i `data/anlegg.json` blir oppretta automatisk (`python manage.py ensure_facilities`, køyrer ved kvar deploy).
Endringar gjer du i admin under **Anlegg**. Dei blir aldri overskrivne.

- **Delar:** namna på delane, skilde med komma, frå venstre mot høgre, t.d. `A,B,C,D`.
- **Kva som kan bookast:** éi linje per storleik. Døme for Kunstgras 11'ar:
  ```
  1/1: A-D
  1/2: A-B, C-D
  1/4: A, B, C, D
  ```
  Fjern linja `1/1: A-D` viss heile bana ikkje skal kunne bookast. Tomt felt = alle delar som ligg ved sida av
  kvarandre kan bookast (slik Blixhalli fungerer).

Sesongar er valfrie. Ei fast tid har eit anlegg og ein periode (gjeld frå/til). Sesongar blir berre brukte for
importerte sesongplanar frå Excel.

## Brukarar og roller

- **Alle** kan sjå kva lag som har kva tid, utan å logge inn.
- **Trenarar/lagleiarar** loggar inn med e-post og passord på `/logg-inn/`. Dei kan berre administrere
  tidene til sine eigne lag: avlyse ein dato, angre avlysinga, og booke eller slette enkelttider.
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
- http://127.0.0.1:8000/ for å sjå vekeplanen (du blir sendt vidare til det første anlegget)
- http://127.0.0.1:8000/admin/ for å leggje inn og endre sesongar, grupper og treningstider

For å teste på mobilen på same nettverk: `python manage.py runserver 0.0.0.0:8000`,
set `DJANGO_ALLOWED_HOSTS` til IP-adressa til PC-en din, og opne `http://<ip-adresse>:8000/`.

## Importere frå Excel

```bash
python manage.py import_timeplan Treningstider_26-27.xlsx --anlegg blixhalli
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
| `bookings/models.py` | Data: Sesong, Gruppe, Treningstid, Avlysing, Enkelttid, og reglane mot kollisjonar |
| `bookings/permissions.py` | Kven kan administrere kva lag |
| `bookings/leader_views.py` | Avlysing og enkelttider for lagleiarar |
| `bookings/views.py` | Lagar vekevisinga og sesongplanen |
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

## Leggje appen ut på nett (Render + Supabase)

Appen køyrer på [Render](https://render.com) og lagrar data i [Supabase](https://supabase.com)
(PostgreSQL). Begge kan liggje i Frankfurt, så data blir verande i EU.
Oppskrifta for Render ligg i `render.yaml`, og `build.sh` køyrer ved kvar ny versjon.

**1. Database i Supabase**
1. Lag eit nytt prosjekt i Supabase. Vel regionen **Central EU (Frankfurt)**, og noter databasepassordet.
2. Trykk **Connect** øvst i prosjektet og vel **Session pooler**. Kopier adressa, som ser slik ut:
   `postgresql://postgres.<prosjekt>:[YOUR-PASSWORD]@aws-0-eu-central-1.pooler.supabase.com:5432/postgres`
3. Byt ut `[YOUR-PASSWORD]` med databasepassordet.

Bruk «Session pooler» og ikkje «Direct connection». Render brukar berre IPv4, og den direkte
tilkoplinga til Supabase er berre IPv6.

**2. Appen i Render**
1. Logg inn på Render med GitHub-kontoen din.
2. Vel **New → Blueprint**, og vel repoet `blixhalli`.
3. Fyll inn verdiane Render spør om:

| Variabel | Kva du skriv |
|---|---|
| `DATABASE_URL` | adressa frå Supabase (steg 1) |
| `DJANGO_ADMIN_EMAIL` | e-postadressa di. Du blir første administrator. |
| `DJANGO_ADMIN_PASSWORD` | eit mellombels passord. Endre det etter første innlogging. |
| `DJANGO_FROM_EMAIL`, `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | e-postoppsett (sjå under). Kan stå tomme i starten. |

4. Trykk **Deploy**. Første gong blir tabellane laga, tidene frå `data/timeplan.json`
   lasta inn og administratoren oppretta. Appen får ei adresse som `https://blixhalli.onrender.com`.

Kvar gong noko blir pusha til `main`, legg Render ut den nye versjonen automatisk.

**E-post** (invitasjonar, «Gløymt passord», varsel). Utan dette blir e-post berre skriven til
loggen i Render. Det enklaste er Gmail med eit *app-passord* (krev totrinnsinnlogging på Google-kontoen):
`EMAIL_HOST=smtp.gmail.com`, `EMAIL_HOST_USER=<gmail-adressa>`, `EMAIL_HOST_PASSWORD=<app-passordet>`,
`DJANGO_FROM_EMAIL=Treningstider Blixhalli <gmail-adressa>`. Seinare kan ei teneste som Brevo eller
Resend og ei eiga avsendaradresse gi betre levering.

**Godt å vite**
- **Gratisvarianten av Render** «søv» etter 15 minutt utan besøk, og første besøk etterpå tek om lag
  eitt minutt. Byt `plan: free` til `plan: starter` i `render.yaml` (om lag 7 dollar i månaden)
  for ein app som alltid er vaken.
- **Gratisprosjekt i Supabase** kan bli pausa etter ein periode utan bruk. Sjå vilkåra hos Supabase.
- **Eige domene**, t.d. `treningstider.idrettslaget.no`: legg det til under *Settings → Custom Domains*
  i Render, og legg domenet til i `DJANGO_ALLOWED_HOSTS`.

**Miljøvariablar**

| Variabel | Døme |
|---|---|
| `DATABASE_URL` | `postgresql://…` (tom = lokal SQLite-fil) |
| `DJANGO_SECRET_KEY` | ein lang, tilfeldig og hemmeleg tekst (Render lagar han) |
| `DJANGO_DEBUG` | `0` i drift |
| `DJANGO_ALLOWED_HOSTS` | `treningstider.idrettslaget.no` (Render-adressa blir lagd til automatisk) |
| `DJANGO_ADMIN_EMAIL`, `DJANGO_ADMIN_PASSWORD` | første administrator |
| `DJANGO_FROM_EMAIL` | `Treningstider Blixhalli <post@example.no>` |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | SMTP-tenaren som sender e-post |

## Lære meir

- Django-tutorialen: https://docs.djangoproject.com/en/5.2/intro/tutorial01/
- Django Girls (for nybyrjarar): https://tutorial.djangogirls.org/

## Moglege neste steg

- Avlysingar og enkeltbookingar (kamp, cup, utleige) oppå den faste vekeplanen
- Innlogging per lag, så kvar trenar kan endre sine eigne tider
- Utskriftsvenleg versjon / eksport til PDF
