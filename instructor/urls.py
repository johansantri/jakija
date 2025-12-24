# instructor/urls.py
from django.urls import path
from . import views

app_name = 'instructor'

urlpatterns = [
    
    path('learner-detail-report/', views.instructor_learner_detail_report, name='instructor_learner_detail_report'),
   
     # URL untuk Instructor
    path('instructor/course/<int:course_id>/submit-curation/', views.instructor_submit_curation, name='instructor_submit_curation'),
    

    # URL untuk Partner
    path('partner/course/<int:course_id>/review-curation/', views.partner_review_curation, name='partner_review_curation'),
    

    # URL untuk Superuser
    path('superuser/course/<int:course_id>/publish/', views.superuser_publish_course, name='superuser_publish_course'),
    path('studios/<str:id>/', views.studios, name='studios'),

    path('instructor/generate-certificates/', views.generate_instructor_certificate_pdf, name='generate_instructor_certificates'),
    path('certificate/verify/<uuid:cert_id>/', views.verify_instructor_certificate, name='verify_instructor_certificate'),


]