from django.urls import path
from . import views

app_name = 'licensing'

urlpatterns = [
    path('dashboard/', views.licens_dashboard, name='licens_dashboard'),
    path('learners/', views.licens_learners, name='licens_learners'),
    path('license/analytics/', views.licens_analytics, name='licens_analytics'),
    path('participant/dashboard/', views.participant_dashboard, name='participant_dashboard'),
    path('invitation/send/', views.send_invitation, name='send_invitation'),
    path('invitation/cancel/<int:invitation_id>/', views.cancel_invitation, name='cancel_invitation'),
    path('invitation/resend/<int:invitation_id>/', views.resend_invitation, name='resend_invitation'),
    path('invitation/accept/<str:uidb64>/<str:token>/', views.accept_invitation, name='accept_invitation'),
    path('invitation/delete/<int:invitation_id>/', views.delete_invitation, name='delete_invitation'),  # Baru
    path('course-participants-dashboard/', views.course_participants_dashboard, name='course_participants_dashboard'),
    path('course-detail/<int:course_id>/', views.course_detail, name='course_detail'),
    path('create/', views.license_create, name='license_create'),
    path('update/license/<int:pk>/', views.license_update, name='license_update'),
    path('manage/', views.subscription_management, name='subscription_management'),
]