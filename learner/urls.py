# learner/urls.py
from django.urls import path
from . import views

app_name = 'learner'

urlpatterns = [
    path('learner/<str:username>/', views.learner_detail, name='learner_detail'),
    path('<str:username>/<int:id>/<str:slug>/', views.my_course, name='course_learn'),
    path('toggle-reaction/<int:comment_id>/<str:reaction_type>/', views.toggle_reaction, name='toggle_reaction'),
    path('<str:username>/<int:id>/<str:slug>/<str:content_type>/<int:content_id>/', views.load_content, name='load_content'),
    path('start-assessment/<int:assessment_id>/courses', views.start_assessment_courses, name='start_assessment'),
    path('submit-assessment/<int:assessment_id>/new', views.submit_assessment_new, name='submit_assessment_new'),
    path('submit-answer/', views.submit_answer, name='submit_answer'),
    path('add-comment/', views.add_comment, name='add_comment'),
    path('<str:username>/<str:slug>/progress/', views.get_progress, name='get_progress'),
    path('submit-answer-askora/<int:ask_ora_id>/new', views.submit_answer_askora_new, name='submit_answer_askora_new'),
    path('submit-peer-review/<int:submission_id>/ora', views.submit_peer_review_new, name='submit_peer_review_new'),
    path('analytics/users/', views.user_analytics_view, name='user_analytics'),
    path('lti/launch/<int:assessment_id>/', views.lti_consume_course, name='lti_consume_course'),
    path('lti/grade-callback/', views.lti_grade_callback, name='lti_grade_callback'),
    path('learner/<str:username>/<int:course_id>/score-summary/', views.score_summary_view, name='score_summary'),
    path('course/<int:course_id>/scores/detail/', views.score_summary_view_detail, name='score_summary_detail'),
    path('mark-progress/', views.mark_progress, name='mark_progress'),
    path('video/<int:video_id>/save-result/<int:assessment_id>/',views.save_invideo_quiz,name='save_invideo_quiz'),
    path("my-activity/", views.my_activity, name="my_activity"),
    path('invite-learner/<int:course_id>/', views.invite_learner, name='invite_learner')




  
]
  
