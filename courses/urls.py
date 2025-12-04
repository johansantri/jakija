from django.urls import path,include
from rest_framework.routers import DefaultRouter
from . import views
from .views import CourseAutocomplete,InstructorAutocomplete,PartnerAutocomplete,SectionViewSet,MaterialViewSet,AssessmentViewSet
app_name = 'courses'

router = DefaultRouter()
router.register(r'sections', SectionViewSet, basename='section')
router.register(r'materials', MaterialViewSet, basename='material')
router.register(r'assessments', AssessmentViewSet, basename='assessment')
urlpatterns = [
    path('courses/', views.courseView, name='course_view'),
    path('course/tim/', views.courseViewTim, name='course_view_tim'),
    path('course/<int:course_id>/enroll/', views.enroll_course, name='enroll_course'),
    path('upload-image/', views.ckeditor_upload_image, name='ckeditor_upload_image'),
    path('ckeditor/delete-image/', views.ckeditor_delete_image, name='ckeditor_delete_image'),
    path('instructor-add/', views.become_instructor, name='instructor_add'),
    path('partner-autocomplete/', PartnerAutocomplete.as_view(), name='partner-autocomplete'),
    path('partner-autocomplete/', views.partner_autocomplete, name='partner_autocomplete'),
    path('instructor/', views.instructor_view, name='instructor_view'),
    path('instructor/<int:instructor_id>/check/', views.instructor_check, name='instructor_check'),
    path('instructor/<int:instructor_id>/delete/', views.delete_instructor, name='delete_instructor'),
    path('instructor/<int:id>/', views.instructor_detail, name='instructor_detail'),
    path('instructor-profile/<slug:username>/', views.instructor_profile, name='instructor_profile'),
    path("studio/<str:id>", views.studio, name= "studio"),
    path('reorder-section/', views.reorder_section, name='reorder_section'),
    path("partner/", views.partnerView, name= "partner_view"),
    path('partner/<int:partner_id>/', views.partner_detail, name='partner_detail'),
    path('partner/<int:partner_id>/update/', views.update_partner, name='update_partner'),
    path('org-partner/<slug:slug>/',views.org_partner, name='org_partner'),
   
    path("course-add/", views.course_create_view, name= "course_create_view"),
    path("category/add/", views.category_create_view, name= "category_create_view"),
    path("partner-add/", views.partner_create_view, name= "partner_create_view"),
    path('user-autocomplete/', views.UserAutocomplete.as_view(), name='user-autocomplete'),
    path('universiti-autocomplete/', views.UniversitiAutocomplete.as_view(), name='universiti-autocomplete'),
    path('create-section/<int:idcourse>/', views.create_section, name='create_section'),
    path('add-matrial/<int:idcourse>/<int:idsection>/',views.add_matrial,name="add-matrial"),
    path('create-assessment/<int:idcourse>/<int:idsection>/', views.create_assessment, name='create-assessment'),
    path('edit-assessment/<int:idcourse>/<int:idsection>/<int:idassessment>/', views.edit_assessment, name='edit_assessment'),
    path('delete-assessment/<int:idcourse>/<int:idsection>/<int:idassessment>/', views.delete_assessment, name='delete_assessment'),
    path('course-list-enroll/<int:id>/', views.course_list_enroll, name='course_list_enroll'),



    
    
    path('questions/create/<int:idcourse>/<int:idsection>/<int:idassessment>/', views.create_question_view, name='create_question'),
    path('edit-matrial/<int:idcourse>/<int:idmaterial>', views.edit_matrial, name='edit_matrial'),
    path('questions/edit/<int:idcourse>/<int:idquestion>/<int:idsection>/<int:idassessment>', views.edit_question, name='edit_question'),
    path('questions/delete/<int:idcourse>/<int:idquestion>/<int:idsection>/<int:idassessment>', views.delete_question, name='delete_question'),
    path(
        'questions/view/<int:idcourse>/<int:idsection>/<int:idassessment>/',
        views.question_view,
        name='view-question',
    ),
    path('delete-matrial/<int:pk>', views.delete_matrial, name='delete_matrial'),
    path('delete-section/<int:pk>/', views.delete_section, name='delete_section'),
    path('update-section/<int:pk>/', views.update_section, name='update_section'),
    path('course-profile/<int:id>/', views.course_profile, name='course_profile'),
    path('course-grade/<int:id>/', views.course_grade, name='course_grade'),
    path("update-grade-range/<int:id>/", views.update_grade_range, name="update_grade_range"),
    path('course-team/<int:course_id>/', views.course_team, name='course_team'),
    path('course-instructor/<int:id>/', views.course_instructor, name='course_instructor'),
    path('instructor-autocomplete/', InstructorAutocomplete.as_view(), name='instructor-autocomplete'),
    
    path('team-member/remove/<int:member_id>/', views.remove_team_member, name='remove_team_member'),
    path('draft-lms/<int:id>/', views.draft_lms, name='draft-lms'),
    path('course-detail/<int:id>/<slug:slug>/', views.course_lms_detail, name='course_lms_detail'),

    path('add-price/<int:id>/', views.add_course_price, name='add_course_price'),
    path('course/<int:id>/<slug:slug>/rating/', views.submit_rating, name='submit_rating'),
    path('courses/re-runs/<int:id>/', views.course_reruns, name='course_reruns'),
    path('course-learn/<str:username>/<slug:slug>/', views.course_learn, name='course_learn'),
    path('self_course/<str:username>/<int:id>/<slug:slug>/', views.self_course, name='self_course'),
    path('submit_assessment/<int:assessment_id>/', views.submit_assessment, name='submit_assessment'),
    path('start-assessment/<int:assessment_id>/', views.start_assessment, name='start_assessment'),
    path('enroll/<int:course_id>/', views.enroll_course, name='enroll'),  # Define 'enroll' URL pattern
    path('add-comment/<int:material_id>/', views.add_comment, name='add_comment'),
    path('add-comment-course/<int:course_id>/', views.add_comment_course, name='add_comment_course'),  # Add this line
    path('course/<int:idcourse>/section/<int:idsection>/assessment/<int:idassessment>/create/', views.create_askora, name='create_askora'),
    #add lti 1.1
    path('course/<int:idcourse>/section/<int:idsection>/lti/<int:idlti>/create/', views.create_lti, name='create_lti'),
    path('course/<int:idcourse>/section/<int:idsection>/lti/<int:idlti>/edit/<int:id_lti_tool>/', views.edit_lti, name='edit_lti'),
    path('course/<int:idcourse>/section/<int:idsection>/lti/<int:idlti>/delete/<int:id_lti_tool>/', views.delete_lti, name='delete_lti'),
    path('course/<int:idcourse>/section/<int:idsection>/lti/<int:idlti>/launch/<int:id_lti_tool>/', views.launch_lti, name='launch_lti'),
    
    path('edit-askora/<int:idcourse>/<int:idaskora>/<int:idsection>/<int:idassessment>/', views.edit_askora, name='edit_askora'),
    path('delete-askora/<int:idcourse>/<int:idaskora>/<int:idsection>/<int:idassessment>/', views.delete_askora, name='delete_askora'),
    #sertifikat
    path('certificate/<int:course_id>/', views.generate_certificate, name='generate_certificate'),
    path('verify/<uuid:certificate_id>/', views.verify_certificate, name='verify_certificate'),
    path('verify-micro/<uuid:certificate_id>/', views.verify_certificate_micro, name='verify_certificate_micro'),
    path('submit-answer/<int:askora_id>/', views.submit_answer, name='submit_answer'),
    path('submit-peer-review/<int:submission_id>/', views.submit_peer_review, name='submit_peer_review'),

    path('microcredentials/', views.listmic, name='microcredential-list'),
    path('microcredentials/create/', views.addmic, name='microcredential-create'),
    path('course-autocomplete/', CourseAutocomplete.as_view(), name='course-autocomplete'),

    path('microcredentials/<int:pk>/edit/', views.editmic, name='microcredential-update'),
    path('microcredentials/<int:pk>/delete/', views.deletemic, name='microcredential-delete'),
    path('microcredentials/<int:pk>/', views.detailmic, name='microcredential-detail'),  # Detail view
    path('microcredential/<slug:slug>/', views.microcredential_detail, name='microcredential_detail'),
    path('microcredential/<int:id>/certificate/', views.generate_microcredential_certificate, name='generate_microcredential_certificate'),
    path('microcredential/<slug:slug>/enroll/', views.enroll_microcredential, name='enroll_microcredential'),
    #detail micro lms
    path('microcredential/<int:id>/<slug:slug>/detail/', views.micro_detail, name='micro_detail'),
    path('microcredential/<int:microcredential_id>/add-review/', views.add_microcredential_review, name='add_microcredential_review'),
    path('microcredential/<int:microcredential_id>/<slug:slug>/add_comment/', views.add_comment_microcredential, name='add_comment_microcredential'),
    path('microcredential/<int:microcredential_id>/report/', views.microcredential_report_view, name='microcredential_report'),
    path('microcredential/report/pdf/<int:microcredential_id>/', views.microcredential_report_pdf_view, name='microcredential_report_pdf'),

    path('comment/<int:comment_id>/reply/', views.reply_comment, name='reply_comment'),
    path('sosial/', views.create_and_list_sos_posts, name='create_and_list_sos_posts'),
    path('sosial/create/', views.create_post, name='create_post'),
    path('sosial/like/<int:post_id>/', views.like_post, name='like_post'),
   
    path('sosial/reply/<int:post_id>/', views.reply_post, name='reply_post'),
    path('sosial/reply-form/<int:post_id>/', views.reply_form, name='reply_form'),  # Ditambahkan
    path('sosial/hashtag/<str:hashtag>/', views.posts_by_hashtag, name='posts_by_hashtag'),  # Rute baru
    path('sosial/load-more/', views.load_more_posts, name='load_more_posts'),
    path('sosial/search/', views.search_posts, name='search_posts'),  # Rute baru
   #menuju home category
    path('category/<slug:slug>/', views.category_course_list, name='category_list'),

 
    
]

urlpatterns += router.urls  # tambahkan router