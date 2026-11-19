from django.urls import path

from . import views

urlpatterns = [
    path("", views.schedule, name="schedule"),
    path("sesong/<int:season_id>/", views.schedule, name="season"),
]
