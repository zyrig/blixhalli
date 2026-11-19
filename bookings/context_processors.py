from .models import Facility
from .permissions import is_any_admin


def navigation(request):
    """Området og anlegga (for fanene øvst), og om brukaren er administrator (med tal på saker som ventar)."""
    workspace = getattr(request, "workspace", None)
    context = {"workspace": workspace,
               "facilities": Facility.objects.filter(workspace=workspace) if workspace else Facility.objects.none()}
    user = getattr(request, "user", None)
    if user is not None and is_any_admin(user):
        from .request_views import open_items_for
        requests, bookings = open_items_for(user, workspace)
        context["is_admin"] = True
        context["pending_request_count"] = len([r for r in requests if r.status == r.PENDING]) + len(bookings)
    return context
