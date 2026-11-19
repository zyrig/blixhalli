"""Kven kan gjere kva. Alle sider som endrar tider skal bruke desse funksjonane.

- Administratorar (is_staff) kan administrere alle lag.
- Lagleiarar kan berre administrere laga dei er lagleiar for.
- Alle andre kan berre sjå.
"""
from .models import Group


def managed_groups(user):
    if not user.is_authenticated:
        return Group.objects.none()
    if user.is_staff:
        return Group.objects.all()
    return user.led_groups.all()


def can_manage(user, group):
    return user.is_authenticated and (user.is_staff or group.leaders.filter(pk=user.pk).exists())
