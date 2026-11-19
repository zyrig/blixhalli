from django.urls import path

from . import views

urlpatterns = [
    path("", views.week_schedule, name="week"),
    path("new/", views.new_booking, name="new_booking"),
]
