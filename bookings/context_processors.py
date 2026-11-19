from .models import Facility, TrainingRequest


def navigation(request):
    """Anlegga (for fanene øvst) og talet på søknader som ventar (for administratorar)."""
    context = {"facilities": Facility.objects.all()}
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and user.is_staff:
        context["pending_request_count"] = TrainingRequest.objects.filter(status=TrainingRequest.PENDING).count()
    return context
