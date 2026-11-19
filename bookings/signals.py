"""Når nokon blir administrator i ein organisasjon, får dei tilgang til admin-sida (/admin/)
med rettar til å administrere treningstider. Kva dei faktisk ser, blir avgrensa i admin.py."""
from django.contrib.auth.models import Group as PermissionGroup
from django.contrib.auth.models import Permission
from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from .models import Organization

ADMIN_GROUP = "Organisasjonsadministrator"
FULL = ["allocation", "booking", "cancellation", "season", "trainingslot", "trainingrequest", "group"]
CHANGE_ONLY = ["facility", "accountrequest"]


def admin_permission_group():
    group, _ = PermissionGroup.objects.get_or_create(name=ADMIN_GROUP)
    if not group.permissions.exists():
        codenames = [f"{a}_{m}" for m in FULL for a in ("view", "add", "change", "delete")]
        codenames += [f"{a}_{m}" for m in CHANGE_ONLY for a in ("view", "change")]
        codenames += ["view_organization"]
        group.permissions.set(Permission.objects.filter(content_type__app_label="bookings", codename__in=codenames))
    return group


@receiver(m2m_changed, sender=Organization.admins.through)
def give_admin_access(sender, instance, action, pk_set, reverse, **kwargs):
    if action != "post_add" or not pk_set:
        return
    from django.contrib.auth import get_user_model
    User = get_user_model()
    users = User.objects.filter(pk__in=pk_set) if not reverse else User.objects.filter(pk=instance.pk)
    group = admin_permission_group()
    for user in users:
        if not user.is_staff:
            user.is_staff = True
            user.save(update_fields=["is_staff"])
        user.groups.add(group)
