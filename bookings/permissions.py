"""Kven kan gjere kva. Alle sider som endrar noko, skal bruke desse funksjonane.

Roller:
- Plattformadministrator (is_superuser): kan alt, i alle område.
- Administrator i ein organisasjon (Organization.admins): administrerer organisasjonen sine lag,
  og anlegga organisasjonen eig eller fordeler tid på. Eigaren (t.d. kommunen) kan overstyre alt på
  anlegga sine.
- Lagleiar (Group.leaders): søkjer om tider, avlyser og bookar for sine eigne lag.
- Alle andre kan berre sjå.
"""
from django.db.models import Q

from .models import Facility, Group, Organization, find_covering_allocation


def is_platform_admin(user):
    return user.is_authenticated and user.is_superuser


def admin_orgs(user):
    if not user.is_authenticated:
        return Organization.objects.none()
    if user.is_superuser:
        return Organization.objects.all()
    return user.admin_of.all()


def is_any_admin(user):
    return user.is_authenticated and (user.is_superuser or user.admin_of.exists())


def is_org_admin(user, organization):
    return user.is_authenticated and (user.is_superuser or organization.admins.filter(pk=user.pk).exists())


def admin_facilities(user):
    orgs = admin_orgs(user)
    return Facility.objects.filter(Q(owner__in=orgs) | Q(manager__in=orgs)).distinct()


def can_admin_facility(user, facility):
    return is_org_admin(user, facility.owner) or is_org_admin(user, facility.manager)


def managed_groups(user):
    """Lag brukaren kan søkje og booke for: eigne lag som lagleiar, og alle lag i organisasjonar
    brukaren er administrator for."""
    if not user.is_authenticated:
        return Group.objects.none()
    if user.is_superuser:
        return Group.objects.all()
    return Group.objects.filter(Q(leaders=user) | Q(organization__admins=user)).distinct()


def can_manage(user, group):
    return user.is_authenticated and managed_groups(user).filter(pk=group.pk).exists()


def can_manage_on_facility(user, group, facility):
    """Lagleiaren/organisasjonen sjølv, eller administrator for anlegget (som kan overstyre)."""
    return can_manage(user, group) or can_admin_facility(user, facility)


# ---------------------------------------------------------------------------
# Godkjenning
# ---------------------------------------------------------------------------

def approver_orgs(facility, organization, weekday, start_time, end_time, first_section, last_section,
                  date_from, date_to):
    """Organisasjonane som kan godkjenne at `organization` får denne tida på anlegget.

    - Fordelaren og eigaren av anlegget kan alltid godkjenne.
    - Ligg tida inne i ei blokk organisasjonen har fått tildelt, kan òg organisasjonen sjølv godkjenne
      (t.d. Vik IL fordeler si eiga blokk i hallen til laga sine).
    """
    orgs = [facility.manager, facility.owner]
    if organization not in orgs and find_covering_allocation(organization, facility, weekday, start_time, end_time,
                                                             first_section, last_section, date_from, date_to):
        orgs.insert(0, organization)
    unique = []
    for o in orgs:
        if o not in unique:
            unique.append(o)
    return unique


def self_approved(facility, organization, weekday, start_time, end_time, first_section, last_section,
                  date_from, date_to):
    """Kan organisasjonen ta denne tida utan at nokon andre godkjenner (gjeld enkelttider)?"""
    return organization in approver_orgs(facility, organization, weekday, start_time, end_time, first_section,
                                         last_section, date_from, date_to)


def request_approver_orgs(r, proposed=False):
    d = r.proposal() if proposed and r.proposed_weekday is not None else r.wanted()
    return approver_orgs(r.facility, r.group.organization, d["weekday"], d["start_time"], d["end_time"],
                         d["first_section"], d["last_section"], d["valid_from"], d["valid_to"])


def booking_approver_orgs(b):
    return approver_orgs(b.facility, b.group.organization, b.date.weekday(), b.start_time, b.end_time,
                         b.first_section, b.last_section, b.date, b.date)


def can_approve_request(user, r):
    return user.is_authenticated and (user.is_superuser or any(is_org_admin(user, o) for o in request_approver_orgs(r)))


def can_approve_booking(user, b):
    return user.is_authenticated and (user.is_superuser or any(is_org_admin(user, o) for o in booking_approver_orgs(b)))
