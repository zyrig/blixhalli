from django.contrib.auth import views as auth_views
from django.urls import path

from . import account_views, leader_views, request_views, views
from .forms import EmailLoginForm, ResetPasswordForm

urlpatterns = [
    path("", views.home, name="home"),
    path("eksport/", views.export_view, name="export"),
    # Lagleiarar og administratorar
    path("mine/", account_views.mine, name="mine"),
    path("avlys/<int:slot_id>/", leader_views.cancel_slot, name="cancel_slot"),
    path("avlysing/<int:pk>/angre/", leader_views.undo_cancellation, name="undo_cancellation"),
    path("enkelttid/<int:pk>/slett/", leader_views.delete_booking, name="delete_booking"),
    # Søknader om faste tider
    path("soknad/<int:pk>/trekk/", request_views.withdraw, name="withdraw_request"),
    path("soknad/<int:pk>/svar/", request_views.answer_proposal, name="answer_proposal"),
    path("soknader/", request_views.request_admin, name="request_admin"),
    path("soknader/<int:pk>/godkjenn/", request_views.approve, name="approve_request"),
    path("soknader/<int:pk>/avsla/", request_views.reject, name="reject_request"),
    path("soknader/<int:pk>/foresla/", request_views.propose, name="propose_request"),
    path("soknader/enkelttid/<int:pk>/", request_views.decide_booking, name="decide_booking"),
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
    # Visning per anlegg (for alle). Må stå sist, sidan adressa byrjar med namnet på anlegget.
    path("<slug:facility>/", views.week_view, name="week_current"),
    path("<slug:facility>/veke/<str:day>/", views.week_view, name="week"),
    path("<slug:facility>/sesong/", views.season_view, name="season_default"),
    path("<slug:facility>/sesong/<int:season_id>/", views.season_view, name="season"),
    path("<slug:facility>/enkelttid/ny/", leader_views.new_booking, name="new_booking"),
    path("<slug:facility>/sok/", request_views.new_request, name="new_request"),
]
