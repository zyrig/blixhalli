from django.contrib.auth import views as auth_views
from django.urls import path

from . import account_views, leader_views, views
from .forms import EmailLoginForm, ResetPasswordForm

urlpatterns = [
    # Visning (for alle)
    path("", views.week_view, name="schedule"),
    path("veke/<str:day>/", views.week_view, name="week"),
    path("sesong/", views.season_view, name="season_default"),
    path("sesong/<int:season_id>/", views.season_view, name="season"),
    # Lagleiarar og administratorar
    path("mine/", account_views.mine, name="mine"),
    path("avlys/<int:slot_id>/", leader_views.cancel_slot, name="cancel_slot"),
    path("avlysing/<int:pk>/angre/", leader_views.undo_cancellation, name="undo_cancellation"),
    path("enkelttid/ny/", leader_views.new_booking, name="new_booking"),
    path("enkelttid/<int:pk>/slett/", leader_views.delete_booking, name="delete_booking"),
    # Brukarar
    path("be-om-brukar/", account_views.request_account, name="request_account"),
    path("inviter/", account_views.invite, name="invite"),
    # Innlogging og passord (Django sine ferdige views, med våre malar)
    path("logg-inn/", auth_views.LoginView.as_view(authentication_form=EmailLoginForm), name="login"),
    path("logg-ut/", auth_views.LogoutView.as_view(), name="logout"),
    path("passord/gloymt/", auth_views.PasswordResetView.as_view(form_class=ResetPasswordForm), name="password_reset"),
    path("passord/sendt/", auth_views.PasswordResetDoneView.as_view(), name="password_reset_done"),
    path("passord/ny/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("passord/ferdig/", auth_views.PasswordResetCompleteView.as_view(), name="password_reset_complete"),
]
