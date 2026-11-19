"""Finn kva område (t.d. «Vik») ein førespurnad gjeld, ut frå adressa.

- Eige domene: Workspace.domain, t.d. treningstider.vikil.no
- Underadresse: vik.<BASE_DOMAIN>, t.d. vik.treningstider.no (set BASE_DOMAIN=treningstider.no)
- Elles: DEFAULT_WORKSPACE (kortnamn), eller det første området.
"""
import os

from .models import Workspace


def resolve_workspace(host):
    host = host.split(":")[0].lower()
    workspace = Workspace.objects.filter(domain__iexact=host).first() if host else None
    base = os.environ.get("BASE_DOMAIN", "").lower().strip(".")
    if workspace is None and base and host.endswith("." + base):
        workspace = Workspace.objects.filter(slug=host[: -len(base) - 1].split(".")[-1]).first()
    if workspace is None and os.environ.get("DEFAULT_WORKSPACE"):
        workspace = Workspace.objects.filter(slug=os.environ["DEFAULT_WORKSPACE"]).first()
    return workspace or Workspace.objects.first()


class WorkspaceMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.workspace = resolve_workspace(request.get_host())
        return self.get_response(request)
