"""Eksport av treningsplanen til Excel, i same rutenett-oppsett som reknearket som har vore brukt:
vekedagar med éin kolonne per del av anlegget, halvtimar nedover, og samanslåtte celler for kvar tid.
"""
import datetime
import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .models import WEEKDAYS, Allocation, Facility, TrainingSlot, overlapping

FILLS = {"fotball": "D7ECD9", "handball": "FDE2C8", "friidrett": "DBE6FB", "trim": "F6D8E8",
         "volleyball": "FFF1B8", "badminton": "E3DCF7", "anna": "E6E8EB", "blokk": "FFFFFF"}
THIN = Side(style="thin", color="B0B7C3")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def _minutes(t):
    return t.hour * 60 + t.minute


def _sheet_title(name, used):
    title = "".join(c for c in name if c not in r':\/?*[]').strip("'")[:31] or "Anlegg"
    base, n = title, 2
    while title in used:
        title = f"{base[:28]} {n}"
        n += 1
    used.add(title)
    return title


def week_entries(facility, monday):
    """Faste tider (og tildelte blokker som ikkje er fordelte) for kvar dag i veka."""
    days = {}
    slots = list(TrainingSlot.objects.filter(facility=facility).select_related("group__organization", "season",
                                                                                "facility"))
    allocations = list(Allocation.objects.filter(facility=facility).select_related("organization", "facility"))
    for i in range(7):
        date = monday + datetime.timedelta(days=i)
        day = [s for s in slots if s.is_active_on(date) and (s.season is None or s.season.published)]
        for a in allocations:
            if a.is_active_on(date) and not any(
                    s.start_time < a.end_time and s.end_time > a.start_time
                    and s.first_section <= a.last_section and s.last_section >= a.first_section for s in day):
                day.append(a)
        days[i] = day
    return days


def build_workbook(workspace, date):
    monday = date - datetime.timedelta(days=date.weekday())
    sunday = monday + datetime.timedelta(days=6)
    week = monday.isocalendar().week
    wb = Workbook()
    wb.remove(wb.active)
    used = set()
    rows = []

    for facility in Facility.objects.filter(workspace=workspace):
        ws = wb.create_sheet(_sheet_title(facility.name, used))
        n = facility.section_count
        days = week_entries(facility, monday)
        everything = [e for d in days.values() for e in d]
        first = min([_minutes(e.start_time) for e in everything] + [9 * 60]) // 60 * 60
        last = -(-max([_minutes(e.end_time) for e in everything] + [22 * 60]) // 60) * 60

        ws["A1"] = f"Treningstider {facility.name} – veke {week} ({monday:%d.%m.}–{sunday:%d.%m.%Y})"
        ws["A1"].font = Font(bold=True, size=14)
        ws["A2"] = f"Fast plan. Tildelt av {facility.manager}. Eksportert {datetime.date.today():%d.%m.%Y}."
        ws["A2"].font = Font(italic=True, color="5D6673")
        ws["A3"], ws["A4"] = "DAG/TID", "DEL"
        for cell in (ws["A3"], ws["A4"]):
            cell.font = Font(bold=True)
            cell.border = BOX
        for i, (_, name) in enumerate(WEEKDAYS):
            col = 2 + i * n
            ws.cell(3, col, f"{name.upper()} {monday + datetime.timedelta(days=i):%d.%m.}")
            ws.cell(3, col).font = Font(bold=True)
            ws.cell(3, col).alignment = Alignment(horizontal="center")
            if n > 1:
                ws.merge_cells(start_row=3, start_column=col, end_row=3, end_column=col + n - 1)
            for s, label in facility.sections:
                c = ws.cell(4, col + s - 1, label)
                c.alignment = Alignment(horizontal="center")
                c.border = BOX
        times = list(range(first, last, 30))
        for r, m in enumerate(times):
            c = ws.cell(5 + r, 1, f"{m // 60:02d}.{m % 60:02d}-{(m + 30) // 60:02d}.{(m + 30) % 60:02d}")
            c.border = BOX
            for col in range(2, 2 + 7 * n):
                ws.cell(5 + r, col).border = BOX

        for i, entries in days.items():
            for e in entries:
                is_block = isinstance(e, Allocation)
                r1 = 5 + (_minutes(e.start_time) - first) // 30
                r2 = 5 + -(-(_minutes(e.end_time) - first) // 30) - 1
                c1 = 2 + i * n + e.first_section - 1
                c2 = 2 + i * n + e.last_section - 1
                org = e.organization if is_block else e.group.organization
                if is_block:
                    title = f"{org} (blokk)"
                elif org == facility.manager or org.name.lower() in e.group.name.lower():
                    title = e.group.name
                else:
                    title = f"{e.group.name} ({org})"
                cell = ws.cell(r1, c1, title)
                cell.alignment = Alignment(wrap_text=True, vertical="top")
                cell.fill = PatternFill("solid", fgColor=FILLS["blokk" if is_block else e.group.category])
                if is_block:
                    cell.font = Font(italic=True)
                if r2 > r1 or c2 > c1:
                    ws.merge_cells(start_row=r1, start_column=c1, end_row=r2, end_column=c2)
                if not is_block:
                    rows.append([facility.name, WEEKDAYS[i][1], e.start_time.strftime("%H:%M"),
                                 e.end_time.strftime("%H:%M"), e.sections_label, e.group.name,
                                 e.group.organization.name,
                                 *(d.strftime("%d.%m.%Y") if d else "" for d in e.effective_range())])

        ws.column_dimensions["A"].width = 12
        for col in range(2, 2 + 7 * n):
            ws.column_dimensions[get_column_letter(col)].width = max(8, 42 // n)
        ws.freeze_panes = "B5"
        ws.page_setup.orientation = "landscape"
        ws.page_setup.fitToWidth = 1

    ls = wb.create_sheet("Liste", 0)
    ls.append([f"Treningstider {workspace.name} – veke {week} ({monday:%d.%m.}–{sunday:%d.%m.%Y})"])
    ls["A1"].font = Font(bold=True, size=14)
    ls.append([])
    header = ["Anlegg", "Dag", "Frå", "Til", "Del", "Lag", "Organisasjon", "Gjeld frå", "Gjeld til"]
    ls.append(header)
    for c in ls[3]:
        c.font = Font(bold=True)
    for row in rows:
        ls.append(row)
    for i, w in enumerate([18, 10, 7, 7, 14, 40, 20, 11, 11], start=1):
        ls.column_dimensions[get_column_letter(i)].width = w
    ls.freeze_panes = "A4"

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue(), f"treningstider-{workspace.slug}-veke-{week}.xlsx"
