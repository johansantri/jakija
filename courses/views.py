# Standard library
import os
import re
import csv
import time
import json
import uuid
import hmac
import html
import base64
import random
import string
import logging
import hashlib
import urllib
from io import BytesIO
from datetime import datetime, timedelta
from django.utils import timezone
from decimal import Decimal, ROUND_DOWN
from urllib.parse import quote, urlparse, parse_qs, urlencode
from django.template.loader import get_template
from .utils import generate_oauth_signature  # pastikan ada util ini
# Third-party packages
import pytz
import qrcode
import bleach
import requests
from PIL import Image
from jose import jwt
from decimal import Decimal, ROUND_HALF_UP
from jose import jwk as jose_jwk
from jose.utils import base64url_decode
from jwt import get_unverified_header, decode as jwt_decode, algorithms
from jwt.algorithms import RSAAlgorithm
from oauthlib.oauth1 import Client, Client as OAuth1Client
from oauthlib.common import to_unicode
from requests_oauthlib import OAuth1, OAuth1Session
from weasyprint import HTML
from django_ckeditor_5.widgets import CKEditor5Widget
from django.core.mail import EmailMessage
# Django core
from django import forms
from django.conf import settings
from django.urls import reverse
from django.db import DatabaseError, IntegrityError
from django.db.models import (
    Q, F, Sum, Count, Avg,
    OuterRef, Subquery, IntegerField, Prefetch
)
from django.db.models.functions import Round
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.middleware.csrf import get_token
from django.template.loader import render_to_string
from django.shortcuts import render, redirect, get_object_or_404
#from django.utils import timezone
from django.utils.timezone import now
from django.utils.text import slugify
from django.http import (
    JsonResponse, Http404, HttpResponse, HttpResponseForbidden,
    HttpResponseNotFound, HttpResponseBadRequest, HttpResponseRedirect,HttpResponseServerError
)
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import cache_page
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

# Internal imports - forms
from .forms import (
    CourseTeamForm, MicroCredentialCommentForm, MicroCredentialReviewForm, LTIExternalToolForm,
    CoursePriceForm, CourseRatingForm, SosPostForm, MicroCredentialForm, AskOraForm,
    CourseForm, CourseRerunForm, PartnerForm, PartnerFormUpdate, CourseInstructorForm,
    SectionForm, GradeRangeForm, ProfilForm, InstructorForm, InstructorAddCoruseForm,
    TeamMemberForm, MatrialForm, QuestionForm, ChoiceFormSet, AssessmentForm,CategoryForm
)

# Internal imports - utils
from .utils import user_has_passed_course, check_for_blacklisted_keywords, is_suspicious

# Internal imports - models
from .models import (
    LTIExternalTool1, LastAccessCourse, UserActivityLog, MicroClaim, CourseViewIP,
    CourseViewLog, UserMicroCredential, MicroCredentialComment, MicroCredentialReview,
    UserMicroProgress, SearchHistory, Certificate,  Course, CourseRating,
    Like, SosPost, Hashtag, UserProfile, MicroCredentialEnrollment, MicroCredential,
    AskOra, PeerReview, AssessmentScore, Submission, CourseStatus, AssessmentSession,
    CourseComment, Comment, Choice, Score, CoursePrice, AssessmentRead, QuestionAnswer,
    Enrollment, PricingType, Partner, CourseProgress, MaterialRead, GradeRange, Category,
    Section, Instructor, TeamMember, Material, Question, Assessment,LTIResult,CourseTeam,Quiz,QuizResult,
)

# Project-level apps
from authentication.models import CustomUser, Universiti
from blog.models import BlogPost
from licensing.models import License
from payments.models import Payment

from django.db.models import Count, Avg, Sum, Q, Value as V
from django.db.models.functions import Coalesce
from django.db.models import DecimalField
from dal import autocomplete
from rest_framework import viewsets,status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import NotFound
from .serializers import SectionSerializer,MaterialSerializer,AssessmentSerializer
from django.views.decorators.http import require_http_methods

@csrf_exempt
@require_POST
def ckeditor_upload_image(request):
    """
    View khusus untuk CKEditor 5 image upload
    CKEditor mengharapkan response:
    { "url": "https://domain.com/media/xxx.jpg" }
    """
    if not request.FILES.get('upload'):
        return JsonResponse({
            'error': {'message': 'No file uploaded.'}
        }, status=400)

    uploaded_file = request.FILES['upload']

    # Validasi tipe file
    allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp']
    if uploaded_file.content_type not in allowed_types:
        return JsonResponse({
            'error': {'message': 'File type not allowed.'}
        }, status=400)

    # Validasi ukuran maksimal 5MB (sesuaikan kalau mau)
    if uploaded_file.size > 5 * 1024 * 1024:
        return JsonResponse({
            'error': {'message': 'File too large (max 5MB).'}
        }, status=400)

    # Buat nama file unik
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    new_filename = f"ckeditor_{timezone.now().strftime('%Y%m%d')}_{uuid.uuid4().hex}{ext}"

    # Tentukan path penyimpanan
    upload_path = os.path.join('ckeditor', timezone.now().strftime('%Y/%m/%d'))
    full_path = os.path.join(upload_path, new_filename)

    # Simpan file
    file_url = settings.MEDIA_URL + full_path.replace('\\', '/')
    file_path = os.path.join(settings.MEDIA_ROOT, full_path.replace('\\', '/').lstrip('/'))

    # Pastikan folder ada
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    with open(file_path, 'wb+') as destination:
        for chunk in uploaded_file.chunks():
            destination.write(chunk)

    # Response yang diharapkan CKEditor 5
    return JsonResponse({
        'url': request.build_absolute_uri(file_url)
    })


class SectionViewSet(viewsets.ModelViewSet):
    queryset = Section.objects.all()
    serializer_class = SectionSerializer

    # ──────────────────────────────────────────────────────────────
    # LIST → hanya root sections (parent=None) + prefetch semua anak + material/assessment
    # ──────────────────────────────────────────────────────────────
    def get_queryset(self):
        course_id = self.request.query_params.get('course')
        if not course_id:
            return Section.objects.none()

        # Prefetch 2 level dalam + materials & assessments hanya di level Unit
        return Section.objects.filter(
            courses_id=course_id,
            parent__isnull=True
        ).order_by('order').prefetch_related(
            # Level 1: Subsection
            Prefetch(
                'children',
                queryset=Section.objects.order_by('order').prefetch_related(
                    # Level 2: Unit → ambil materials & assessments
                    Prefetch(
                        'children',
                        queryset=Section.objects.order_by('order').prefetch_related(
                            'materials',
                            'assessments'
                        )
                    )
                )
            )
        )

    # ──────────────────────────────────────────────────────────────
    # RETRIEVE, UPDATE, DELETE → tetap bisa akses semua level via PK
    # ──────────────────────────────────────────────────────────────
    def get_object(self):
        pk = self.kwargs.get('pk')
        obj = get_object_or_404(Section, pk=pk)
        self.check_object_permissions(self.request, obj)
        return obj

    # ──────────────────────────────────────────────────────────────
    # REORDER → terima struktur baru dari frontend
    # ──────────────────────────────────────────────────────────────
    @action(detail=False, methods=['post'])
    def reorder(self, request):
        data = request.data  # list of dicts: [{id, children: [...]}, ...]
        self._update_order_recursive(data, parent_id=None)
        return Response({"status": "ok"})

    def _update_order_recursive(self, items, parent_id):
        for index, item in enumerate(items):
            section_id = item['id']
            section = get_object_or_404(Section, pk=section_id)

            # Update parent & order dalam satu save() → lebih cepat
            Section.objects.filter(pk=section_id).update(
                parent_id=parent_id,
                order=index
            )

            # Rekursif ke children
            if item.get('children'):
                self._update_order_recursive(item['children'], parent_id=section_id)

    # ──────────────────────────────────────────────────────────────
    # DELETE → hapus + rapikan order sibling
    # ──────────────────────────────────────────────────────────────
    def destroy(self, request, *args, **kwargs):
        section = self.get_object()
        course = section.courses
        parent = section.parent

        section.delete()  # CASCADE hapus semua anak

        # Rapikan order sibling di level yang sama
        if parent:
            siblings = parent.children.all()
        else:
            siblings = Section.objects.filter(courses=course, parent__isnull=True)

        for index, sib in enumerate(siblings.order_by('order')):
            sib.order = index
            sib.save(update_fields=['order'])

        return Response({"status": "deleted"}, status=status.HTTP_204_NO_CONTENT)

class MaterialViewSet(viewsets.ModelViewSet):
    queryset = Material.objects.all()
    serializer_class = MaterialSerializer

class AssessmentViewSet(viewsets.ModelViewSet):
    queryset = Assessment.objects.all()
    serializer_class = AssessmentSerializer

def custom_ratelimit(view_func):
    def wrapper(request, *args, **kwargs):
        key = request.user.username if request.user.is_authenticated else request.META.get('REMOTE_ADDR', 'anonymous')
        cache_key = f'ratelimit_{key}'
        timestamp_key = f'{cache_key}_timestamp'
        limit = 500
        window = 3600  # 1 hour in seconds

        request_count = cache.get(cache_key, 0)
        first_request_time = cache.get(timestamp_key)

        if request_count >= limit:
            if first_request_time:
                time_passed = int(time.time()) - first_request_time
                time_remaining = window - time_passed
            else:
                time_remaining = window

            logger.warning(f"Rate limit exceeded for {cache_key}: {request_count} requests")

            if request.user.is_authenticated:
                user_info = f" ⚠️ You have exceeded the limit of {limit} requests per hour."
            else:
                user_info = f" ⚠️ Too many requests from your IP address. The limit is {limit} requests per hour."

            response_content = (
                f"{user_info}\n"
                f"You have made {request_count} requests.\n"
                f"Please try again in {time_remaining} seconds."
            )
            return HttpResponse(response_content, status=429)

        if request_count == 0:
            cache.set(cache_key, 1, window)
            cache.set(timestamp_key, int(time.time()), window)
        else:
            try:
                cache.incr(cache_key)
            except ValueError as e:
                logger.error(f"Cache increment failed for {cache_key}: {str(e)}")
                cache.set(cache_key, request_count + 1, window)

        return view_func(request, *args, **kwargs)
    return wrapper


@login_required
def microcredential_report_view(request, microcredential_id):
    user = request.user
    if not (user.is_superuser or getattr(user, 'is_curation', False)):
        return HttpResponseForbidden("You do not have permission to access this page.")

    micro = get_object_or_404(MicroCredential, id=microcredential_id)
    enrollments = MicroCredentialEnrollment.objects.filter(microcredential=micro)
    total_participants = enrollments.count()
    required_courses = micro.required_courses.all()

    participants_data = []
    for enrollment in enrollments:
        user = enrollment.user
        user_micro = UserMicroCredential.objects.filter(user=user, microcredential=micro).first()
        micro_claim = MicroClaim.objects.filter(user=user, microcredential=micro).first()
        completed = user_micro.completed if user_micro else False
        certificate_id = user_micro.certificate_id if user_micro else "N/A"
        issued_at = micro_claim.issued_at if micro_claim else None 

        country = user.country if user.country else "N/A"
        gender = user.gender if user.gender else "N/A"
        university = user.university.name if user.university else "N/A"
        full_name = f"{user.first_name} {user.last_name}".strip() or user.username

        course_progress = []
        total_user_score = Decimal(0)
        total_max_score = Decimal(0)
        all_courses_completed = True

        for course in required_courses:
            assessments = Assessment.objects.filter(section__courses=course)
            course_score = Decimal(0)
            course_max_score = Decimal(0)
            course_completed = True

            for assessment in assessments:
                score_value = Decimal(0)
                total_questions = assessment.questions.count()
                if total_questions > 0:
                    total_correct_answers = 0
                    answers_exist = False
                    for question in assessment.questions.all():
                        answers = QuestionAnswer.objects.filter(question=question, user=user)
                        if answers.exists():
                            answers_exist = True
                        total_correct_answers += answers.filter(choice__is_correct=True).count()
                    if not answers_exist:
                        course_completed = False
                    if total_questions > 0:
                        score_value = (Decimal(total_correct_answers) / Decimal(total_questions)) * Decimal(assessment.weight)
                else:
                    askora_submissions = Submission.objects.filter(askora__assessment=assessment, user=user)
                    if not askora_submissions.exists():
                        course_completed = False
                    else:
                        latest_submission = askora_submissions.order_by('-submitted_at').first()
                        assessment_score = AssessmentScore.objects.filter(submission=latest_submission).first()
                        if assessment_score:
                            score_value = Decimal(assessment_score.final_score)

                score_value = min(score_value, Decimal(assessment.weight))
                course_score += score_value
                course_max_score += assessment.weight

            course_score = course_score.quantize(Decimal('1'), rounding=ROUND_DOWN)
            course_max_score = course_max_score.quantize(Decimal('1'), rounding=ROUND_DOWN)
            min_score = Decimal(micro.get_min_score(course) or 0).quantize(Decimal('1'), rounding=ROUND_DOWN)
            course_passed = course_completed and course_score >= min_score

            course_progress.append({
                'course_name': course.course_name,
                'user_score': course_score,
                'max_score': course_max_score,
                'min_score': min_score,
                'completed': course_completed,
                'passed': course_passed,
            })

            total_user_score += course_score
            total_max_score += course_max_score
            if not course_passed:
                all_courses_completed = False

        total_user_score = total_user_score.quantize(Decimal('1'), rounding=ROUND_DOWN)
        total_max_score = total_max_score.quantize(Decimal('1'), rounding=ROUND_DOWN)
        microcredential_passed = all_courses_completed and total_user_score >= Decimal(micro.min_total_score)

        # CEK APAKAH SUDAH KLAIM SERTIFIKAT
        micro_claim = MicroClaim.objects.filter(user=user, microcredential=micro).first()
        has_claimed = bool(micro_claim)
        certificate_claim_id = micro_claim.certificate_id if micro_claim else "N/A"
        claim_verified = micro_claim.verified if micro_claim else False
        claimed_at = micro_claim.claim_date if micro_claim else None

        participants_data.append({
            'full_name': full_name,
            'email': user.email,
            'country': country,
            'gender': gender,
            'university': university,
            'total_user_score': total_user_score,
            'total_max_score': total_max_score,
            'min_total_score': micro.min_total_score,
            'microcredential_passed': microcredential_passed,
            'completed': completed,
            'certificate_id': certificate_claim_id,
            'issued_at': issued_at,
            'claimed': has_claimed,
            'verified': claim_verified,
            'claimed_at': claimed_at,
            'course_progress': course_progress,
        })

    # PAGINATION
    per_page = 25
    paginator = Paginator(participants_data, per_page)
    page = request.GET.get('page')

    try:
        participants_page = paginator.page(page)
    except PageNotAnInteger:
        participants_page = paginator.page(1)
    except EmptyPage:
        participants_page = paginator.page(paginator.num_pages)

    context = {
        'report': {
            'microcredential_title': micro.title,
            'microcredential_id': micro.id,
            'total_participants': total_participants,
            'min_total_score': micro.min_total_score,
            'participants': participants_page,
        },
        'current_date': timezone.now().date(),
    }

    return render(request, 'micro/microcredential_report.html', context)


@login_required
def microcredential_report_pdf_view(request, microcredential_id):
    if not request.user.is_staff:
        raise PermissionDenied("You do not have permission to generate this PDF.")

    # Ambil data dari view utama
    micro = get_object_or_404(MicroCredential, id=microcredential_id)
    enrollments = MicroCredentialEnrollment.objects.filter(microcredential=micro)
    total_participants = enrollments.count()
    required_courses = micro.required_courses.all()

    participants_data = []
    for enrollment in enrollments:
        user = enrollment.user
        user_micro = UserMicroCredential.objects.filter(user=user, microcredential=micro).first()
        micro_claim = MicroClaim.objects.filter(user=user, microcredential=micro).first()
        completed = user_micro.completed if user_micro else False
        certificate_id = user_micro.certificate_id if user_micro else "N/A"
        issued_at = micro_claim.issued_at if micro_claim else None

        country = user.country or "N/A"
        gender = user.gender or "N/A"
        university = user.university.name if user.university else "N/A"
        full_name = f"{user.first_name} {user.last_name}".strip() or user.username

        course_progress = []
        total_user_score = Decimal(0)
        total_max_score = Decimal(0)
        all_courses_completed = True

        for course in required_courses:
            assessments = Assessment.objects.filter(section__courses=course)
            course_score = Decimal(0)
            course_max_score = Decimal(0)
            course_completed = True

            for assessment in assessments:
                score_value = Decimal(0)
                total_questions = assessment.questions.count()
                if total_questions > 0:
                    total_correct_answers = 0
                    answers_exist = False
                    for question in assessment.questions.all():
                        answers = QuestionAnswer.objects.filter(question=question, user=user)
                        if answers.exists():
                            answers_exist = True
                        total_correct_answers += answers.filter(choice__is_correct=True).count()
                    if not answers_exist:
                        course_completed = False
                    if total_questions > 0:
                        score_value = (Decimal(total_correct_answers) / Decimal(total_questions)) * Decimal(assessment.weight)
                else:
                    askora_submissions = Submission.objects.filter(askora__assessment=assessment, user=user)
                    if not askora_submissions.exists():
                        course_completed = False
                    else:
                        latest_submission = askora_submissions.order_by('-submitted_at').first()
                        assessment_score = AssessmentScore.objects.filter(submission=latest_submission).first()
                        if assessment_score:
                            score_value = Decimal(assessment_score.final_score)

                score_value = min(score_value, Decimal(assessment.weight))
                course_score += score_value
                course_max_score += assessment.weight

            course_score = course_score.quantize(Decimal('1'), rounding=ROUND_DOWN)
            course_max_score = course_max_score.quantize(Decimal('1'), rounding=ROUND_DOWN)
            min_score = Decimal(micro.get_min_score(course) or 0).quantize(Decimal('1'), rounding=ROUND_DOWN)
            course_passed = course_completed and course_score >= min_score

            course_progress.append({
                'course_name': course.course_name,
                'user_score': course_score,
                'max_score': course_max_score,
                'min_score': min_score,
                'completed': course_completed,
                'passed': course_passed,
            })

            total_user_score += course_score
            total_max_score += course_max_score
            if not course_passed:
                all_courses_completed = False

        total_user_score = total_user_score.quantize(Decimal('1'), rounding=ROUND_DOWN)
        total_max_score = total_max_score.quantize(Decimal('1'), rounding=ROUND_DOWN)
        microcredential_passed = all_courses_completed and total_user_score >= Decimal(micro.min_total_score)

        participants_data.append({
            'full_name': full_name,
            'email': user.email,
            'country': country,
            'gender': gender,
            'university': university,
            'total_user_score': total_user_score,
            'total_max_score': total_max_score,
            'min_total_score': micro.min_total_score,
            'microcredential_passed': microcredential_passed,
            'completed': completed,
            'certificate_id': certificate_id,
            'issued_at': issued_at,
            'course_progress': course_progress,
        })

    context = {
        'micro': micro,
        'participants': participants_data,
        'current_date': now().date(),
    }

    template = get_template('micro/microcredential_report_pdf.html')
    html_content = template.render(context)
    pdf_file = HTML(string=html_content).write_pdf()

    response = HttpResponse(pdf_file, content_type='application/pdf')
    response['Content-Disposition'] = f'filename="Microcredential_Report_{micro.id}_{now().strftime("%Y%m%d")}.pdf"'
    return response


@login_required
def add_microcredential_review(request, microcredential_id):
    microcredential = get_object_or_404(MicroCredential, id=microcredential_id)

    # Validasi apakah user terdaftar dalam microcredential
    is_enrolled = MicroCredentialEnrollment.objects.filter(user=request.user, microcredential=microcredential).exists()
    if not is_enrolled:
        messages.error(request, "You must be enrolled in this MicroCredential to leave a review.")
        return redirect('courses:micro_detail', slug=microcredential.slug)

    # Hitung kelulusan seluruh kursus
    required_courses = microcredential.required_courses.all()
    total_user_score = Decimal(0)
    total_max_score = Decimal(0)
    all_courses_completed = True

    for course in required_courses:
        assessments = Assessment.objects.filter(section__courses=course)
        course_score = Decimal(0)
        course_completed = True

        for assessment in assessments:
            score_value = Decimal(0)
            total_questions = assessment.questions.count()

            if total_questions > 0:  # Multiple Choice
                total_correct_answers = 0
                answers_exist = False
                for question in assessment.questions.all():
                    answers = QuestionAnswer.objects.filter(question=question, user=request.user)
                    if answers.exists():
                        answers_exist = True
                    total_correct_answers += answers.filter(choice__is_correct=True).count()
                if not answers_exist:
                    course_completed = False
                if total_questions > 0:
                    score_value = (Decimal(total_correct_answers) / Decimal(total_questions)) * Decimal(assessment.weight)
            else:  # AskOra
                submissions = Submission.objects.filter(askora__assessment=assessment, user=request.user)
                if not submissions.exists():
                    course_completed = False
                else:
                    latest = submissions.order_by('-submitted_at').first()
                    score_obj = AssessmentScore.objects.filter(submission=latest).first()
                    if score_obj:
                        score_value = Decimal(score_obj.final_score)

            score_value = min(score_value, Decimal(assessment.weight))
            course_score += score_value

        min_score = Decimal(microcredential.get_min_score(course))
        course_passed = course_completed and course_score >= min_score
        if not course_passed:
            all_courses_completed = False

        total_user_score += course_score
        total_max_score += sum(a.weight for a in assessments)

    microcredential_passed = all_courses_completed and total_user_score >= Decimal(microcredential.min_total_score)

    if not microcredential_passed:
        messages.error(request, "You must complete and pass all required courses to leave a review.")
        return redirect('courses:micro_detail', slug=microcredential.slug)

    # Form submission
    if request.method == 'POST':
        form = MicroCredentialReviewForm(request.POST)
        if form.is_valid():
            review, created = MicroCredentialReview.objects.get_or_create(
                user=request.user,
                microcredential=microcredential
            )
            review.rating = form.cleaned_data['rating']
            review.review_text = form.cleaned_data['review_text']
            review.save()
            if created:
                messages.success(request, "Your review has been submitted.")
            else:
                messages.success(request, "Your review has been updated.")
            return redirect('courses:micro_detail', id=microcredential.id, slug=microcredential.slug)
    else:
        existing_review = MicroCredentialReview.objects.filter(user=request.user, microcredential=microcredential).first()
        if existing_review:
            messages.info(request, "You're editing your previous review.")
            form = MicroCredentialReviewForm(instance=existing_review)
        else:
            form = MicroCredentialReviewForm()

    return render(request, 'micro/add_review.html', {
        'form': form,
        'microcredential': microcredential
    })


def self_course(request, username, id, slug):
    if not request.user.is_authenticated:
        return redirect(f"/login/?next={request.path}")

    course = get_object_or_404(Course, id=id, slug=slug)

    # Redirect jika bukan user yang benar
    if request.user.username != username:
        return redirect('authentication:course_list')

    is_instructor = course.instructor == request.user
    course_name = course.course_name

    # Prefetch semua konten yang diperlukan
    sections = Section.objects.filter(courses=course).prefetch_related(
        Prefetch('materials', queryset=Material.objects.all()),
        Prefetch('assessments', queryset=Assessment.objects.all().prefetch_related(
            Prefetch('questions', queryset=Question.objects.all().prefetch_related(
                Prefetch('choices', queryset=Choice.objects.all())
            )),
            Prefetch('ask_oras', queryset=AskOra.objects.all())
        ))
    )

    # Gabungkan material dan assessment jadi satu urutan
    combined_content = []
    for section in sections:
        for material in section.materials.all():
            combined_content.append(('material', material, section))
        for assessment in section.assessments.all():
            combined_content.append(('assessment', assessment, section))

    total_content = len(combined_content)

    # Tentukan konten saat ini
    material_id = request.GET.get('material_id')
    assessment_id = request.GET.get('assessment_id')
    current_content = None

    if not material_id and not assessment_id:
        current_content = combined_content[0] if combined_content else None
    elif material_id:
        material = get_object_or_404(Material, id=material_id)
        section = next((s for s in sections if material in s.materials.all()), None)
        current_content = ('material', material, section)
    elif assessment_id:
        assessment = get_object_or_404(Assessment, id=assessment_id)
        section = next((s for s in sections if assessment in s.assessments.all()), None)
        current_content = ('assessment', assessment, section)

    # Komentar
    comments = None
    page_comments = []
    if current_content:
        if current_content[0] == 'material':
            material = current_content[1]
            comments = Comment.objects.filter(material=material, parent=None).order_by('-created_at')
        elif current_content[0] == 'assessment':
            section = current_content[2]
            comments = Comment.objects.filter(material__section=section, parent=None).order_by('-created_at')

        if comments:
            paginator = Paginator(comments, 5)
            page_number = request.GET.get('page')
            page_comments = paginator.get_page(page_number)

    # Cek status assessment hanya jika sedang di assessment
    is_started = False
    is_expired = False
    remaining_time = 0

    if not is_instructor and current_content and current_content[0] == 'assessment':
        assessment = current_content[1]
        session = AssessmentSession.objects.filter(user=request.user, assessment=assessment).first()
        if session:
            is_started = True
            remaining_time = int((session.end_time - timezone.now()).total_seconds())
            if remaining_time <= 0:
                is_expired = True
                remaining_time = 0
        else:
            is_started = assessment.duration_in_minutes == 0

    # Index konten
    current_index = -1
    if current_content:
        for i, content in enumerate(combined_content):
            if (content[0] == current_content[0] and
                content[1].id == current_content[1].id and
                content[2].id == current_content[2].id):
                current_index = i
                break

    # Navigasi
    previous_content = combined_content[current_index - 1] if current_index > 0 else None
    next_content = combined_content[current_index + 1] if 0 <= current_index < total_content - 1 else None
    is_last_content = next_content is None

    previous_url = "#" if not previous_content else f"?{previous_content[0]}_id={previous_content[1].id}"
    next_url = "#" if not next_content else f"?{next_content[0]}_id={next_content[1].id}"

    # Progres dan tracking
    if not is_instructor:
        if current_content:
            if current_content[0] == 'material':
                material = current_content[1]
                MaterialRead.objects.get_or_create(user=request.user, material=material)
            elif current_content[0] == 'assessment':
                assessment = current_content[1]
                AssessmentRead.objects.get_or_create(user=request.user, assessment=assessment)

        user_progress, _ = CourseProgress.objects.get_or_create(user=request.user, course=course)
        if current_index + 1 > user_progress.progress_percentage / 100 * total_content:
            user_progress.progress_percentage = ((current_index + 1) / total_content) * 100
            user_progress.save()

    # Skor dan penilaian
    user_grade = None
    if not is_instructor:
        score = Score.objects.filter(user=request.user.username, course=course).order_by('-date').first()
        user_grade = 'Fail'
        if score and score.total_questions > 0:
            score_percentage = (score.score / score.total_questions) * 100
            user_grade = calculate_grade(score_percentage, course)

    assessments = Assessment.objects.filter(section__courses=course)
    assessment_scores = []
    total_score = 0
    total_max_score = 0
    all_assessments_submitted = True

    grade_range = GradeRange.objects.filter(course=course)
    if grade_range.exists():
        pass_grade = grade_range.filter(name='Pass').first()
        passing_threshold = pass_grade.min_grade if pass_grade else 0
    else:
        from django.urls import reverse
        grade_url = reverse('courses:course_grade', kwargs={'id': course.id})
        message = f'Grade range not found for this course. <a href="{grade_url}">Click here to add it.</a>'
        return render(request, 'error.html', {'message': message})


    for assessment in assessments:
        score_value = Decimal(0)
        total_questions = assessment.questions.count()
        total_correct = 0
        answers_exist = False

        if total_questions > 0:
            for question in assessment.questions.all():
                answers = QuestionAnswer.objects.filter(question=question, user=request.user)
                if answers.exists():
                    answers_exist = True
                total_correct += answers.filter(choice__is_correct=True).count()

            if not answers_exist:
                all_assessments_submitted = False

            if total_questions > 0:
                score_value = (Decimal(total_correct) / Decimal(total_questions)) * Decimal(assessment.weight)

        else:
            # Handle AskOra
            askora_submissions = Submission.objects.filter(
                askora__assessment=assessment, user=request.user
            )
            if not askora_submissions.exists():
                all_assessments_submitted = False
            else:
                latest_submission = askora_submissions.order_by('-submitted_at').first()
                assessment_score = AssessmentScore.objects.filter(submission=latest_submission).first()
                if assessment_score:
                    score_value = Decimal(assessment_score.final_score)

        score_value = min(score_value, Decimal(assessment.weight))
        total_score += score_value
        total_max_score += assessment.weight

        assessment_scores.append({
            'assessment': assessment,
            'score': score_value,
            'weight': assessment.weight
        })

    context = {
        'course': course,
        'course_name': course_name,
        'sections': sections,
        'current_content': current_content,
        'previous_url': previous_url,
        'next_url': next_url,
        'course_progress': user_progress.progress_percentage if not is_instructor else None,
        'user_grade': user_grade if not is_instructor else None,
        'assessment_results': assessment_scores,
        'total_score': total_score,
        'overall_percentage': (total_score / total_max_score * 100) if total_max_score > 0 else 0,
        'total_weight': total_max_score,
        'status': 'Pass' if total_score >= passing_threshold else 'Fail',
        'is_last_content': is_last_content,
        'comments': page_comments,
        'material': current_content[1] if current_content and current_content[0] == 'material' else None,
        'assessment': current_content[1] if current_content and current_content[0] == 'assessment' else None,
    }

    return render(request, 'instructor/self_course.html', context)





logger = logging.getLogger(__name__)


@login_required
def launch_lti(request, idcourse, idsection, idlti, id_lti_tool):
    user = request.user
    logger.info(f"LTI 1.1 Launch requested by user {user.username} (ID: {user.id})")

    # Get course, section, assessment, and tool
    course = get_object_or_404(Course, id=idcourse)
    section = get_object_or_404(Section, id=idsection, courses=course)
    assessment = get_object_or_404(Assessment, id=idlti, section=section)
    lti_tool = get_object_or_404(LTIExternalTool1, id=id_lti_tool, assessment=assessment)

    if not lti_tool:
        logger.error("LTI tool not configured for assessment %s", assessment.id)
        return HttpResponse("LTI tool belum dikonfigurasi.", status=400)

    launch_url = lti_tool.launch_url
    consumer_key = lti_tool.consumer_key
    shared_secret = lti_tool.shared_secret

    # Handle user
    user_id = str(user.id) if user.is_authenticated else str(uuid.uuid4())
    user_full_name = user.get_full_name() if user.is_authenticated else "Anonymous User"
    user_email = user.email if user.is_authenticated else "anonymous@example.com"


    # Tentukan role LTI berdasarkan role user di sistem LMS kita
    if user.is_superuser or user.is_staff:
        lti_role = "Instructor"
    elif getattr(user, "is_instructor", False):
        lti_role = "Instructor"
    else:
        lti_role = "Learner"

    # Basic OAuth and LTI parameters
    oauth_params = {
        "oauth_consumer_key": consumer_key,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_version": "1.0",
        "oauth_nonce": uuid.uuid4().hex,
        "oauth_timestamp": str(int(time.time())),
        "resource_link_id": f"res-{assessment.id}",
        "user_id": user_id,
        "roles": lti_role,
        "lis_person_name_full": user_full_name,
        "lis_person_contact_email_primary": user_email,
        "context_id": f"course-{course.id}",
        "context_title": getattr(assessment, "title", "Course"),
        "launch_presentation_locale": "en-US",
        "lti_version": "LTI-1p0",
        "lti_message_type": "basic-lti-launch-request",
        "tool_consumer_info_product_family_code": "django-lms",
        "tool_consumer_info_version": "1.0",
        "launch_presentation_document_target": "iframe",
    }

    # Add outcome service parameters
    result_sourcedid = f"lti-{assessment.id}-{user_id}"
    outcome_url = request.build_absolute_uri(reverse("learner:lti_grade_callback")).rstrip('/')
    oauth_params.update({
        "lis_outcome_service_url": outcome_url,
        "lis_result_sourcedid": result_sourcedid,
    })

    # Add custom parameters
    if lti_tool.custom_parameters:
        try:
            for line in lti_tool.custom_parameters.strip().splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    oauth_params[k.strip()] = v.strip()
        except Exception as e:
            logger.warning("Failed to parse custom_parameters: %s", e)

    # Generate OAuth signature
    signature = generate_oauth_signature(oauth_params, shared_secret, launch_url)
    oauth_params["oauth_signature"] = signature

    logger.debug("Sending LTI Launch to %s with params: %s", launch_url, oauth_params)

    # Initialize LTIResult record
    if user.is_authenticated:
        try:
            LTIResult.objects.update_or_create(
                user=user,
                assessment=assessment,
                defaults={
                    'result_sourcedid': result_sourcedid,
                    'outcome_service_url': outcome_url,
                    'consumer_key': consumer_key,
                    'score': None,
                    'last_sent_at': None,
                    'created_at': timezone.now(),
                }
            )
            logger.info("Initialized LTIResult for user %s, assessment %s", user_id, assessment.id)
        except Exception as e:
            logger.error("Failed to initialize LTIResult: %s", e)

    return render(request, "learner/lti_launch_form.html", {
        "launch_url": launch_url,
        "params": oauth_params,
    })






logger = logging.getLogger(__name__)

@login_required
def create_lti(request, idcourse, idsection, idlti):

    # 1️⃣ Pastikan user login
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)

    user = request.user
    course = None
    team_member = None  # inisialisasi

    # 2️⃣ Prioritas superuser / curation
    if user.is_superuser or user.is_curation:
        course = get_object_or_404(Course, id=idcourse)

    # 3️⃣ Partner / instructor hanya jika course belum ditemukan
    if not course and user.is_partner:
        course = get_object_or_404(Course, id=idcourse, org_partner__user_id=user.id)

    if not course and user.is_instructor:
        course = get_object_or_404(Course, id=idcourse, instructor__user_id=user.id)

    # 4️⃣ Cek CourseTeam sebagai fallback
    if not course:
        team_member = CourseTeam.objects.filter(course_id=idcourse, user=user).first()
        if team_member:
            course = team_member.course
        else:
            messages.error(request, "You do not have permission to view questions for this course.")
            return redirect('authentication:home')

    # Ambil section dan assessment terkait
    section = get_object_or_404(Section, id=idsection, courses=course)
    assessment = get_object_or_404(Assessment, id=idlti, section=section)

    # Jika form disubmit
    if request.method == 'POST':
        form = LTIExternalToolForm(request.POST)
        if form.is_valid():
            # Cek apakah LTI tool sudah ada untuk assessment ini
            if hasattr(assessment, 'lti_tool'):
                messages.error(request, "Assessment ini sudah memiliki alat LTI.")
            else:
                lti_tool = form.save(commit=False)
                lti_tool.assessment = assessment
                lti_tool.save()
                messages.success(request, "Alat LTI berhasil ditambahkan!")
                return redirect('courses:view-question', idcourse=course.id, idsection=section.id, idassessment=assessment.id)
    else:
        form = LTIExternalToolForm()

    return render(request, 'courses/lti_tool_form.html', {
        'form': form,
        'course': course,
        'section': section,
        'assessment': assessment,
    })

@login_required
def edit_lti(request, idcourse, idsection, idlti, id_lti_tool):
    # 1️⃣ Pastikan user login
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)

    user = request.user
    course = None
    team_member = None  # inisialisasi

    # 2️⃣ Prioritas superuser / curation
    if user.is_superuser or user.is_curation:
        course = get_object_or_404(Course, id=idcourse)

    # 3️⃣ Partner / instructor hanya jika course belum ditemukan
    if not course and user.is_partner:
        course = get_object_or_404(Course, id=idcourse, org_partner__user_id=user.id)

    if not course and user.is_instructor:
        course = get_object_or_404(Course, id=idcourse, instructor__user_id=user.id)

    # 4️⃣ Cek CourseTeam sebagai fallback
    if not course:
        team_member = CourseTeam.objects.filter(course_id=idcourse, user=user).first()
        if team_member:
            course = team_member.course
        else:
            messages.error(request, "You do not have permission to view questions for this course.")
            return redirect('authentication:home')

    # Pastikan section milik course
    section = get_object_or_404(Section, id=idsection, courses=course)

    # Pastikan assessment milik section
    assessment = get_object_or_404(Assessment, id=idlti, section=section)

    # Pastikan LTI tool milik assessment
    lti_tool = get_object_or_404(LTIExternalTool1, id=id_lti_tool, assessment=assessment)

    # Menangani form
    if request.method == 'POST':
        form = LTIExternalToolForm(request.POST, instance=lti_tool)
        if form.is_valid():
            lti_tool = form.save(commit=False)
            lti_tool.assessment = assessment
            try:
                lti_tool.save()
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True,
                        'message': 'Alat LTI berhasil diperbarui.',
                        'redirect_url': reverse('courses:view-question', kwargs={
                            'idcourse': course.id,
                            'idsection': section.id,
                            'idassessment': assessment.id
                        })
                    })
                messages.success(request, "Alat LTI berhasil diperbarui.")
                return redirect('courses:view-question', idcourse=course.id, idsection=section.id, idassessment=assessment.id)
            except ValueError as e:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'errors': str(e)}, status=400)
                messages.error(request, str(e))
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'errors': form.errors}, status=400)
            messages.error(request, "Ada kesalahan dalam formulir. Silakan periksa kembali.")
    else:
        form = LTIExternalToolForm(instance=lti_tool)

    return render(request, 'courses/edit_lti_tool_form.html', {
        'course': course,
        'section': section,
        'assessment': assessment,
        'form': form,
    })


@login_required
def delete_lti(request, idcourse, idsection, idlti, id_lti_tool):
    # 1️⃣ Pastikan user login
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)

    user = request.user
    course = None
    team_member = None  # inisialisasi

    # 2️⃣ Prioritas superuser / curation
    if user.is_superuser or user.is_curation:
        course = get_object_or_404(Course, id=idcourse)

    # 3️⃣ Partner / instructor hanya jika course belum ditemukan
    if not course and user.is_partner:
        course = get_object_or_404(Course, id=idcourse, org_partner__user_id=user.id)

    if not course and user.is_instructor:
        course = get_object_or_404(Course, id=idcourse, instructor__user_id=user.id)

    # 4️⃣ Cek CourseTeam sebagai fallback
    if not course:
        team_member = CourseTeam.objects.filter(course_id=idcourse, user=user).first()
        if team_member:
            course = team_member.course
        else:
            messages.error(request, "You do not have permission to view questions for this course.")
            return redirect('authentication:home')

    # Pastikan section milik course
    section = get_object_or_404(Section, id=idsection, courses=course)

    # Pastikan assessment milik section
    assessment = get_object_or_404(Assessment, id=idlti, section=section)

    # Pastikan LTI tool milik assessment
    lti_tool = get_object_or_404(LTIExternalTool1, id=id_lti_tool, assessment=assessment)

    if request.method == 'POST':
        try:
            lti_tool.delete()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': 'Alat LTI berhasil dihapus.',
                    'redirect_url': reverse('courses:view-question', kwargs={
                        'idcourse': course.id,
                        'idsection': section.id,
                        'idassessment': assessment.id
                    })
                })
            messages.success(request, "Alat LTI berhasil dihapus.")
            return redirect('courses:view-question', idcourse=course.id, idsection=section.id, idassessment=assessment.id)
        except Exception as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'errors': str(e)}, status=400)
            messages.error(request, f"Gagal menghapus alat LTI: {str(e)}")
            return redirect('courses:view-question', idcourse=course.id, idsection=section.id, idassessment=assessment.id)

    # Jika bukan POST, arahkan kembali ke halaman view-question
    return redirect('courses:view-question', idcourse=course.id, idsection=section.id, idassessment=assessment.id)

@csrf_exempt
@require_POST
def reorder_section(request):
    try:
        sections_data = json.loads(request.POST.get('sections', '[]'))
        subsections_data = json.loads(request.POST.get('subsections', '[]'))

        if not sections_data and not subsections_data:
            return JsonResponse({'status': 'error', 'message': 'No data provided for reordering'}, status=400)

        # Update sections
        for item in sections_data:
            section = Section.objects.get(id=item['id'])
            section.order = item['order']
            section.save()

        # Update subsections
        for item in subsections_data:
            subsection = Section.objects.get(id=item['id'])
            subsection.order = item['order']
            subsection.parent_id = item.get('parent_id') or None
            subsection.save()

        return JsonResponse({'status': 'success', 'message': 'Order updated successfully'})
    except Section.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'One or more sections/subsections not found'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'Error: {str(e)}'}, status=500)
    


logger = logging.getLogger(__name__)


@login_required
def course_list_enroll(request, id):
    """
    Menampilkan daftar peserta kursus dengan detail skor lengkap
    (LTI, In-video Quiz, MCQ, Askora), progress, status kelulusan,
    dan export CSV.
    """

    # --- Cek course ---
    course = get_object_or_404(Course, id=id)
    user = request.user

    # === 🔒 ACCESS CONTROL ===
    allowed_roles = ['curation', 'finance']

    is_allowed = (
        user.is_superuser or
        user.is_staff or
        (hasattr(user, 'role') and user.role in allowed_roles) or
        user.groups.filter(name__in=allowed_roles).exists()
    )

    # Partner
    is_partner_owner = (
        hasattr(user, 'partner_user') and
        course.org_partner and
        course.org_partner.user == user
    )

    # Instructor
    is_instructor = (
        hasattr(course, 'instructor') and
        course.instructor and
        course.instructor.user == user
    )

    if not (is_allowed or is_partner_owner or is_instructor):
        messages.error(request, "Access denied.")
        return redirect('authentication:home')

    # --- Ambil enrollments ---
    enrollments = course.enrollments.all()

    # --- Pencarian ---
    search_query = request.GET.get('search', '')
    if search_query:
        enrollments = enrollments.filter(
            Q(user__email__icontains=search_query) |
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query)
        )

    sections = course.sections.all()
    section_ids = sections.values_list('id', flat=True)
    user_ids = enrollments.values_list('user_id', flat=True)

    # --- MATERIAL READS ---
    material_reads = MaterialRead.objects.filter(
        user_id__in=user_ids,
        material__section_id__in=section_ids
    ).order_by('-read_at')

    last_material_map = {}
    for mr in material_reads:
        key = (mr.user_id, mr.material_id)
        if key not in last_material_map:
            last_material_map[key] = mr.read_at

    # --- ASSESSMENT READS ---
    assessment_ids = []
    for section in sections:
        assessment_ids += list(section.assessments.values_list('id', flat=True))

    assessment_reads = AssessmentRead.objects.filter(
        user_id__in=user_ids,
        assessment_id__in=assessment_ids
    ).order_by('-completed_at')

    last_assessment_map = {}
    for ar in assessment_reads:
        key = (ar.user_id, ar.assessment_id)
        if key not in last_assessment_map:
            last_assessment_map[key] = ar.completed_at

    # --- Passing threshold ---
    grade_ranges = GradeRange.objects.filter(course=course)
    if grade_ranges.exists():
        grade_fail = grade_ranges.order_by('max_grade').first()
        passing_threshold = grade_fail.max_grade + 1 if grade_fail else Decimal('60')
    else:
        passing_threshold = Decimal('60')

    # --- SIAPKAN HASIL ---
    enrollment_details = []
    assessments = Assessment.objects.filter(section__courses=course)

    for enrollment in enrollments:
        user = enrollment.user

        total_max_score = Decimal('0')
        total_score = Decimal('0')
        all_assessments_submitted = True

        # ==========================================
        # 🔥 PERHITUNGAN SKOR LENGKAP
        # (LTI → InVideo → MCQ → ASKORA)
        # ==========================================
        for assessment in assessments:
            score_value = Decimal('0')
            is_submitted = True
            weight = Decimal(assessment.weight)

            # === CASE 1: LTI RESULT ===
            lti_result = LTIResult.objects.filter(user=user, assessment=assessment).first()
            if lti_result and lti_result.score is not None:
                lti_score = Decimal(lti_result.score)
                if lti_score > 1.0:
                    lti_score = lti_score / 100
                score_value = lti_score * weight

            else:
                # === CASE 2: IN-VIDEO QUIZ ===
                invideo_quizzes = Quiz.objects.filter(assessment=assessment)

                if invideo_quizzes.exists():
                    quiz_result = QuizResult.objects.filter(
                        user=user,
                        assessment=assessment
                    ).first()

                    if quiz_result:
                        if quiz_result.total_questions > 0:
                            raw_percentage = Decimal(quiz_result.score) / Decimal(quiz_result.total_questions)
                            score_value = raw_percentage * weight
                        else:
                            score_value = Decimal('0')
                    else:
                        is_submitted = False
                        all_assessments_submitted = False

                else:
                    # === CASE 3: OLD QUESTION MODEL ===
                    total_questions = assessment.questions.count()
                    if total_questions > 0:
                        total_correct = 0
                        answers_exist = False

                        for q in assessment.questions.all():
                            answers = QuestionAnswer.objects.filter(question=q, user=user)
                            if answers.exists():
                                answers_exist = True
                            total_correct += answers.filter(choice__is_correct=True).count()

                        if not answers_exist:
                            is_submitted = False
                            all_assessments_submitted = False

                        score_value = (
                            (Decimal(total_correct) / Decimal(total_questions)) * weight
                        )
                    else:
                        # === CASE 4: ASKORA ===
                        askora_submissions = Submission.objects.filter(
                            askora__assessment=assessment, user=user
                        )

                        if not askora_submissions.exists():
                            is_submitted = False
                            all_assessments_submitted = False
                        else:
                            latest_submission = askora_submissions.order_by('-submitted_at').first()
                            assessment_score = AssessmentScore.objects.filter(
                                submission=latest_submission
                            ).first()

                            if assessment_score:
                                score_value = Decimal(assessment_score.final_score)
                            else:
                                is_submitted = False
                                all_assessments_submitted = False

            # Limit ke bobot
            score_value = min(score_value, weight)

            total_max_score += weight
            total_score += score_value

        # === Final scoring ===
        total_score = min(total_score, total_max_score)
        overall_percentage = (
            total_score / total_max_score * 100
            if total_max_score > 0 else Decimal('0')
        )

        # Bulatkan
        total_score = total_score.quantize(Decimal("0.01"))
        total_max_score = total_max_score.quantize(Decimal("0.01"))
        overall_percentage = overall_percentage.quantize(Decimal("0.01"))

        # === Progress ===
        course_progress = CourseProgress.objects.filter(
            user=user, course=course
        ).first()
        progress_percentage = Decimal(
            course_progress.progress_percentage if course_progress else 0
        ).quantize(Decimal("0.01"))

        # === Status Kelulusan ===
        passing_criteria_met = (
            overall_percentage >= passing_threshold and progress_percentage == 100
        )
        status = "Pass" if all_assessments_submitted and passing_criteria_met else "Fail"

        # === Last Access ===
        last_accessed_material = None
        last_completed_assessment = None
        for section in sections:
            # materials
            for material in section.materials.all():
                t = last_material_map.get((user.id, material.id))
                if t and (not last_accessed_material or t > last_accessed_material):
                    last_accessed_material = t
            # assessments
            for assessment in section.assessments.all():
                t = last_assessment_map.get((user.id, assessment.id))
                if t and (not last_completed_assessment or t > last_completed_assessment):
                    last_completed_assessment = t

        enrollment_details.append({
            'user': user,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'last_login': user.last_login,
            'gender': getattr(user, 'gender', 'N/A'),
            'birth': getattr(user, 'birth', 'N/A'),
            'address': getattr(user, 'address', 'N/A'),
            'country': getattr(user, 'country', 'N/A'),
            'phone': getattr(user, 'phone', 'N/A'),
            'education': getattr(user, 'education', 'N/A'),
            'university': getattr(user, 'university', 'N/A'),
            'total_score': total_score,
            'total_max_score': total_max_score,
            'status': status,
            'progress_percentage': progress_percentage,
            'overall_percentage': overall_percentage,
            'last_accessed_material': last_accessed_material,
            'last_completed_assessment': last_completed_assessment,
        })

    # === Pagination ===
    paginator = Paginator(enrollment_details, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # === Export CSV ===
    if request.GET.get('download') == 'csv':
        return download_enrollment_data(course, enrollment_details)

    return render(request, 'courses/course_enroll_list.html', {
        'course': course,
        'enrollments': page_obj,
        'search_query': search_query,
    })

def download_enrollment_data(course, enrollment_details):
    """
    Export data enrollment ke CSV
    """
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{course.course_name}_enrollments.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Name', 'Email', 'Last Login', 'Gender', 'Birth', 'Address', 'Country',
        'Phone', 'Education', 'University', 'Score', 'Status', 'Progress %', 'Overall %',
        'Last Accessed Material', 'Last Completed Assessment'
    ])

    for enrollment in enrollment_details:
        full_name = f"{enrollment.get('first_name', '')} {enrollment.get('last_name', '')}".strip()
        last_login = enrollment.get('last_login')
        last_login_str = last_login.strftime('%Y-%m-%d %H:%M:%S') if last_login else ''
        birth = enrollment.get('birth')
        birth_str = birth.strftime('%Y-%m-%d') if hasattr(birth, "strftime") else (birth if birth != 'N/A' else '')

        writer.writerow([
            full_name,
            enrollment.get('email', ''),
            last_login_str,
            enrollment.get('gender', ''),
            birth_str,
            enrollment.get('address', ''),
            enrollment.get('country', ''),
            enrollment.get('phone', ''),
            enrollment.get('education', ''),
            enrollment.get('university', ''),
            f"{enrollment.get('total_score', 0):.2f} / {enrollment.get('total_max_score', 0):.2f}",
            enrollment.get('status', ''),
            f"{enrollment.get('progress_percentage', 0):.2f}%",
            f"{enrollment.get('overall_percentage', 0):.2f}%",
            enrollment['last_accessed_material'].strftime('%Y-%m-%d %H:%M:%S') if enrollment.get('last_accessed_material') else '',
            enrollment['last_completed_assessment'].strftime('%Y-%m-%d %H:%M:%S') if enrollment.get('last_completed_assessment') else '',
        ])

    return response



@login_required
def submit_rating(request, id, slug):
    course = get_object_or_404(Course, id=id, slug=slug)

    # Cek apakah user sudah lulus
    if not user_has_passed_course(request.user, course):
        messages.error(request, "Kamu hanya bisa memberi rating setelah lulus dari course ini.")
        return redirect('courses:course_lms_detail', id=course.id, slug=course.slug)

    # Cek apakah user sudah memberi rating sebelumnya
    if CourseRating.objects.filter(user=request.user, course=course).exists():
        messages.info(request, "Kamu sudah memberikan rating untuk course ini.")
        return redirect('courses:course_lms_detail', id=course.id, slug=course.slug)

    if request.method == 'POST':
        form = CourseRatingForm(request.POST)

        # Deteksi aktivitas mencurigakan
        if is_suspicious(request):
            messages.warning(request, "Aktivitas mencurigakan terdeteksi. Rating tidak disimpan.")
            return redirect('courses:course_lms_detail', id=course.id, slug=course.slug)

        if form.is_valid():
            rating = form.save(commit=False)
            comment = form.cleaned_data.get('comment')

            # Validasi isi komentar
            blacklisted = check_for_blacklisted_keywords(comment)
            if blacklisted:
                messages.warning(request, f"Komentarmu mengandung kata yang dilarang: '{blacklisted}'")
                return redirect('courses:course_lms_detail', id=course.id, slug=course.slug)

            # Cek spam (opsional)
            if hasattr(rating, 'is_spam') and rating.is_spam():
                messages.warning(request, "Terlalu sering mengirim rating. Coba lagi nanti.")
                return redirect('courses:course_lms_detail', id=course.id, slug=course.slug)

            rating.user = request.user
            rating.course = course
            rating.save()

            messages.success(request, "Terima kasih! Rating kamu sudah disimpan.")
            return redirect('courses:course_lms_detail', id=course.id, slug=course.slug)
    else:
        form = CourseRatingForm()

    return render(request, 'home/submit_rating.html', {'form': form, 'course': course})

@ratelimit(key='ip', rate='100/h')
def category_course_list(request, slug):
    # Mengambil objek Category berdasarkan slug
    category = get_object_or_404(Category, slug=slug)

    # Mendapatkan status 'published'
    published_status = CourseStatus.objects.filter(status='published').first()
    if not published_status:
        return HttpResponseNotFound("Status 'published' tidak ditemukan")

    # Ambil courses yang terkait dengan kategori tersebut dan status 'published'
    courses = Course.objects.filter(
        category=category,
        status_course=published_status,
        end_enrol__gte=timezone.now()
    ).select_related(
        'category', 'instructor__user', 'org_partner'
    ).prefetch_related('enrollments', 'prices')

    # Paginasi: menampilkan 10 kursus per halaman
    paginator = Paginator(courses, 10)
    page = request.GET.get('page')

    try:
        courses_paginated = paginator.page(page)
    except PageNotAnInteger:
        courses_paginated = paginator.page(1)
    except EmptyPage:
        courses_paginated = paginator.page(paginator.num_pages)

    # Mengambil kategori yang terkait dengan kursus
    categories = Category.objects.filter(
        category_courses__status_course=published_status,
        category_courses__end_enrol__gte=timezone.now()
    ).annotate(course_count=Count('category_courses')).distinct()

    # Siapkan data untuk ditampilkan
    courses_data = []
    total_enrollments = 0

    for course in courses_paginated:
        review_qs = CourseRating.objects.filter(course=course)
        average_rating = round(review_qs.aggregate(avg=Avg('rating'))['avg'] or 0, 1)
        full_stars = int(average_rating)
        half_star = (average_rating % 1) >= 0.5
        empty_stars = 5 - full_stars - (1 if half_star else 0)

        num_enrollments = course.enrollments.count()
        total_enrollments += num_enrollments

        # Get pricing information
        course_price = course.prices.first()  # Get the first CoursePrice (adjust if specific price_type needed)
        price = course_price.portal_price if course_price else Decimal('0.00')
        is_free = price == Decimal('0.00')
        discount_amount = course_price.discount_amount if course_price else Decimal('0.00')
        normal_price = course_price.normal_price if course_price else Decimal('0.00')

        courses_data.append({
            'course_name': course.course_name,
            'course_id': course.id,
            'num_enrollments': num_enrollments,
            'course_slug': course.slug,
            'course_image': course.image.url if course.image else None,
            'instructor': course.instructor.user.get_full_name() if course.instructor else None,
            'instructor_username': course.instructor.user.username if course.instructor else None,
            'photo': course.instructor.user.photo.url if course.instructor and course.instructor.user.photo else None,
            'partner': course.org_partner.name if course.org_partner else None,
            'partner_kode': course.org_partner.name if course.org_partner else None,  # Changed from kode to name
            'partner_photo': course.org_partner.logo.url if course.org_partner and course.org_partner.logo else None,
            'category': course.category.name if course.category else None,
            'language': course.get_language_display(),
            'average_rating': average_rating,
            'review_count': review_qs.count(),
            'full_star_range': range(full_stars),
            'half_star': half_star,
            'empty_star_range': range(empty_stars),
            'duration': course.hour,
            'price': float(price),
            'is_free': is_free,
            'discount_amount': float(discount_amount),
            'normal_price': float(normal_price),  # Added for discount display
        })

    context = {
        'category': category,
        'courses': courses_data,
        'page_obj': courses_paginated,
        'total_courses': courses.count(),
        'total_enrollments': total_enrollments,
        'total_pages': paginator.num_pages,
        'current_page': courses_paginated.number,
        'start_index': courses_paginated.start_index(),
        'end_index': courses_paginated.end_index(),
        'categories': list(categories.values('id', 'name', 'course_count')),
    }

    

    return render(request, 'courses/course_list.html', context)

@csrf_protect

def search_posts(request):
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)
    
    user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
    if 'bot' in user_agent or 'crawler' in user_agent:
        return HttpResponse(render_to_string('messages.html', {'message': "Akses diblokir. Terdeteksi bot!", 'type': 'error'}))

    user_profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if user_profile.is_blocked():
        return render(request, 'blocked.html', {'until': user_profile.blocked_until})

    was_limited = getattr(request, 'limited', False)
    if was_limited:
        user_profile.blocked_until = timezone.now() + timedelta(days=1)
        user_profile.save()
        return HttpResponse(render_to_string('messages.html', {'message': "Diblokir 1 hari karena melanggar batas!", 'type': 'error'}))
    
    query = request.GET.get('q', '').strip()
    posts = SosPost.objects.filter(
        deleted=False,
        content__icontains=query
    ).select_related('user', 'parent').prefetch_related('replies').order_by('-created_at')[:10]
    
    for post in posts:
        post.liked = Like.objects.filter(user=request.user, post=post).exists()
        post.like_count = Like.objects.filter(post=post).count()
    
    html = ''
    for post in posts:
        if not post.parent:
            html += render_to_string('home/post_item.html', {'post': post}, request=request)
    
    return HttpResponse(html if html else '<p>No posts found for this search.</p>')

@csrf_protect
def posts_by_hashtag(request, hashtag):
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)
    
    user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
    if 'bot' in user_agent or 'crawler' in user_agent:
        return HttpResponse(render_to_string('messages.html', {'message': "Akses diblokir. Terdeteksi bot!", 'type': 'error'}))

    user_profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if user_profile.is_blocked():
        return render(request, 'blocked.html', {'until': user_profile.blocked_until})

    was_limited = getattr(request, 'limited', False)
    if was_limited:
        user_profile.blocked_until = timezone.now() + timedelta(days=1)
        user_profile.save()
        return HttpResponse(render_to_string('messages.html', {'message': "Diblokir 1 hari karena melanggar batas!", 'type': 'error'}))
    
    posts = SosPost.objects.filter(
        deleted=False,
        hashtags__name=hashtag.lower()
    ).select_related('user', 'parent').prefetch_related('replies').order_by('-created_at')[:10]
    
    for post in posts:
        post.liked = Like.objects.filter(user=request.user, post=post).exists()
        post.like_count = Like.objects.filter(post=post).count()
    
    html = ''
    for post in posts:
        if not post.parent:  # Hanya post utama
            html += render_to_string('home/post_item.html', {'post': post}, request=request)
    
    return HttpResponse(html if html else '<p>No posts found for this hashtag.</p>')

def create_and_list_sos_posts(request):
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)
    
    user = request.user

    # Validasi data diri wajib
    required_fields = {
        'first_name': 'First Name',
        'last_name': 'Last Name',
        'email': 'Email',
        'phone': 'Phone Number',
        'gender': 'Gender',
        'birth': 'Date of Birth',
    }

    missing_fields = [
        label for field, label in required_fields.items()
        if not getattr(user, field, None)
        or (isinstance(getattr(user, field), str) and not getattr(user, field).strip())
    ]

    if missing_fields:
        messages.warning(
            request,
            f"Please complete your profile before accessing microcredentials: {', '.join(missing_fields)}"
        )
        return redirect('authentication:edit-profile', pk=user.pk)
    
    user_profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if user_profile.is_blocked():
        return render(request, 'blocked.html', {'until': user_profile.blocked_until})

    # Ambil post awal (misalnya 10 pertama)
    posts = SosPost.objects.filter(deleted=False).select_related('user', 'parent').prefetch_related('replies').order_by('-created_at')[:10]
    
    for post in posts:
        post.liked = Like.objects.filter(user=request.user, post=post).exists()
        post.like_count = Like.objects.filter(post=post).count()

    today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    trending = Hashtag.objects.filter(posts__created_at__gte=today).annotate(count=Count('posts')).order_by('-count')[:5]
    
    form = SosPostForm()
    context = {
        'form': form,
        'posts': posts,
        'trending': trending,
        'default_photo': '/media/profile_pics/hasbusiness-icon.png'
    }
    return render(request, 'home/sosial.html', context)

def load_more_posts(request):
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)
    
    user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
    if 'bot' in user_agent or 'crawler' in user_agent:
        return HttpResponse(render_to_string('messages.html', {'message': "Akses diblokir. Terdeteksi bot!", 'type': 'error'}))

    user_profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if user_profile.is_blocked():
        return render(request, 'blocked.html', {'until': user_profile.blocked_until})

    was_limited = getattr(request, 'limited', False)
    if was_limited:
        user_profile.blocked_until = timezone.now() + timedelta(days=1)
        user_profile.save()
        return HttpResponse(render_to_string('messages.html', {'message': "Diblokir 1 hari karena melanggar batas!", 'type': 'error'}))
    
    if request.method == 'GET':
        offset = int(request.GET.get('offset', 0))
        hashtag = request.GET.get('hashtag', None)
        query = request.GET.get('q', None)
        limit = 10
        
        qs = SosPost.objects.filter(deleted=False)
        if hashtag:
            qs = qs.filter(hashtags__name=hashtag.lower())
        if query:
            qs = qs.filter(content__icontains=query)
        
        posts = qs.select_related('user', 'parent').prefetch_related('replies').order_by('-created_at')[offset:offset + limit]
        
        html = ''
        for post in posts:
            if not post.parent:
                html += render_to_string('home/post_item.html', {'post': post}, request=request)
        
        return HttpResponse(html if html else '<p>No more posts to load.</p>')
    return HttpResponse(status=400)

@csrf_protect
@require_POST
def create_post(request):
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)

    user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
    if 'bot' in user_agent or 'crawler' in user_agent:
        return HttpResponse(render_to_string('messages.html', {'message': "Akses diblokir. Terdeteksi bot!", 'type': 'error'}))

    user_profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if user_profile.is_blocked():
        return render(request, 'blocked.html', {'until': user_profile.blocked_until})

    was_limited = getattr(request, 'limited', False)
    if was_limited:
        user_profile.blocked_until = timezone.now() + timedelta(days=1)
        user_profile.save()
        return HttpResponse(render_to_string('messages.html', {'message': "Diblokir 1 hari karena melanggar batas!", 'type': 'error'}))

    if request.method == 'POST':
        form = SosPostForm(request.POST)
        if form.is_valid():
            new_post = form.save(commit=False)
            new_post.user = request.user
            new_post.save()
            liked = Like.objects.filter(user=request.user, post=new_post).exists()
            like_count = Like.objects.filter(post=new_post).count()
            html = render_to_string('home/post_item.html', {
                'post': new_post,
                'liked': liked,
                'like_count': like_count,
                'request': request,
                'default_photo': '/media/profile_pics/hasbusiness-icon.png'
            })
            return HttpResponse(html, headers={'HX-Trigger': 'clearForm'})
        else:
            return HttpResponse(render_to_string('messages.html', {'message': "Form tidak valid!", 'type': 'error'}))
    return HttpResponse(status=400)
@csrf_protect
@require_POST
def like_post(request, post_id):
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)

    if request.method == 'POST':
        try:
            post = get_object_or_404(SosPost, id=post_id)
            like = Like.objects.filter(user=request.user, post=post).first()

            if like:
                like.delete()
                liked = False
            else:
                Like.objects.create(user=request.user, post=post)
                liked = True

            like_count = Like.objects.filter(post=post).count()

            html = render_to_string('home/like_button.html', {
                'post': post,
                'liked': liked,
                'like_count': like_count
            })
            return HttpResponse(html)

        except SosPost.DoesNotExist:
            return HttpResponse(render_to_string('messages.html', {'message': "Postingan tidak ditemukan!", 'type': 'error'}))
        except Exception:
            return HttpResponse(status=500)

    return HttpResponse(status=400)

@csrf_protect
@require_POST

def reply_post(request, post_id):
    try:
        if not request.user.is_authenticated:
            return redirect("/login/?next=%s" % request.path)
        
        user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
        if 'bot' in user_agent or 'crawler' in user_agent:
            return HttpResponse(render_to_string('messages.html', {'message': "Akses diblokir. Terdeteksi bot!", 'type': 'error'}))

        user_profile, _ = UserProfile.objects.get_or_create(user=request.user)
        if user_profile.is_blocked():
            return render(request, 'blocked.html', {'until': user_profile.blocked_until})

        was_limited = getattr(request, 'limited', False)
        if was_limited:
            user_profile.blocked_until = timezone.now() + timedelta(days=1)
            user_profile.save()
            return HttpResponse(render_to_string('messages.html', {'message': "Diblokir 1 hari karena melanggar batas!", 'type': 'error'}))
        
        if request.method == 'POST':
            form = SosPostForm(request.POST)
            if form.is_valid():
                reply = form.save(commit=False)
                reply.user = request.user
                reply.parent = SosPost.objects.get(id=post_id)
                reply.save()
                reply.liked = Like.objects.filter(user=request.user, post=reply).exists()
                reply.like_count = Like.objects.filter(post=reply).count()
                html = render_to_string('home/post_item.html', {'post': reply})
                return HttpResponse(html, headers={'HX-Trigger': 'clearForm'})
            return HttpResponse(render_to_string('messages.html', {'message': "Form tidak valid!", 'type': 'error'}))
        return HttpResponse(status=400)
    except SosPost.DoesNotExist:
        return HttpResponse(render_to_string('messages.html', {'message': "Post tidak ditemukan!", 'type': 'error'}))
    except Exception:
        return HttpResponse(status=500)
    
def reply_form(request, post_id):
    try:
        post = SosPost.objects.get(id=post_id)
        html = render_to_string('home/reply_form.html', {'post_id': post_id})
        return HttpResponse(html)
    except SosPost.DoesNotExist:
        return HttpResponse(render_to_string('messages.html', {'message': "Post tidak ditemukan!", 'type': 'error'}))

def micro_detail(request, id, slug):
    # Ambil data MicroCredential
    microcredential = get_object_or_404(MicroCredential, id=id, slug=slug)

    # Mengecek apakah pengguna sudah terdaftar dalam microcredential
    is_enrolled = False
    if request.user.is_authenticated:
        is_enrolled = MicroCredentialEnrollment.objects.filter(user=request.user, microcredential=microcredential).exists()

    # Ambil semua review
    reviews = microcredential.reviews.select_related('user').all().order_by('-created_at')

    # Paginasi: menampilkan 10 review per halaman
    paginator_reviews = Paginator(reviews, 10)  # 10 review per halaman
    page_number_reviews = request.GET.get('page')  # ambil nomor halaman dari URL
    page_obj_reviews = paginator_reviews.get_page(page_number_reviews)

    # Hitung rating rata-rata dan jumlah review
    rating_summary = reviews.aggregate(
        average_rating=Avg('rating'),
        total_reviews=Count('id')
    )


    # Ambil semua review untuk microcredential ini
    reviews = microcredential.reviews.all().order_by('-created_at')

    # Hitung rating rata-rata dan jumlah review
    rating_summary = reviews.aggregate(
        average_rating=Avg('rating'),
        total_reviews=Count('id')
    )
    # Ambil komentar utama (parent) untuk microcredential ini
    comments = MicroCredentialComment.objects.filter(microcredential=microcredential, parent=None).order_by('-created_at')

    # Paginasi komentar utama
    paginator_comments = Paginator(comments, 10)  # 10 komentar per halaman
    page_number_comments = request.GET.get('page_comments')
    page_obj_comments = paginator_comments.get_page(page_number_comments)

    

    context = {
        'microcredential': microcredential,
        'page_obj_reviews': page_obj_reviews,  # Paginasi review
        'average_rating': rating_summary['average_rating'] or 0,
        'total_reviews': rating_summary['total_reviews'],
        'is_enrolled': is_enrolled,  # Menambahkan status enrollment ke context

        # Menambahkan komentar ke context
        'page_obj_comments': page_obj_comments,  # Paginasi komentar
       
    }

    return render(request, 'micro/micro_detail.html', context)


logger = logging.getLogger(__name__)

# Form untuk validasi input komentar
class CommentForm(forms.Form):
    content = forms.CharField(max_length=1000, min_length=1, strip=True)
    parent_id = forms.IntegerField(required=False)
    honeypot = forms.CharField(required=False, widget=forms.HiddenInput)  # Honeypot untuk bot detection

    def clean_content(self):
        content = self.cleaned_data['content']
        # Sanitasi HTML menggunakan bleach
        cleaned_content = bleach.clean(content, tags=['p', 'br', 'strong', 'em'], strip=True)
        if len(cleaned_content.strip()) == 0:
            raise ValidationError("Comment cannot be empty after sanitization.")
        return cleaned_content

    def clean_honeypot(self):
        honeypot = self.cleaned_data['honeypot']
        if honeypot:
            raise ValidationError("Suspicious activity detected.")
        return honeypot

# Fungsi untuk mendeteksi aktivitas mencurigakan (bot detection)
def is_suspicious(request):
    user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
    # Contoh pemeriksaan sederhana: User-Agent kosong atau mencurigakan
    if not user_agent or 'bot' in user_agent or 'crawler' in user_agent:
        logger.warning("Suspicious request detected: Invalid User-Agent", extra={'user_agent': user_agent})
        return True
    # Periksa honeypot melalui form
    return False

# Fungsi untuk memeriksa kata kunci terlarang
def contains_blacklisted_keywords(content):
    blacklist = ['<script>', 'javascript:', 'onerror', 'onload', 'viagra', 'casino']  # Sesuaikan
    content_lower = content.lower()
    for keyword in blacklist:
        if keyword in content_lower:
            logger.warning("Blacklisted keyword detected: %s", keyword)
            return True
    return False

# Fungsi untuk memeriksa spam berdasarkan cooldown
def is_spam(user, cache_key_prefix="comment_spam"):
    from django.core.cache import cache
    cache_key = f"{cache_key_prefix}:{user.id}"
    last_comment_time = cache.get(cache_key)
    if last_comment_time:
        cooldown_seconds = 30  # Cooldown 30 detik
        if (timezone.now() - last_comment_time).total_seconds() < cooldown_seconds:
            logger.warning("Spam detected: User %s posting too frequently", user.id)
            return True
    cache.set(cache_key, timezone.now(), timeout=60)  # Cache selama 60 detik
    return False

# Kunci untuk rate-limiting
def get_ratelimit_key(group, request):
    user_agent = request.META.get('HTTP_USER_AGENT', 'unknown')
    return f"{request.META.get('REMOTE_ADDR')}:{user_agent}"

@ratelimit(key=get_ratelimit_key, rate='10/m', block=True)  # Batasi 10 permintaan per menit
@csrf_protect
@require_POST  # Hanya izinkan POST
def add_comment_microcredential(request, microcredential_id, slug):
    try:
        # Mengecek apakah pengguna sudah login
        if not request.user.is_authenticated:
            return redirect(f"/login/?next={request.path}")

        # Ambil data MicroCredential
        microcredential = get_object_or_404(MicroCredential, id=microcredential_id, slug=slug)

        # Validasi form
        form = CommentForm(request.POST)
        if not form.is_valid():
            logger.warning("Invalid comment form submission: %s", form.errors)
            messages.warning(request, "Invalid comment data.")
            return redirect('courses:micro_detail', id=microcredential.id, slug=microcredential.slug)

        # Deteksi bot melalui is_suspicious
        if is_suspicious(request):
            logger.warning("Suspicious activity detected for user %s", request.user.id)
            messages.warning(request, "Suspicious activity detected. Comment not posted.")
            return redirect('courses:micro_detail', id=microcredential.id, slug=microcredential.slug)

        content = form.cleaned_data['content']
        parent_id = form.cleaned_data['parent_id']
        parent_comment = None

        # Validasi parent_id jika ada
        if parent_id:
            try:
                parent_comment = MicroCredentialComment.objects.get(id=parent_id, microcredential=microcredential)
            except MicroCredentialComment.DoesNotExist:
                logger.warning("Invalid parent comment ID: %s", parent_id)
                messages.warning(request, "Invalid parent comment.")
                return redirect('courses:micro_detail', id=microcredential.id, slug=microcredential.slug)

        # Periksa kata kunci terlarang
        if contains_blacklisted_keywords(content):
            messages.warning(request, "Your comment contains blacklisted content.")
            return redirect('courses:micro_detail', id=microcredential.id, slug=microcredential.slug)

        # Periksa spam
        if is_spam(request.user):
            messages.warning(request, "You are posting too frequently. Please wait a moment before posting again.")
            return redirect('courses:micro_detail', id=microcredential.id, slug=microcredential.slug)

        # Buat dan simpan komentar
        comment = MicroCredentialComment(
            user=request.user,
            content=content,
            microcredential=microcredential,
            parent=parent_comment
        )
        comment.save()

        messages.success(request, 'Your comment has been posted.')
        return redirect('courses:micro_detail', id=microcredential.id, slug=microcredential.slug)

    except DatabaseError:
        logger.exception("Database error in add_comment_microcredential")
        messages.error(request, "A server error occurred. Please try again later.")
        return redirect('courses:micro_detail', id=microcredential.id, slug=microcredential.slug)
    except Exception as e:
        logger.exception("Unexpected error in add_comment_microcredential: %s", str(e))
        messages.error(request, "An unexpected error occurred.")
        return redirect('courses:micro_detail', id=microcredential.id, slug=microcredential.slug)
    

def reply_comment(request, comment_id):
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)
    
    # Ambil komentar yang akan dibalas
    comment = get_object_or_404(MicroCredentialComment, id=comment_id)

    # Jika form di-submit
    if request.method == 'POST':
        content = request.POST.get('content')
        if content:
            # Buat balasan komentar
            reply_comment = MicroCredentialComment(
                user=request.user,
                content=content,
                microcredential=comment.microcredential,
                parent=comment  # Tautkan dengan komentar induk
            )
            reply_comment.save()
            messages.success(request, 'Your reply has been posted.')
            return redirect('courses:micro_detail', id=comment.microcredential.id, slug=comment.microcredential.slug)

    return redirect('courses:micro_detail', id=comment.microcredential.id, slug=comment.microcredential.slug)


def enroll_microcredential(request, slug):
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)

    # Ambil microcredential berdasarkan slug
    microcredential = get_object_or_404(MicroCredential, slug=slug)

    # Cek apakah microcredential aktif dan dalam periode pendaftaran
    current_date = timezone.now().date()
    if microcredential.status != 'active':
        messages.error(request, "This MicroCredential is not currently active.")
        return redirect('courses:microcredential_detail', slug=slug)
    
    if microcredential.start_date and current_date < microcredential.start_date:
        messages.error(request, "Enrollment has not yet started for this MicroCredential.")
        return redirect('courses:microcredential_detail', slug=slug)
    
    if microcredential.end_date and current_date > microcredential.end_date:
        messages.error(request, "Enrollment has closed for this MicroCredential.")
        return redirect('courses:microcredential_detail', slug=slug)
    
    # Proses enrollment jika metode adalah POST
    if request.method == 'POST':
        enrollment, created = microcredential.enroll_user(request.user)
        if created:
            messages.success(request, f"You have successfully enrolled in {microcredential.title} and its required courses!")
        else:
            messages.info(request, f"You are already enrolled in {microcredential.title}.")
        return redirect('courses:microcredential_detail', slug=slug)

    # Tampilkan halaman konfirmasi enrollment
    context = {
        'microcredential': microcredential,
        'required_courses': microcredential.required_courses.all(),
        'current_date': current_date,
    }
    return render(request, 'learner/enroll_microcredential.html', context)


def microcredential_detail(request, slug):
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)

    # Ambil microcredential berdasarkan slug
    microcredential = get_object_or_404(MicroCredential, slug=slug)

    # Cek apakah pengguna sudah terdaftar
    is_enrolled = microcredential.enrollments.filter(user=request.user).exists()

    # Ambil semua kursus yang diperlukan
    required_courses = microcredential.required_courses.all()

    # Hitung status kelulusan dan skor untuk setiap kursus
    course_progress = []
    total_user_score = Decimal(0)
    total_max_score = Decimal(0)
    all_courses_completed = True

    for course in required_courses:
        assessments = Assessment.objects.filter(section__courses=course)
        course_score = Decimal(0)
        course_max_score = Decimal(0)
        course_completed = True

        for assessment in assessments:
            score_value = Decimal(0)
            total_questions = assessment.questions.count()
            if total_questions > 0:  # Multiple choice
                total_correct_answers = 0
                answers_exist = False
                for question in assessment.questions.all():
                    answers = QuestionAnswer.objects.filter(question=question, user=request.user)
                    if answers.exists():
                        answers_exist = True
                    total_correct_answers += answers.filter(choice__is_correct=True).count()
                if not answers_exist:
                    course_completed = False
                if total_questions > 0:
                    score_value = (Decimal(total_correct_answers) / Decimal(total_questions)) * Decimal(assessment.weight)
            else:  # AskOra
                askora_submissions = Submission.objects.filter(
                    askora__assessment=assessment,
                    user=request.user
                )
                if not askora_submissions.exists():
                    course_completed = False
                else:
                    latest_submission = askora_submissions.order_by('-submitted_at').first()
                    assessment_score = AssessmentScore.objects.filter(submission=latest_submission).first()
                    if assessment_score:
                        score_value = Decimal(assessment_score.final_score)

            score_value = min(score_value, Decimal(assessment.weight))
            course_score += score_value
            course_max_score += assessment.weight

        min_score = Decimal(microcredential.get_min_score(course))
        course_passed = course_completed and course_score >= min_score

        course_progress.append({
            'course': course,
            'user_score': course_score,
            'max_score': course_max_score,
            'min_score': min_score,
            'completed': course_completed,
            'passed': course_passed
        })

        total_user_score += course_score
        total_max_score += course_max_score
        if not course_passed:
            all_courses_completed = False

    microcredential_passed = all_courses_completed and total_user_score >= Decimal(microcredential.min_total_score)

    context = {
        'microcredential': microcredential,
        'course_progress': course_progress,
        'total_user_score': total_user_score,
        'total_max_score': total_max_score,
        'min_total_score': microcredential.min_total_score,
        'microcredential_passed': microcredential_passed,
        'current_date': timezone.now().date(),
        'is_enrolled': is_enrolled,  # Status enrollment
    }

    return render(request, 'learner/microcredential_detail.html', context)

@custom_ratelimit
def generate_microcredential_certificate(request, id):
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)

    # Pindahkan definisi base_url ke sini agar selalu tersedia
    base_url = request.build_absolute_uri('/')

    microcredential = get_object_or_404(MicroCredential, id=id)
    required_courses = microcredential.required_courses.all()

    total_user_score = Decimal(0)
    total_max_score = Decimal(0)
    all_courses_completed = True
    course_grades = []

    # Hitung nilai per course
    for course in required_courses:
        assessments = Assessment.objects.filter(section__courses=course)
        course_score = Decimal(0)
        course_max_score = Decimal(0)
        course_completed = True

        for assessment in assessments:
            score_value = Decimal(0)
            total_questions = assessment.questions.count()
            if total_questions > 0:
                total_correct_answers = 0
                answers_exist = False
                for question in assessment.questions.all():
                    answers = QuestionAnswer.objects.filter(question=question, user=request.user)
                    if answers.exists():
                        answers_exist = True
                    total_correct_answers += answers.filter(choice__is_correct=True).count()
                if not answers_exist:
                    course_completed = False
                score_value = (Decimal(total_correct_answers) / Decimal(total_questions)) * Decimal(assessment.weight)
            else:
                submissions = Submission.objects.filter(askora__assessment=assessment, user=request.user)
                if not submissions.exists():
                    course_completed = False
                else:
                    latest = submissions.order_by('-submitted_at').first()
                    score_obj = AssessmentScore.objects.filter(submission=latest).first()
                    if score_obj:
                        score_value = Decimal(score_obj.final_score)

            score_value = min(score_value, Decimal(assessment.weight))
            course_score += score_value
            course_max_score += assessment.weight

        min_score = Decimal(microcredential.get_min_score(course))
        if not (course_completed and course_score >= min_score):
            all_courses_completed = False

        grade_point = (course_score / course_max_score * 100) if course_max_score > 0 else Decimal(0)
        course_grades.append({
            'name': course.course_name,
            'grade_point': grade_point.quantize(Decimal('0.01')),
        })
        total_user_score += course_score
        total_max_score += course_max_score

    # Jika belum memenuhi syarat
    if not (all_courses_completed and total_user_score >= Decimal(microcredential.min_total_score)):
        return render(request, 'error_template.html', {'message': 'You have not yet completed this MicroCredential.'})

    # Periksa klaim di database
    existing_claim = MicroClaim.objects.filter(user=request.user, microcredential=microcredential).first()

    if existing_claim:
        certificate_uuid = existing_claim.certificate_uuid
        certificate_id = existing_claim.certificate_id
    else:
        # Generate certificate details for new claim
        certificate_uuid = str(uuid.uuid4())
        certificate_id = f"CERT-{microcredential.id}-{request.user.id}"
        MicroClaim.objects.create(
            user=request.user,
            microcredential=microcredential,
            certificate_id=certificate_id,
            certificate_uuid=certificate_uuid
        )

        # Send email notification with certificate and congratulatory message
        try:
            # Render email template
            email_context = {
                'user': request.user,
                'microcredential': microcredential,
                'certificate_id': certificate_id,
                'verification_url': f"{base_url.rstrip('/')}/verify-micro/{certificate_uuid}/",
                'congratulatory_message': f"Congratulations, {request.user.get_full_name() or request.user.username}! You have successfully earned the {microcredential.title} MicroCredential!",
            }
            email_subject = f"Congratulations! Your {microcredential.title} Certificate"
            email_body = render_to_string('email/certificate_email_micro.html', email_context)

            # Generate PDF for attachment
            html_content = render_to_string('learner/microcredential_certificate.html', {
                'microcredential': microcredential,
                'user': request.user,
                'current_date': timezone.now().date(),
                'certificate_id': certificate_id,
                'certificate_uuid': certificate_uuid,
                'verification_url': email_context['verification_url'],  # For verification button
                'course_grades': course_grades,
                'min_total_score': microcredential.min_total_score,
            })
            pdf = HTML(string=html_content, base_url=base_url).write_pdf()

            # Send email
            email = EmailMessage(
                subject=email_subject,
                body=email_body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[request.user.email],
            )
            email.attach(f"certificate_{microcredential.slug}.pdf", pdf, 'application/pdf')
            email.content_subtype = 'html'  # Set email to HTML format
            email.send()

            # Add success message for user
            messages.success(request, f"Congratulations! You have earned the {microcredential.title} certificate. A copy has been sent to your email.")
        except Exception as e:
            logger.error(f"Error sending email: {str(e)}")
            messages.error(request, f"Certificate generated, but there was an issue sending the email: {str(e)}")

    # Generate QR Code
    qr_dir = os.path.join(settings.MEDIA_ROOT, 'qrcodes')
    os.makedirs(qr_dir, exist_ok=True)
    qr_path = os.path.join(qr_dir, f'certificate_{certificate_uuid}.png')
    qr_code_url = f"{base_url.rstrip('/')}{settings.MEDIA_URL}qrcodes/certificate_{certificate_uuid}.png"

    if not os.path.exists(qr_path):
        verification_url = f"{base_url.rstrip('/')}/verify-micro/{certificate_uuid}/"
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(verification_url)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white")
        qr_img.save(qr_path)

    # Ambil gambar microcredential dan foto author
    microcredential_image_absolute_url = (
        f"{base_url.rstrip('/')}{microcredential.image.url}" if microcredential.image else None
    )
    author_photo_absolute_url = (
        f"{base_url.rstrip('/')}{microcredential.author.photo.url}"
        if hasattr(microcredential.author, 'photo') and microcredential.author.photo
        else None
    )

    context = {
        'microcredential': microcredential,
        'user': request.user,
        'current_date': timezone.now().date(),
        'microcredential_image_absolute_url': microcredential_image_absolute_url,
        'author_photo_absolute_url': author_photo_absolute_url,
        'course_grades': course_grades,
        'certificate_id': certificate_id,
        'min_total_score': microcredential.min_total_score,
        'qr_code_url': qr_code_url,
        'certificate_uuid': certificate_uuid,
        'verification_url': f"{base_url.rstrip('/')}/verify-micro/{certificate_uuid}/",  # For verification button
    }

    html_content = render_to_string('learner/microcredential_certificate.html', context)

    try:
        pdf = HTML(string=html_content, base_url=base_url).write_pdf()
    except Exception as e:
        logger.error(f"Error generating PDF: {str(e)}")
        return render(request, 'error_template.html', {'message': f'Error generating PDF: {str(e)}'})

    filename = f"certificate_{microcredential.slug}.pdf"
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

def verify_certificate_micro(request, certificate_id):
    # Ambil MicroClaim berdasarkan certificate_uuid yang diberikan
    certificate = get_object_or_404(MicroClaim, certificate_uuid=certificate_id)

    # Jika form disubmit dan email yang dimasukkan cocok
    if request.method == 'POST':
        input_email = request.POST.get('email')  # Ambil email dari form
        # Periksa apakah email yang dimasukkan sesuai dengan email pengguna yang mengklaim sertifikat
        if input_email == certificate.user.email:
            if not certificate.verified:
                certificate.verified = True
                certificate.save()
            message = "Certificate verified successfully."
        else:
            message = "The email you entered does not match. Verification failed."

        # Kirim pesan status ke template
        context = {
            'certificate': certificate,
            'message': message,
            'base_url': request.build_absolute_uri('/')
        }
        return render(request, 'courses/verify_certificate_micro.html', context)

    # Jika GET request (halaman pertama kali dimuat), tampilkan form tanpa perubahan
    context = {
        'certificate': certificate,
        'base_url': request.build_absolute_uri('/')
    }
    return render(request, 'courses/verify_certificate_micro.html', context)

def deletemic(request, pk):
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)
    if not request.user.is_superuser:
        # Jika pengguna bukan superuser, beri pesan dan arahkan ke halaman lain (misalnya halaman utama)
        messages.error(request, "You do not have permission to delete this microcredential.")
        return redirect('courses:microcredential-list')
    
    microcredential = get_object_or_404(MicroCredential, pk=pk)  # Get the MicroCredential by pk

    if request.method == 'POST':  # Confirm deletion after form submission
        microcredential.delete()
        return redirect('courses:microcredential-list')  # Redirect to the list after deletion

    return render(request, 'micro/delete_micro.html', {'microcredential': microcredential})



def editmic(request, pk):
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)
    microcredential = get_object_or_404(MicroCredential, pk=pk)  # Get the MicroCredential by pk

    if not request.user.is_superuser:
        # Jika pengguna bukan superuser, beri pesan dan arahkan ke halaman lain (misalnya halaman utama)
        messages.error(request, "You do not have permission to edit this microcredential.")
        return redirect('courses:microcredential-list')  

    if request.method == 'POST':
        form = MicroCredentialForm(request.POST, request.FILES, instance=microcredential)  # Prepopulate form with existing data
        if form.is_valid():
            form.save()
            return redirect('courses:microcredential-list')  # Redirect to the list after saving
    else:
        form = MicroCredentialForm(instance=microcredential)

    return render(request, 'micro/edit_micro.html', {'form': form, 'microcredential': microcredential})


class CourseAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return Course.objects.none()

        if not self.q:
            return Course.objects.none()

        q = self.q.strip()
        # Filter course yang status_course.status = 'published'
        qs = Course.objects.filter(
            Q(course_name__icontains=q) | Q(course_run__icontains=q),
            status_course__status='published'
        ).order_by('course_name', 'course_run')[:20]

        return qs

    def get_result_label(self, item):
        # Gabungkan course_name dan course_run agar jelas
        return f"{item.course_name} | {item.course_run}"

def addmic(request):
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)
    if not (request.user.is_superuser or getattr(request.user, 'is_curation', False)):
   

        # Jika pengguna bukan superuser, beri pesan dan arahkan ke halaman lain (misalnya halaman utama)
        messages.error(request, "You do not have permission to add this microcredential.")
        return redirect('courses:microcredential-list')
    
    if request.method == 'POST':
        form = MicroCredentialForm(request.POST, request.FILES)  # Handle file uploads for the image field
        if form.is_valid():
            # Automatically set the author field to the logged-in user
            form.instance.author = request.user
            form.save()
            return redirect('courses:microcredential-list')  # Redirect to the list of microcredentials
    else:
        form = MicroCredentialForm()

    return render(request, 'micro/add_micro.html', {'form': form})
    
def detailmic(request, pk):
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)
    # Fetch the MicroCredential object by its primary key
    microcredential = get_object_or_404(MicroCredential, pk=pk)

    return render(request, 'micro/detail_micro.html', {'microcredential': microcredential})


def listmic(request):
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)

    if not (request.user.is_staff or request.user.is_superuser or request.user.is_curation):
        messages.error(request, "You do not have permission to add this microcredential.")
        return redirect('authentication:dasbord')

    # Search logic
    search_query = request.GET.get('search', '')
    microcredentials = MicroCredential.objects.all()
    if search_query:
        microcredentials = microcredentials.filter(title__icontains=search_query)

    # Annotate dengan perhitungan yang akurat
    microcredentials = microcredentials.annotate(
        num_enrollments=Count('enrollments', distinct=True),
        avg_rating=Avg('reviews__rating'),
        num_courses=Count('required_courses', distinct=True),
        num_reviews=Count('reviews', distinct=True)
    ).order_by('-id')

    # Pagination
    paginator = Paginator(microcredentials, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'micro/list_micro.html', {
        'page_obj': page_obj,
        'search_query': search_query,
    })





def calculate_score_for_user_and_course(user, course):
    # Implementasikan logika untuk menghitung skor berdasarkan asesmen yang ada
    assessments = Assessment.objects.filter(course=course)
    total_score = 0
    total_max_score = 0

    for assessment in assessments:
        # Hitung skor untuk setiap asesmen berdasarkan jawaban yang benar
        total_correct_answers = 0
        total_questions = assessment.questions.count()

        for question in assessment.questions.all():
            answers = QuestionAnswer.objects.filter(question=question, user=user)
            correct_answers = answers.filter(choice__is_correct=True).count()
            total_correct_answers += correct_answers

        score_value = (Decimal(total_correct_answers) / Decimal(total_questions)) * Decimal(assessment.weight)
        total_score += score_value
        total_max_score += assessment.weight

    if total_max_score > 0:
        percentage = (total_score / total_max_score) * 100
        # Simpan skor ke dalam Score
        score = Score(user=user, course=course, score=total_score, total_questions=total_max_score, percentage=percentage)
        score.save()
        return score
    return None

    
#ora create question
@csrf_exempt
def create_askora(request, idcourse, idsection, idassessment):
    # 1️⃣ Pastikan user login
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)

    user = request.user
    course = None
    team_member = None  # inisialisasi

    # 2️⃣ Prioritas superuser / curation
    if user.is_superuser or user.is_curation:
        course = get_object_or_404(Course, id=idcourse)

    # 3️⃣ Partner / instructor hanya jika course belum ditemukan
    if not course and user.is_partner:
        course = get_object_or_404(Course, id=idcourse, org_partner__user_id=user.id)

    if not course and user.is_instructor:
        course = get_object_or_404(Course, id=idcourse, instructor__user_id=user.id)

    # 4️⃣ Cek CourseTeam sebagai fallback
    if not course:
        team_member = CourseTeam.objects.filter(course_id=idcourse, user=user).first()
        if team_member:
            course = team_member.course
        else:
            messages.error(request, "You do not have permission to view questions for this course.")
            return redirect('authentication:home')

    # Pastikan section milik course
    section = get_object_or_404(Section, id=idsection, courses=course)

    # Pastikan assessment milik section
    assessment = get_object_or_404(Assessment, id=idassessment, section=section)

    # Menangani form jika metode adalah POST
    if request.method == 'POST':
        # Membuat form untuk AskOra
        question_form = AskOraForm(request.POST)

        # Validasi form
        if question_form.is_valid():
            # Menyimpan AskOra (pertanyaan)
            askora = question_form.save(commit=False)
            askora.assessment = assessment  # Tentukan assessment yang sesuai
            askora.save()  # Simpan pertanyaan

            messages.success(request, "question open response assement successfully to add")
            return redirect('courses:view-question', idcourse=course.id, idsection=section.id, idassessment=assessment.id)  # Redirect kembali ke halaman yang sama

    else:
        # Menangani GET request
        question_form = AskOraForm()

    return render(request, 'courses/create_ora.html', {
        'course': course,
        'section': section,
        'assessment': assessment,
        'question_form': question_form,
    })


def edit_askora(request, idcourse, idaskora, idsection, idassessment):
    # 1️⃣ Pastikan user login
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)

    user = request.user
    course = None
    team_member = None  # inisialisasi

    # 2️⃣ Prioritas superuser / curation
    if user.is_superuser or user.is_curation:
        course = get_object_or_404(Course, id=idcourse)

    # 3️⃣ Partner / instructor hanya jika course belum ditemukan
    if not course and user.is_partner:
        course = get_object_or_404(Course, id=idcourse, org_partner__user_id=user.id)

    if not course and user.is_instructor:
        course = get_object_or_404(Course, id=idcourse, instructor__user_id=user.id)

    # 4️⃣ Cek CourseTeam sebagai fallback
    if not course:
        team_member = CourseTeam.objects.filter(course_id=idcourse, user=user).first()
        if team_member:
            course = team_member.course
        else:
            messages.error(request, "You do not have permission to view questions for this course.")
            return redirect('authentication:home')
        
    # Fetch the objects needed (course, section, assessment, and askora)
    course = get_object_or_404(Course, id=idcourse)
    section = get_object_or_404(Section, id=idsection)
    assessment = get_object_or_404(Assessment, id=idassessment, section=section)
    askora = get_object_or_404(AskOra, id=idaskora, assessment=assessment)

    # Handle the form submission (POST)
    if request.method == 'POST':
        form = AskOraForm(request.POST, instance=askora)  # pre-populate with the existing data
        if form.is_valid():
            form.save()  # Save the updated AskOra
            messages.success(request, "AskOra question updated successfully!")
            return redirect('courses:view-question', idcourse=course.id, idsection=section.id, idassessment=assessment.id)
    else:
        form = AskOraForm(instance=askora)  # Populate the form with existing data

    # Render the template with the form
    return render(request, 'courses/edit_askora.html', {
        'course': course,
        'section': section,
        'assessment': assessment,
        'askora': askora,
        'question_form': form  # Pass the form to the template
    })


def delete_askora(request, idcourse, idaskora, idsection, idassessment):
    # 1️⃣ Pastikan user login
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)

    user = request.user
    course = None
    team_member = None  # inisialisasi

    # 2️⃣ Prioritas superuser / curation
    if user.is_superuser or user.is_curation:
        course = get_object_or_404(Course, id=idcourse)

    # 3️⃣ Partner / instructor hanya jika course belum ditemukan
    if not course and user.is_partner:
        course = get_object_or_404(Course, id=idcourse, org_partner__user_id=user.id)

    if not course and user.is_instructor:
        course = get_object_or_404(Course, id=idcourse, instructor__user_id=user.id)

    # 4️⃣ Cek CourseTeam sebagai fallback
    if not course:
        team_member = CourseTeam.objects.filter(course_id=idcourse, user=user).first()
        if team_member:
            course = team_member.course
        else:
            messages.error(request, "You do not have permission to view questions for this course.")
            return redirect('authentication:home')
            
    # Fetch the relevant objects
    course = get_object_or_404(Course, id=idcourse)
    section = get_object_or_404(Section, id=idsection)
    assessment = get_object_or_404(Assessment, id=idassessment, section=section)
    askora = get_object_or_404(AskOra, id=idaskora, assessment=assessment)

    # Check if the user has permission to delete (optional, based on your logic)
    if request.user.is_authenticated:
        

        # Delete the AskOra object
        askora.delete()
        messages.error(request, "AskOra question deleted successfully.")

        # Redirect after deletion
        return redirect('courses:view-question', idcourse=course.id, idsection=section.id, idassessment=assessment.id)

    # Redirect if not authenticated
    return redirect("/login/?next=%s" % request.path)


#add coment matrial course
def is_bot(request):
    """
    Mengecek apakah permintaan berasal dari bot.
    Dengan melihat user-agent dan header lainnya.
    """
    user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
    if 'bot' in user_agent or 'crawler' in user_agent:
        return True  # Bot terdeteksi
    return False

def is_spam(request, user, content):
    """
    Memeriksa apakah komentar terdeteksi sebagai spam berdasarkan
    rate-limiting, bot detection dan blacklist keywords.
    """
    # 1. Cek Bot Detection
    if is_bot(request):
        return True  # Bot terdeteksi, komentar dianggap spam
    
    # 2. Cek Rate Limiting (Spam)
    time_limit = timedelta(seconds=30)  # Menentukan batas waktu antara komentar
    last_comment = Comment.objects.filter(user=user).order_by('-created_at').first()
    if last_comment and timezone.now() - last_comment.created_at < time_limit:
        return True  # Terlalu cepat mengirim komentar, dianggap spam
    
    # 3. Cek Kata Kunci yang Diblokir menggunakan metode model
    comment_instance = Comment(user=user, content=content)
    if comment_instance.contains_blacklisted_keywords():
        return True  # Mengandung kata terlarang, dianggap spam
    
    return False

def is_suspicious(request):
    """Check if the request is suspicious based on User-Agent or missing Referer."""
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    referer = request.META.get('HTTP_REFERER', '')
    
    # Bot detection (simple heuristic)
    if 'bot' in user_agent.lower() or not referer:
        return True
    return False

def add_comment(request, material_id):
    # Pastikan pengguna terautentikasi
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)

    # Ambil objek material berdasarkan material_id yang diberikan
    material = get_object_or_404(Material, id=material_id)

    # Memastikan bahwa material terhubung dengan kursus dan bagian yang valid
    if material.section:
        if material.section.courses:
            course_slug = material.section.courses.slug
        else:
            # Jika tidak ada kursus yang terhubung, lakukan redirect
            return redirect('courses:course_list')
    else:
        return redirect('courses:course_list')  # Redirect jika bagian tidak ditemukan

    if request.method == 'POST':
        if is_suspicious(request):
            messages.warning(request, "Suspicious activity detected. Comment not posted.")
            return redirect(reverse('courses:course_learn', kwargs={'username': request.user.username, 'slug': course_slug}) + f"?material_id={material.id}")
        
        content = request.POST.get('content')
        parent_id = request.POST.get('parent_id')  # Ambil parent_id dari form

        parent_comment = None
        if parent_id:
            parent_comment = get_object_or_404(Comment, id=parent_id)  # Cari komentar induk berdasarkan parent_id

        # Memeriksa apakah komentar adalah spam
        if is_spam(request, request.user, content):
            messages.warning(request, "Komentar Anda terdeteksi sebagai spam!")
            return redirect(reverse('courses:course_learn', kwargs={'username': request.user.username, 'slug': course_slug}) + f"?material_id={material.id}")

        # Buat komentar baru atau balasan jika tidak terdeteksi sebagai spam
        Comment.objects.create(
            user=request.user,
            content=content,
            material=material,
            parent=parent_comment  # Menghubungkan balasan dengan komentar induk jika ada
        )

        # Redirect kembali ke halaman kursus
        messages.success(request, "Komentar berhasil diposting!")
        return redirect(reverse('courses:course_learn', kwargs={'username': request.user.username, 'slug': course_slug}) + f"?material_id={material.id}")

    # Jika bukan POST, hanya redirect ke halaman material yang sama
    return redirect(reverse('courses:course_learn', kwargs={'username': request.user.username, 'slug': course_slug}) + f"?material_id={material.id}")

#add coment course


@require_POST  # Hanya izinkan metode POST
@ratelimit(key='ip', rate='10/m', block=True)  # Batasi 10 request per menit per IP
@csrf_protect  # Pastikan CSRF protection aktif
def add_comment_course(request, course_id):
    # Cek akses
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)
    
    try:
        course = get_object_or_404(Course, id=course_id)
    except Http404:
        messages.error(request, "Course not found.")
        return redirect('courses:course_list')

    if request.method == 'POST':
        # Mengecek apakah request mencurigakan (bot detection)
        if is_suspicious(request):
            messages.warning(request, "Suspicious activity detected. Comment not posted.")
            return redirect('courses:course_lms_detail', id=course.id, slug=course.slug)

        content = request.POST.get('content', '').strip()  # Ambil dan bersihkan input
        if not content:  # Validasi input kosong
            messages.error(request, "Comment cannot be empty.")
            return redirect('courses:course_lms_detail', id=course.id, slug=course.slug)

        parent_id = request.POST.get('parent_id')
        parent_comment = None

        # Menentukan apakah ini komentar balasan
        if parent_id:
            try:
                parent_comment = get_object_or_404(CourseComment, id=parent_id, course=course)
            except Http404:
                messages.error(request, "Invalid parent comment.")
                return redirect('courses:course_lms_detail', id=course.id, slug=course.slug)

        # Membuat objek komentar
        comment = CourseComment(
            user=request.user,
            content=content,
            course=course,
            parent=parent_comment
        )

        # Memeriksa apakah komentar mengandung kata kunci terlarang
        if comment.contains_blacklisted_keywords():
            messages.warning(request, "Your comment contains blacklisted content.")
            return redirect('courses:course_lms_detail', id=course.id, slug=course.slug)

        # Memeriksa apakah komentar adalah spam berdasarkan cooldown
        if comment.is_spam():
            messages.warning(request, "You are posting too frequently. Please wait a moment before posting again.")
            return redirect('courses:course_lms_detail', id=course.id, slug=course.slug)

        # Validasi dan simpan komentar
        try:
            comment.full_clean()  # Validasi model Django
            comment.save()
            messages.success(request, "Comment posted successfully!")
        except ValidationError as e:
            messages.error(request, f"Error posting comment: {e}")
            return redirect('courses:course_lms_detail', id=course.id, slug=course.slug)

        # Redirect aman dengan validasi referer
        referer = request.META.get('HTTP_REFERER')
        if referer and str(course_id) in referer:

            return redirect(referer)
        return redirect('courses:course_lms_detail', id=course.id, slug=course.slug)

    return redirect('courses:course_lms_detail', id=course.id, slug=course.slug)

# Fungsi contoh untuk is_suspicious (harus didefinisikan)
def is_suspicious(request):
    # Logika deteksi bot (misalnya, cek header, CAPTCHA, dll.)
    # Contoh sederhana: return True jika tidak ada user agent
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    return not user_agent or 'bot' in user_agent.lower()





def submit_assessment(request, assessment_id):
    if not request.user.is_authenticated:
        logger.info(f"Unauthenticated user attempted to submit assessment {assessment_id}")
        return redirect("/login/?next=%s" % request.path)

    # Ambil assessment berdasarkan ID
    assessment = get_object_or_404(Assessment, id=assessment_id)
    # Ambil course (pastikan hanya satu course terkait)
    try:
        course = assessment.section.courses.first()
        if not course:
            raise ValueError("No course associated with this assessment")
    except Exception as e:
        logger.error(f"Error retrieving course for assessment {assessment_id}: {str(e)}")
        messages.error(request, "Course not found for this assessment.")
        return redirect('authentication:dashbord')

    # Cek honeypot (bot jika terisi)
    honeypot = request.POST.get('honeypot')
    if honeypot:
        logger.warning(f"Spam detected for assessment {assessment_id} by user {request.user.username}")
        messages.error(request, "Spam terdeteksi. Pengiriman dibatalkan.")
        return redirect(reverse('courses:course_learn', kwargs={'username': request.user.username, 'slug': course.slug}) + f"?assessment_id={assessment.id}")

    # Periksa waktu pengisian form (cegah pengiriman terlalu cepat)
    start_time = request.POST.get('start_time')
    if start_time:
        try:
            start_time_obj = timezone.make_aware(datetime.strptime(start_time, '%Y-%m-%dT%H:%M:%S.%fZ'))
            elapsed_time = timezone.now() - start_time_obj
            if elapsed_time < timedelta(seconds=10):
                logger.warning(f"Submission too fast for assessment {assessment_id} by user {request.user.username}")
                messages.error(request, "Pengiriman terlalu cepat. Coba lagi setelah beberapa detik.")
                return redirect(reverse('courses:course_learn', kwargs={'username': request.user.username, 'slug': course.slug}) + f"?assessment_id={assessment.id}")
        except ValueError as e:
            logger.error(f"Invalid start time format for assessment {assessment_id}: {str(e)}")
            messages.error(request, "Format waktu mulai tidak valid.")
            return redirect(reverse('courses:course_learn', kwargs={'username': request.user.username, 'slug': course.slug}) + f"?assessment_id={assessment.id}")

    # Cek apakah user sudah pernah submit untuk assessment ini
    if Score.objects.filter(user=request.user, course=course, section=assessment.section, submitted=True).exists():
        logger.info(f"User {request.user.username} already submitted assessment {assessment_id}")
        messages.info(request, "Anda sudah mengirimkan jawaban untuk ujian ini.")
        return redirect(reverse('courses:course_learn', kwargs={'username': request.user.username, 'slug': course.slug}) + f"?assessment_id={assessment.id}")

    # Cek sesi dan waktu hanya jika durasi > 0
    session = AssessmentSession.objects.filter(user=request.user, assessment=assessment).first()
    if assessment.duration_in_minutes > 0:  # Hanya cek waktu jika bukan unlimited
        if not session:
            logger.warning(f"No session found for user {request.user.username}, assessment {assessment_id}")
            messages.error(request, "Sesi ujian tidak ditemukan.")
            return redirect(reverse('courses:course_learn', kwargs={'username': request.user.username, 'slug': course.slug}) + f"?assessment_id={assessment.id}")

        # Cek apakah waktu ujian sudah habis
        if timezone.now() > session.end_time:
            logger.warning(f"Assessment session expired for user {request.user.username}, assessment {assessment_id}")
            messages.warning(request, "Waktu ujian telah habis, Anda tidak dapat mengirimkan jawaban.")
            return redirect(reverse('courses:course_learn', kwargs={'username': request.user.username, 'slug': course.slug}) + f"?assessment_id={assessment.id}")

    if request.method == 'POST':
        correct_answers = 0
        total_questions = assessment.questions.count()

        # Proses setiap soal di assessment
        for question in assessment.questions.all():
            if QuestionAnswer.objects.filter(user=request.user, question=question).exists():
                logger.debug(f"Answer already exists for question {question.id} by user {request.user.username}")
                continue

            user_answer = request.POST.get(f"question_{question.id}")
            if user_answer:
                try:
                    choice = Choice.objects.get(id=user_answer)
                    QuestionAnswer.objects.create(user=request.user, question=question, choice=choice)
                    if choice.is_correct:
                        correct_answers += 1
                    logger.debug(f"Processed answer for question {question.id}: choice {choice.id}, correct={choice.is_correct}")
                except Choice.DoesNotExist:
                    logger.warning(f"Invalid choice ID {user_answer} for question {question.id} by user {request.user.username}")
                    continue

        # Menghitung nilai berdasarkan jawaban yang benar
        score_percentage = (correct_answers / total_questions) * 100 if total_questions > 0 else 0
        grade = calculate_grade(score_percentage, course)

        # Menyimpan hasil score ke model Score
        try:
            score = Score.objects.create(
                user=request.user,  # Gunakan objek User
                course=course,
                section=assessment.section,
                score=correct_answers,
                total_questions=total_questions,
                grade=grade,
                submitted=True
            )
            logger.info(f"Score saved for user {request.user.username}, assessment {assessment_id}, score {correct_answers}/{total_questions}")
        except Exception as e:
            logger.error(f"Error saving score for user {request.user.username}, assessment {assessment_id}: {str(e)}")
            messages.error(request, "Error submitting assessment. Please try again.")
            return redirect(reverse('courses:course_learn', kwargs={'username': request.user.username, 'slug': course.slug}) + f"?assessment_id={assessment.id}")

        # Perbarui progress user
        try:
            user_progress, created = CourseProgress.objects.get_or_create(user=request.user, course=course)
            user_progress.progress_percentage = score_percentage  # Asumsi field progress_percentage
            user_progress.save()
            logger.info(f"Updated progress for user {request.user.username}, course {course.id}, progress {score_percentage}%")
        except Exception as e:
            logger.error(f"Error updating progress for user {request.user.username}, course {course.id}: {str(e)}")

        # Hapus sesi asesmen jika ada
        if session:
            session.delete()
            logger.debug(f"Deleted session for user {request.user.username}, assessment {assessment_id}")

        messages.success(request, "Jawaban Anda telah berhasil disubmit. Terima kasih!")
        return redirect(reverse('courses:course_learn', kwargs={'username': request.user.username, 'slug': course.slug}) + f"?assessment_id={assessment.id}")

    logger.debug(f"Rendering submit_assessment.html for assessment {assessment_id}, user {request.user.username}")
    return render(request, 'submit_assessment.html', {'assessment': assessment})

def calculate_overall_pass_fail(user, course):
    
    # Ambil semua asesmen untuk kursus ini
    assessments = Assessment.objects.filter(section__courses=course)
    total_max_score = 0  # Total skor maksimal dari semua asesmen
    total_score = 0  # Total skor yang didapatkan dari pengguna
    all_passed = True  # Untuk melacak apakah semua asesmen lulus

    # Hitung skor untuk setiap asesmen
    for assessment in assessments:
        total_questions = assessment.questions.count()  # Jumlah soal pada asesmen ini
        total_correct_answers = 0  # Jumlah jawaban benar dari pengguna

        for question in assessment.questions.all():
            # Mengambil jawaban yang dipilih oleh pengguna untuk pertanyaan ini
            answers = QuestionAnswer.objects.filter(question=question, user=user)
            
            # Cek apakah jawaban yang dipilih benar
            correct_answers = answers.filter(choice__is_correct=True).count()  # Jawaban benar
            total_correct_answers += correct_answers

        # Tentukan skor berdasarkan jumlah jawaban benar dan jumlah soal
        score_value = 0
        if total_questions > 0:
            # Menghitung skor berdasarkan jawaban benar dan total soal
            score_value = (Decimal(total_correct_answers) / Decimal(total_questions)) * Decimal(assessment.weight)

        # Tentukan status kelulusan per asesmen
        passing_threshold = 60  # Ambang batas kelulusan per asesmen (misalnya 60%)
        if (score_value / assessment.weight) * 100 < passing_threshold:
            all_passed = False  # Jika ada asesmen yang tidak lulus, status keseluruhan adalah "Fail"

        total_max_score += assessment.weight  # Bobot maksimal
        total_score += score_value  # Skor yang didapat pengguna

    # Hitung persentase keseluruhan
    if total_max_score > 0:
        overall_percentage = (total_score / total_max_score) * 100
    else:
        overall_percentage = 0

    # Ambil ambang batas kelulusan dari GradeRange
    grade_range = GradeRange.objects.filter(course=course).first()  # Ambil grade range untuk kursus ini

    if grade_range:
        passing_threshold = grade_range.min_grade
    else:
        passing_threshold = 60  # Default jika tidak ada GradeRange

    status = "Pass" if all_passed and overall_percentage >= passing_threshold else "Fail"

    return total_score, overall_percentage, status






def calculate_total_score_and_status(user_id, course):
    # Ambil semua asesmen untuk kursus yang ditentukan
    assessments = Assessment.objects.filter(section__courses=course)
    print(f"Assessments for course {course.course_name}: {assessments.count()}")  # Debugging

    if not assessments.exists():
        return 0, 0, "No assessments available"  # Jika tidak ada asesmen

    total_score = 0
    total_weight = 0
    total_questions = 0  # Menyimpan total pertanyaan

    # Hitung total skor berdasarkan nilai yang diperoleh dari setiap asesmen
    for assessment in assessments:
        # Ambil nilai dari model Score yang relevan
        score_entry = Score.objects.filter(user=user_id, course=course, section=assessment.section).first()
        print(f"Score entry for assessment {assessment.name}: {score_entry}")  # Debugging
        if score_entry:
            total_score += score_entry.score  # Tambahkan skor yang diperoleh
            total_weight += assessment.weight  # Tambahkan bobot asesmen
            total_questions += score_entry.total_questions  # Tambahkan total pertanyaan

    if total_weight == 0 or total_questions == 0:
        return total_score, 0, "No assessments available"  # Jika tidak ada bobot atau pertanyaan

    overall_percentage = (total_score / total_questions) * 100  # Hitung persentase berdasarkan total pertanyaan

    # Ambil rentang nilai untuk kursus ini
    grade_ranges = GradeRange.objects.filter(course=course).order_by('min_grade')

    # Tentukan status kelulusan berdasarkan rentang nilai
    for grade_range in grade_ranges:
        if overall_percentage >= grade_range.min_grade and overall_percentage <= grade_range.max_grade:
            return total_score, overall_percentage, grade_range.name  # Mengembalikan total skor, persentase, dan nama grade

    # Jika tidak ada grade range yang sesuai, default ke "Fail"
    return total_score, overall_percentage, "Fail"

def calculate_grade(overall_percentage, course):
    # Ambil grade ranges untuk course ini
    grade_ranges = GradeRange.objects.filter(course=course).order_by('min_grade')

    # Memeriksa score_percentage dalam rentang grade yang ditemukan
    for grade_range in grade_ranges:
        # Periksa jika overall_percentage berada dalam rentang nilai yang valid
        if overall_percentage >= grade_range.min_grade and overall_percentage <= grade_range.max_grade:
            return grade_range.name  # Mengembalikan nama grade

    # Jika tidak ada grade range yang sesuai, default ke "Fail"
    return 'Fail'  # Default ke Fail jika tidak ada grade range yang sesuai

def start_assessment(request, assessment_id):
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)
    # Get the assessment using the provided ID
    assessment = get_object_or_404(Assessment, id=assessment_id)

    # Check if the user already has a session for this assessment
    existing_session = AssessmentSession.objects.filter(user=request.user, assessment=assessment).first()

    if not existing_session:
        # If the session doesn't exist, create a new one with start_time set to now
        session = AssessmentSession(
            user=request.user,
            assessment=assessment,
            start_time=timezone.now()  # Set the start time to now
        )
        # Calculate the end time by adding the duration of the assessment to the start time
        session.end_time = session.start_time + timedelta(minutes=assessment.duration_in_minutes)
        session.save()  # Save the session

    # Get the associated course slug and username for redirecting
    username = request.user.username
    slug = assessment.section.courses.slug

    # Redirect back to the course or assessment page after starting
    return redirect(reverse('courses:course_learn', kwargs={'username': request.user.username, 'slug': assessment.section.courses.slug}) + f"?assessment_id={assessment.id}")


def course_learn(request, username, slug):
    if not request.user.is_authenticated:
        logger.info(f"Unauthenticated user attempted to access course {slug}")
        return redirect("/login/?next=%s" % request.path)
    if request.user.is_authenticated:
        UserActivityLog.objects.create(user=request.user, activity_type='course_learn')

    course = get_object_or_404(Course, slug=slug)

    if request.user.username != username:
        logger.warning(f"User {request.user.username} attempted to access course {slug} with username {username}")
        return redirect('authentication:course_list')

    if not Enrollment.objects.filter(user=request.user, course=course).exists():
        logger.info(f"User {request.user.username} not enrolled in course {slug}")
        return redirect('courses:course_lms_detail', id=course.id, slug=course.slug)

    course_name = course.course_name

    sections = Section.objects.filter(courses=course).prefetch_related(
        Prefetch('materials', queryset=Material.objects.all()),
        Prefetch('assessments', queryset=Assessment.objects.all().prefetch_related(
            Prefetch('questions', queryset=Question.objects.all().prefetch_related(
                Prefetch('choices', queryset=Choice.objects.all())
            )),
            Prefetch('ask_oras', queryset=AskOra.objects.all()),
            Prefetch('lti_tools', queryset=LTIExternalTool1.objects.all())
        ))
    )

    combined_content = []
    for section in sections:
        for material in section.materials.all():
            combined_content.append(('material', material, section))
        for assessment in section.assessments.all():
            combined_content.append(('assessment', assessment, section))

    total_content = len(combined_content)

    material_id = request.GET.get('material_id')
    assessment_id = request.GET.get('assessment_id')

    current_content = None
    assessment_locked = False
    payment_required_url = None

    if not material_id and not assessment_id:
        current_content = combined_content[0] if combined_content else None
    elif material_id:
        material = get_object_or_404(Material, id=material_id)
        current_content = ('material', material, next((s for s in sections if material in s.materials.all()), None))
    elif assessment_id:
        assessment = get_object_or_404(Assessment, id=assessment_id)
        # Cek pembayaran untuk pay for exam
        if course.payment_model == 'pay for exam':
            payment = Payment.objects.filter(
                user=request.user,
                course=course,
                status='completed',
                payment_model='pay for exam'
            ).first()
            if not payment:
                assessment_locked = True
                payment_required_url = reverse('payments:process_payment', kwargs={'course_id': course.id, 'payment_type': 'exam'})
                messages.info(request, "This exam requires payment. You can add it to your cart or proceed to the next content.")
                logger.info(f"Payment required for exam in course {course.id} for user {request.user.username}")
                # Tetap atur current_content untuk assessment terkunci
                current_content = ('assessment', assessment, next((s for s in sections if assessment in s.assessments.all()), None))
            else:
                current_content = ('assessment', assessment, next((s for s in sections if assessment in s.assessments.all()), None))
        else:
            current_content = ('assessment', assessment, next((s for s in sections if assessment in s.assessments.all()), None))

    comments = None
    page_comments = []
    if current_content:
        if current_content[0] == 'material':
            material = current_content[1]
            comments = Comment.objects.filter(material=material, parent=None).order_by('-created_at')
        elif current_content[0] == 'assessment':
            section = current_content[2]
            comments = Comment.objects.filter(material__section=section, parent=None).order_by('-created_at')

        if comments:
            paginator = Paginator(comments, 5)
            page_number = request.GET.get('page')
            page_comments = paginator.get_page(page_number)

    material = None
    assessment = None

    if current_content:
        if current_content[0] == 'material':
            material = current_content[1]
        elif current_content[0] == 'assessment':
            assessment = current_content[1]

        LastAccessCourse.objects.update_or_create(
            user=request.user,
            course=course,
            defaults={
                'material': material,
                'assessment': assessment
            }
        )

    is_started = False
    is_expired = False
    remaining_time = 0

    if assessment:
        session = AssessmentSession.objects.filter(user=request.user, assessment=assessment).first()
        if session:
            is_started = True
            remaining_time = int((session.end_time - timezone.now()).total_seconds())
            if remaining_time <= 0:
                is_expired = True
                remaining_time = 0
        else:
            if assessment.duration_in_minutes == 0:
                is_started = True
                remaining_time = 0
            else:
                is_started = False

    current_index = -1
    if current_content:
        for i, content in enumerate(combined_content):
            if (content[0] == current_content[0] and 
                content[1].id == current_content[1].id and 
                content[2].id == current_content[2].id):
                current_index = i
                break
    elif assessment_locked and assessment_id:
        # Pastikan current_content untuk assessment terkunci
        assessment = get_object_or_404(Assessment, id=assessment_id)
        current_content = ('assessment', assessment, next((s for s in sections if assessment in s.assessments.all()), None))
        for i, content in enumerate(combined_content):
            if content[0] == 'assessment' and content[1].id == int(assessment_id):
                current_index = i
                break
        if current_index == -1:
            current_index = 0  # Fallback untuk mencegah error

    previous_content = combined_content[current_index - 1] if current_index > 0 else None
    next_content = combined_content[current_index + 1] if current_index < len(combined_content) - 1 and current_index != -1 else None
    is_last_content = next_content is None

    previous_url = None
    next_url = None
    if previous_content:
        previous_url = reverse('courses:course_learn', kwargs={'username': username, 'slug': slug}) + f"?{previous_content[0]}_id={previous_content[1].id}"
    if next_content:
        next_url = reverse('courses:course_learn', kwargs={'username': username, 'slug': slug}) + f"?{next_content[0]}_id={next_content[1].id}"

    if current_content:
        if current_content[0] == 'material':
            material = current_content[1]
            if not MaterialRead.objects.filter(user=request.user, material=material).exists():
                MaterialRead.objects.create(user=request.user, material=material)
        elif current_content[0] == 'assessment':
            assessment = current_content[1]
            if not AssessmentRead.objects.filter(user=request.user, assessment=assessment).exists():
                AssessmentRead.objects.create(user=request.user, assessment=assessment)

    user_progress, created = CourseProgress.objects.get_or_create(user=request.user, course=course)
    if current_content and (current_index + 1) > user_progress.progress_percentage / 100 * total_content:
        user_progress.progress_percentage = (current_index + 1) / total_content * 100
        user_progress.save()

    score = Score.objects.filter(user=request.user.username, course=course).order_by('-date').first()
    user_grade = 'Fail'
    if score:
        score_percentage = (score.score / score.total_questions) * 100
        user_grade = calculate_grade(score_percentage, course)

    assessments = Assessment.objects.filter(section__courses=course)
    assessment_scores = []
    total_max_score = 0
    total_score = 0
    all_assessments_submitted = True

    grade_range = GradeRange.objects.filter(course=course).all()
    if grade_range:
        pass_range = grade_range.filter(name='Pass').first()
        passing_threshold = pass_range.min_grade
        max_grade = pass_range.max_grade
    else:
        return render(request, 'error_template.html', {'error': 'Grade range not found for this course.'})

    for assessment in assessments:
        score_value = Decimal(0)
        total_correct_answers = 0
        total_questions = assessment.questions.count()
        if total_questions > 0:
            answers_exist = False
            for question in assessment.questions.all():
                answers = QuestionAnswer.objects.filter(question=question, user=request.user)
                if answers.exists():
                    answers_exist = True
                total_correct_answers += answers.filter(choice__is_correct=True).count()
            if not answers_exist:
                all_assessments_submitted = False
            if total_questions > 0:
                score_value = (Decimal(total_correct_answers) / Decimal(total_questions)) * Decimal(assessment.weight)
        else:
            askora_submissions = Submission.objects.filter(askora__assessment=assessment, user=request.user)
            if not askora_submissions.exists():
                all_assessments_submitted = False
            else:
                latest_submission = askora_submissions.order_by('-submitted_at').first()
                assessment_score = AssessmentScore.objects.filter(submission=latest_submission).first()
                if assessment_score:
                    score_value = Decimal(assessment_score.final_score)

        score_value = min(score_value, Decimal(assessment.weight))
        assessment_scores.append({
            'assessment': assessment,
            'score': score_value,
            'weight': assessment.weight
        })
        total_max_score += assessment.weight
        total_score += score_value

    total_score = min(total_score, total_max_score)
    overall_percentage = (total_score / total_max_score) * 100 if total_max_score > 0 else 0
    passing_criteria_met = overall_percentage >= passing_threshold
    status = "Pass" if all_assessments_submitted and passing_criteria_met else "Fail"

    assessment_results = [
        {'name': score['assessment'].name, 'max_score': score['weight'], 'score': score['score']}
        for score in assessment_scores
    ]
    assessment_results.append({'name': 'Total', 'max_score': total_max_score, 'score': total_score})

    askoras = AskOra.objects.filter(assessment__section__courses=course)
    try:
        submissions = Submission.objects.filter(
            askora__in=AskOra.objects.filter(assessment__section__courses=course),
            user=request.user
        )
    except Exception as e:
        submissions = []

    questions = Question.objects.filter(assessment__in=assessments)
    answered_questions = {q.id: QuestionAnswer.objects.filter(user=request.user, question=q).first() for q in questions}

    peer_submissions = Submission.objects.filter(
        askora__in=AskOra.objects.filter(assessment__section__courses=course)
    ).exclude(user=request.user).prefetch_related('peer_reviews')

    peer_submissions_data = []
    for submission in peer_submissions:
        has_reviewed = submission.peer_reviews.filter(reviewer=request.user).exists()
        assessment_score, created = AssessmentScore.objects.get_or_create(submission=submission)
        peer_reviews = submission.peer_reviews.all()
        assessment_weight = float(submission.askora.assessment.weight)
        max_peer_score = 5.0

        user_has_submitted = Submission.objects.filter(
            askora=submission.askora,
            user=request.user
        ).exists()

        if peer_reviews:
            total_score_reviews = sum(float(review.score) * float(review.weight) for review in peer_reviews)
            peer_review_count = peer_reviews.count()
            avg_peer_score = total_score_reviews / peer_review_count
            scaled_peer_score = (avg_peer_score / max_peer_score) * assessment_weight
            participant_score = assessment_weight
            final_score = (participant_score * 0.5) + (scaled_peer_score * 0.5)
        else:
            final_score = assessment_weight * 0.5

        try:
            assessment_score.final_score = final_score
            assessment_score.save()
        except Exception as e:
            final_score = float(assessment_score.final_score or 0.0)

        peer_submissions_data.append({
            'submission': submission,
            'has_reviewed': has_reviewed,
            'final_score': final_score,
            'can_review': user_has_submitted
        })

    lti_tools = LTIExternalTool1.objects.filter(assessment__section__courses=course)
    context = {
        'course': course,
        'course_name': course_name,
        'sections': sections,
        'current_content': current_content,
        'previous_url': previous_url,
        'next_url': next_url,
        'course_progress': user_progress.progress_percentage,
        'user_grade': user_grade,
        'assessment_results': assessment_results,
        'total_score': total_score,
        'overall_percentage': overall_percentage,
        'total_weight': total_max_score,
        'status': status,
        'is_started': is_started,
        'is_expired': is_expired,
        'remaining_time': remaining_time,
        'max_grade': max_grade,
        'passing_threshold': passing_threshold,
        'is_last_content': is_last_content,
        'comments': page_comments,
        'material': current_content[1] if current_content and current_content[0] == 'material' else None,
        'assessment': current_content[1] if current_content and current_content[0] == 'assessment' else None,
        'answered_questions': answered_questions,
        'askoras': askoras,
        'submissions': submissions,
        'lti_tools': lti_tools,
        'peer_submissions_data': peer_submissions_data,
        'assessment_locked': assessment_locked,
        'payment_required_url': payment_required_url,
    }

    return render(request, 'learner/course_learn.html', context)

def submit_peer_review(request, submission_id):
    submission = get_object_or_404(Submission, id=submission_id)
    if request.method == 'POST':
        if not PeerReview.objects.filter(submission=submission, reviewer=request.user).exists():
            try:
                peer_review = PeerReview(
                    submission=submission,
                    reviewer=request.user,
                    score=int(request.POST.get('score')),
                    comment=request.POST.get('comment'),
                    weight=1.0
                )
                peer_review.save()
                #print(f"Peer review saved for Submission {submission.id} by {request.user.username}")

                # Hitung skor akhir secara manual
                assessment_score, created = AssessmentScore.objects.get_or_create(submission=submission)
                peer_reviews = submission.peer_reviews.all()
                if peer_reviews:
                    total_score = sum(float(review.score) * float(review.weight) for review in peer_reviews)
                    peer_review_count = peer_reviews.count()
                    avg_peer_score = total_score / peer_review_count
                    participant_score = 5.0
                    assessment_score.final_score = (participant_score * 0.5) + (avg_peer_score * 0.5)
                else:
                    assessment_score.final_score = 2.5
                assessment_score.save()
                print(f"Final score updated: {assessment_score.final_score}")
            except Exception as e:
                print(f"Error in peer review process for Submission {submission.id}: {e}")
    
    assessment = submission.askora.assessment
    course_slug = assessment.section.courses.slug
    return redirect(
        reverse('courses:course_learn', kwargs={'username': request.user.username, 'slug': course_slug}) + 
        f"?assessment_id={assessment.id}"
    )

def submit_answer(request, askora_id):
    askora = get_object_or_404(AskOra, id=askora_id)
    if request.method == 'POST' and askora.is_responsive():
        try:
            submission = Submission(
                askora=askora,
                user=request.user,
                answer_text=request.POST.get('answer_text'),
                answer_file=request.FILES.get('answer_file')
            )
            submission.save()
            print(f"Submission saved for AskOra {askora.id}")
        except Exception as e:
            print(f"Error saving submission: {e}")
    
    # Redirect ke course_learn dengan assessment_id
    assessment = askora.assessment
    course_slug = assessment.section.courses.slug  # Ganti .first() dengan akses langsung
    return redirect(
        reverse('courses:course_learn', kwargs={'username': request.user.username, 'slug': course_slug}) + 
        f"?assessment_id={assessment.id}"
    )


# Setup logging untuk debugging
logger = logging.getLogger(__name__)

def build_verifiable_credential(certificate, passing_threshold):
    return {
        "@context": ["https://www.w3.org/2018/credentials/v1"],
        "id": f"urn:uuid:{certificate.certificate_id}",
        "type": ["VerifiableCredential", "CourseCertificate"],
        "issuer": {
            "id": "https://ini.icei.ac.id",
            "name": "LMSKu"
        },
        "issuanceDate": certificate.issue_date.isoformat() + "T00:00:00Z",
        "credentialSubject": {
            "id": f"did:user:{certificate.user.id}",
            "name": certificate.user.get_full_name(),
            "email": certificate.user.email,
            "course": {
                "id": str(certificate.course.id),
                "name": certificate.course.course_name,
            },
            "score": str(certificate.total_score),
            "status": "Pass" if certificate.total_score >= passing_threshold else "Fail"
        }
    }

@custom_ratelimit
def generate_certificate(request, course_id):
    if not request.user.is_authenticated:
        logger.info(f"Unauthenticated user attempted to claim certificate for course {course_id}")
        return redirect("/login/?next=%s" % request.path)

    course = get_object_or_404(Course, id=course_id)

    # === CEK ENROLLMENT ===
    if not Enrollment.objects.filter(user=request.user, course=course).exists():
        logger.warning(f"User {request.user.username} not enrolled in course {course.id}")
        messages.error(request, "You are not enrolled in this course.")
        return redirect('authentication:dashbord')

    # === CEK PEMBAYARAN (JIKA MODELNYA PAY-FOR-CERTIFICATE) ===
    if course.payment_model.code == 'pay_only_certificate':
        payment = Payment.objects.filter(
            user=request.user,
            course=course,
            status='completed',
            payment_model='pay_only_certificate'
        ).first()
        if not payment:
            logger.info(f"Payment required for certificate in course {course.id} for user {request.user.username}")
            messages.info(request, "This certificate requires payment.")
            return redirect(reverse('payments:process_payment', kwargs={'course_id': course.id, 'payment_type': 'certificate'}))

    # === HITUNG NILAI ASESMEN ===
    assessments = Assessment.objects.filter(section__courses=course)
    assessment_scores, total_max_score, total_score = [], 0, 0
    all_assessments_submitted = True

    grade_range = GradeRange.objects.filter(course=course)
    if not grade_range.exists():
        logger.error(f"No grade range found for course {course.id}")
        messages.error(request, "Passing grade not found for this course.")
        return redirect('authentication:dashbord')

    passing_range = grade_range.filter(name='Pass').first()
    if not passing_range:
        logger.error(f"'Pass' grade range not found for course {course.id}")
        messages.error(request, "No 'Pass' grade range defined for this course.")
        return redirect('authentication:dashbord')

    passing_threshold = passing_range.min_grade
    max_grade = passing_range.max_grade

    for assessment in assessments:
        score_value = Decimal(0)
        weight = Decimal(assessment.weight or 1)

        # ==============================
        # 1. LTI RESULT
        # ==============================
        lti_result = LTIResult.objects.filter(user=request.user, assessment=assessment).first()
        if lti_result and lti_result.score is not None:
            lti_score = Decimal(lti_result.score)

            # Normalisasi jika 0–100
            if lti_score > 1:
                logger.warning(f"[LTI] Score {lti_score} >1. Normalizing to {lti_score / 100}")
                lti_score = lti_score / Decimal(100)

            score_value = lti_score * weight
            assessment_scores.append({
                'assessment': assessment,
                'score': score_value,
                'weight': weight
            })
            total_score += score_value
            total_max_score += weight
            continue  # lanjut ke assessment berikutnya


        # ==============================
        # 2. VIDEO QUIZ (QuizResult)
        # ==============================
        video_quiz = QuizResult.objects.filter(
            user=request.user,
            assessment=assessment
        ).order_by("-created_at").first()

        if video_quiz:
            if video_quiz.total_questions > 0:
                vr_score = Decimal(video_quiz.score) / Decimal(video_quiz.total_questions)
                score_value = vr_score * weight
            else:
                score_value = Decimal(0)

            assessment_scores.append({
                'assessment': assessment,
                'score': score_value,
                'weight': weight
            })
            total_score += score_value
            total_max_score += weight
            continue


        # ==============================
        # 3. MCQ / MULTIPLE CHOICE
        # ==============================
        total_questions = assessment.questions.count()
        if total_questions > 0:
            answers_exist = False
            correct_total = 0

            for q in assessment.questions.all():
                answers = QuestionAnswer.objects.filter(question=q, user=request.user)
                if answers.exists():
                    answers_exist = True
                correct_total += answers.filter(choice__is_correct=True).count()

            if not answers_exist:
                all_assessments_submitted = False

            score_value = (
                Decimal(correct_total) / Decimal(total_questions) * weight
                if total_questions > 0 else Decimal(0)
            )

            assessment_scores.append({
                'assessment': assessment,
                'score': score_value,
                'weight': weight
            })
            total_score += score_value
            total_max_score += weight
            continue


        # ==============================
        # 4. ASKORA / ESSAY
        # ==============================
        submission = Submission.objects.filter(
            askora__assessment=assessment,
            user=request.user
        ).order_by('-submitted_at').first()

        if submission:
            score_obj = AssessmentScore.objects.filter(submission=submission).first()
            if score_obj:
                score_value = Decimal(score_obj.final_score)
            else:
                all_assessments_submitted = False
        else:
            all_assessments_submitted = False

        # ==============================
        # FINALIZE SCORE
        # ==============================
        score_value = min(score_value, weight)

        assessment_scores.append({
            'assessment': assessment,
            'score': score_value,
            'weight': weight
        })

        total_score += score_value
        total_max_score += weight


    total_score = min(total_score, total_max_score)
    overall_percentage = (total_score / total_max_score) * 100 if total_max_score > 0 else 0
    passing_criteria_met = overall_percentage >= passing_threshold
    status = "Pass" if all_assessments_submitted and passing_criteria_met else "Fail"

    # === PREPARE DATA UNTUK TEMPLATE ===
    assessment_results = [
        {'name': score['assessment'].name, 'max_score': score['weight'], 'score': score['score']}
        for score in assessment_scores
    ]
    assessment_results.append({'name': 'Total', 'max_score': total_max_score, 'score': total_score})

    base_url = request.build_absolute_uri('/')
    partner_logo_url = None
    try:
        if course.org_partner and course.org_partner.logo:
            partner_logo_url = base_url.rstrip('/') + course.org_partner.logo.url
            logger.info(f"Partner logo found: {partner_logo_url}")
        else:
            logger.warning(f"No logo found for partner {course.org_partner}")
    except Exception as e:
        logger.error(f"Error fetching partner logo: {str(e)}")

    # === CEK JIKA SERTIFIKAT SUDAH ADA ===
    existing_certificate = Certificate.objects.filter(user=request.user, course=course).first()
    if existing_certificate:
        logger.info(f"Certificate {existing_certificate.certificate_id} already exists for user {request.user.username}")

        # CEK/GENERATE QR CODE
        existing_qr_path = os.path.join(settings.MEDIA_ROOT, 'qrcodes', f'certificate_{existing_certificate.certificate_id}.png')
        if not os.path.exists(existing_qr_path):
            verification_url = f"{base_url.rstrip('/')}/verify/{existing_certificate.certificate_id}/"
            qr = qrcode.QRCode(version=1, box_size=10, border=4)
            qr.add_data(verification_url)
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="black", back_color="white")
            os.makedirs(os.path.dirname(existing_qr_path), exist_ok=True)
            qr_img.save(existing_qr_path)
            logger.info(f"QR code regenerated for existing certificate: {existing_qr_path}")

        qr_url = request.build_absolute_uri(settings.MEDIA_URL + f'qrcodes/certificate_{existing_certificate.certificate_id}.png')

        # === REGENERATE VC JSON UNTUK SERTIFIKAT LAMA ===
        try:
            vc = build_verifiable_credential(existing_certificate, passing_threshold)
            vc_path = os.path.join(settings.MEDIA_ROOT, 'credentials', f'vc_{existing_certificate.certificate_id}.json')
            os.makedirs(os.path.dirname(vc_path), exist_ok=True)
            with open(vc_path, 'w', encoding='utf-8') as f:
                json.dump(vc, f, ensure_ascii=False, indent=4)
            logger.info(f"VC JSON regenerated for existing certificate: {vc_path}")
        except Exception as e:
            logger.error(f"Error generating VC for existing certificate {existing_certificate.certificate_id}: {str(e)}")

        # === GENERATE PDF ===
        html_content = render_to_string('learner/certificate_template.html', {
            'passing_threshold': passing_threshold,
            'status': status,
            'course': course,
            'total_score': total_score,
            'user': request.user,
            'issue_date': existing_certificate.issue_date.strftime('%Y-%m-%d'),
            'assessment_results': assessment_results,
            'partner_logo_url': partner_logo_url,
            'qr_code_url': qr_url,
            'base_url': base_url,
        })

        try:
            pdf = HTML(string=html_content, base_url=base_url).write_pdf()
            response = HttpResponse(pdf, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="certificate_{course.slug}.pdf"'
            return response
        except Exception as e:
            logger.error(f"Error re-generating PDF: {str(e)}")
            messages.error(request, "Error retrieving certificate.")
            return redirect('authentication:dashbord')

    # === JIKA BELUM ADA — BUAT SERTIFIKAT BARU ===
    certificate_id = uuid.uuid4()
    verification_url = f"{base_url.rstrip('/')}/verify/{certificate_id}/"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(verification_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    qr_path = os.path.join(settings.MEDIA_ROOT, 'qrcodes', f'certificate_{certificate_id}.png')
    os.makedirs(os.path.dirname(qr_path), exist_ok=True)
    qr_img.save(qr_path)
    qr_url = request.build_absolute_uri(settings.MEDIA_URL + f'qrcodes/certificate_{certificate_id}.png')
    logger.info(f"QR code generated: {qr_url}")

    try:
        certificate = Certificate.objects.create(
            certificate_id=certificate_id,
            user=request.user,
            course=course,
            issue_date=timezone.now().date(),
            total_score=total_score,
            partner=course.org_partner
        )

        # === Generate VC JSON untuk sertifikat baru ===
        vc = build_verifiable_credential(certificate, passing_threshold)
        vc_path = os.path.join(settings.MEDIA_ROOT, 'credentials', f'vc_{certificate.certificate_id}.json')
        os.makedirs(os.path.dirname(vc_path), exist_ok=True)
        with open(vc_path, 'w', encoding='utf-8') as f:
            json.dump(vc, f, ensure_ascii=False, indent=4)
        logger.info(f"VC JSON generated for new certificate: {vc_path}")

        logger.info(f"Certificate {certificate_id} saved for user {request.user.username}")

    except Exception as e:
        logger.error(f"Error saving certificate or generating VC: {str(e)}")
        messages.error(request, "Error generating certificate.")
        return redirect('authentication:dashbord')

    # === GENERATE PDF DAN KIRIM EMAIL ===
    html_content = render_to_string('learner/certificate_template.html', {
        'passing_threshold': passing_threshold,
        'status': status,
        'course': course,
        'total_score': total_score,
        'user': request.user,
        'issue_date': timezone.now().strftime('%Y-%m-%d'),
        'assessment_results': assessment_results,
        'partner_logo_url': partner_logo_url,
        'qr_code_url': qr_url,
        'base_url': base_url,
    })

    try:
        pdf = HTML(string=html_content, base_url=base_url).write_pdf()
        
        # Kirim email notifikasi
        email_subject = f"Your LMSKu Certificate for {course.course_name}"
        email_html = render_to_string('email/certificate_notification.html', {
            'user': request.user,
            'course': course,
            'issue_date': timezone.now().strftime('%Y-%m-%d'),
            'total_score': total_score,
            'max_score': total_max_score,
            'certificate_id': certificate_id,
            'verification_url': verification_url,
        })
        email_text = render_to_string('email/certificate_notification.txt', {
            'user': request.user,
            'course': course,
            'issue_date': timezone.now().strftime('%Y-%m-%d'),
            'total_score': total_score,
            'max_score': total_max_score,
            'certificate_id': certificate_id,
            'verification_url': verification_url,
        })

        email = EmailMessage(
            subject=email_subject,
            body=email_html,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[request.user.email],
        )
        email.content_subtype = 'html'
        email.attach(f'certificate_{course.slug}.pdf', pdf, 'application/pdf')

        # Attach VC JSON
        try:
            email.attach(
                f'vc_certificate_{course.slug}.json',
                json.dumps(vc, ensure_ascii=False, indent=4),
                'application/json'
            )
            logger.info(f"VC JSON attached to email for certificate {certificate.certificate_id}")
        except Exception as e:
            logger.error(f"Error attaching VC JSON to email: {str(e)}")

        email.send(fail_silently=False)
        logger.info(f"Certificate notification email sent to {request.user.email}")

    except Exception as e:
        logger.error(f"Error generating PDF or sending email: {str(e)}")
        messages.error(request, "Error generating certificate or sending notification.")
        return redirect('authentication:dashbord')

    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="certificate_{course.slug}.pdf"'
    return response




def verify_certificate(request, certificate_id):
    certificate = get_object_or_404(Certificate, certificate_id=certificate_id)
    context = {
        'certificate': certificate,
        'base_url': request.build_absolute_uri('/')
    }
    return render(request, 'courses/verify_certificate.html', context)

#re-runs course
def course_reruns(request, id):
    """ View for creating a re-run of a course, along with related data like CoursePrice, Assessments, Materials, and GradeRange """

    course = get_object_or_404(Course, id=id)

    # Check if the course status is "archive"
    try:
        archive_status = CourseStatus.objects.get(status='archived')
        draft_status = CourseStatus.objects.get(status='draft')
    except CourseStatus.DoesNotExist:
        messages.error(request, "The 'archived' or 'draft' status is missing. Please check your data.")
        return redirect('courses:studio', id=course.id)

    # Check if the course status is 'archived'
    if course.status_course != archive_status:
        messages.warning(request, "Only archived courses can be re-run.")
        return redirect('courses:studio', id=course.id)

    # Check if the user has permission to create a re-run for this course
    if not (request.user.is_superuser or request.user == course.org_partner.user or request.user == course.instructor.user):
        messages.error(request, "You do not have permission to create a re-run for this course.")
        return redirect('courses:studio', id=course.id)

    # If the request method is POST, the user is submitting the form to create the re-run
    if request.method == 'POST':
        form = CourseRerunForm(request.POST)

        if form.is_valid():
            today = timezone.now().date()

            # Check if a re-run already exists for today
            existing_rerun = Course.objects.filter(
                course_name=course.course_name,
                course_run__startswith="Run",
                created_at__date=today
            ).exists()

            if existing_rerun:
                messages.error(request, "A re-run for this course has already been created today.")
                return redirect('courses:studio', id=course.id)

            # Process the creation of the new course re-run
            new_course = form.save(commit=False)
            new_course.course_name = form.cleaned_data['course_name_hidden']
            new_course.org_partner = form.cleaned_data['org_partner_hidden']
            new_course.status_course = draft_status
            new_course.slug = f"{slugify(new_course.course_name)}-{new_course.course_run.lower().replace(' ', '-')}"
            new_course.created_at = timezone.now()
            new_course.author = request.user
            
            # Set fields from the original course
            new_course.instructor = course.instructor
            new_course.language = course.language
            new_course.image = course.image
            new_course.link_video = course.link_video
            new_course.description = course.description
            new_course.sort_description = course.sort_description
            new_course.hour = course.hour
            new_course.save()

            # Copy the CoursePrice related to the original course
            for course_price in course.prices.all():
                CoursePrice.objects.create(
                    course=new_course,
                    price_type=course_price.price_type,
                    partner=course_price.partner,
                    partner_price=course_price.partner_price,
                    discount_percent=course_price.discount_percent,
                    discount_amount=course_price.discount_amount,
                    ice_share_rate=course_price.ice_share_rate,
                    admin_fee=course_price.admin_fee,
                    sub_total=course_price.sub_total,
                    portal_price=course_price.portal_price,
                    normal_price=course_price.normal_price,
                    calculate_admin_price=course_price.calculate_admin_price,
                    platform_fee=course_price.platform_fee,
                    voucher=course_price.voucher,
                    user_payment=course_price.user_payment,
                    partner_earning=course_price.partner_earning,
                    ice_earning=course_price.ice_earning
                )

            # Copy GradeRange related to the original course
            grade_range_mapping = {}
            for grade_range in course.grade_ranges.all():
                new_grade_range = GradeRange.objects.create(
                    course=new_course,
                    name=grade_range.name,
                    min_grade=grade_range.min_grade,
                    max_grade=grade_range.max_grade,
                    created_at=grade_range.created_at
                )
                grade_range_mapping[grade_range.id] = new_grade_range

            # Copy the Sections and related Materials, Assessments, and AskOra
            for section in course.sections.all():
                # Check if the new section already exists for this course (avoid duplicates)
                existing_section = Section.objects.filter(
                    title=section.title,
                    courses=new_course,
                    parent__title=section.parent.title if section.parent else None
                ).first()

                if not existing_section:
                    parent_section = None
                    if section.parent:
                        parent_section = Section.objects.filter(
                            title=section.parent.title,
                            courses=new_course
                        ).first()

                    # Create the new section
                    new_section = Section.objects.create(
                        parent=parent_section,
                        title=section.title,
                        courses=new_course,
                        order=section.order  # Copy the order field
                    )

                    # Copy the materials associated with the section
                    for material in section.materials.all():
                        Material.objects.create(
                            section=new_section,
                            title=material.title,
                            description=material.description,
                            created_at=material.created_at
                        )

                    # Copy the assessments associated with the section
                    for assessment in section.assessments.all():
                        new_assessment = Assessment.objects.create(
                            name=assessment.name,
                            section=new_section,
                            weight=assessment.weight,
                            description=assessment.description,
                            flag=assessment.flag,
                            duration_in_minutes=assessment.duration_in_minutes,
                            grade_range=grade_range_mapping.get(assessment.grade_range.id) if assessment.grade_range else None,
                            created_at=assessment.created_at
                        )

                        # Copy the questions associated with the assessment
                        for question in assessment.questions.all():
                            new_question = Question.objects.create(
                                assessment=new_assessment,
                                text=question.text,
                                created_at=question.created_at
                            )

                            # Copy the choices associated with the question
                            for choice in question.choices.all():
                                Choice.objects.create(
                                    question=new_question,
                                    text=choice.text,
                                    is_correct=choice.is_correct
                                )

                        # Copy the AskOra associated with the assessment
                        for ask_ora in assessment.ask_oras.all():
                            AskOra.objects.create(
                                assessment=new_assessment,
                                title=ask_ora.title,
                                question_text=ask_ora.question_text,
                                response_deadline=ask_ora.response_deadline,
                                created_at=ask_ora.created_at
                            )

            messages.success(request, f"Re-run of course '{new_course.course_name}' created successfully!")
            return redirect('courses:studio', id=new_course.id)

        else:
            messages.error(request, "There was an error with the form. Please correct the errors below.")
            print(form.errors)  # Debugging form errors

    else:
        form = CourseRerunForm(instance=course)
        form.fields['course_name_hidden'].initial = course.course_name
        form.fields['org_partner_hidden'].initial = course.org_partner

    return render(request, 'courses/course_reruns.html', {'form': form, 'course': course})


def add_course_price(request, id):
    if not request.user.is_authenticated:
        return redirect(f"/login/?next={request.path}")

    if not (hasattr(request.user, 'is_partner') and request.user.is_partner):
        messages.error(request, "Anda tidak memiliki izin untuk menambahkan harga ke kursus ini.")
        return redirect('courses:studio', id=id)

    course = get_object_or_404(Course, id=id, org_partner__user_id=request.user.id)
    partner = request.user.partner_user

    existing_price = CoursePrice.objects.filter(course=course, partner=partner).first()

    if request.method == 'POST':
        form = CoursePriceForm(request.POST, user=request.user, instance=existing_price)

        if form.is_valid():
            course_price = form.save(commit=False)
            course_price.course = course
            course_price.partner = partner
            course_price.save()
            messages.success(request, "✅ Harga kursus berhasil disimpan!")
            # Redirect ke detail kursus atau halaman lain yang sesuai
            return redirect(reverse('courses:studio', args=[course.id]))
        else:
            messages.error(request, "Terdapat kesalahan pada form, silakan cek kembali.")
    else:
        form = CoursePriceForm(user=request.user, instance=existing_price)

    return render(request, 'courses/course_price_form.html', {
        'form': form,
        'course': course,
    })

#instrcutor profile

# @cache_page(60 * 5)  # Cache for 5 minutes
# @ratelimit(key='ip', rate='30/h', block=True)  # Rate limit 30 requests per hour per IP
def instructor_profile(request, username):
    try:
        # Get instructor by username
        instructor = get_object_or_404(Instructor, user__username=username)

        # Ensure that the instructor has a provider (Partner) with a slug in the related Universiti
        if not instructor.provider or not hasattr(instructor.provider.name, 'slug'):
            partner_slug = None
        else:
            partner_slug = instructor.provider.name.slug  # Access slug from Universiti model

        # Get published status
        published_status = CourseStatus.objects.get(status='published')

        # Cache key for courses
        cache_key_courses = f'instructor_courses_{username}'
        courses = cache.get(cache_key_courses)
        if not courses:
            # Query courses with price and rating data
            courses = instructor.courses.filter(
                status_course=published_status,
                end_date__gte=timezone.now()
            ).select_related('category', 'instructor__user', 'org_partner').prefetch_related('enrollments', 'prices', 'ratings').annotate(
                total_enrollments=Count('enrollments', distinct=True),
                avg_rating=Avg('ratings__rating', default=0),
                review_count=Count('ratings', distinct=True)
            ).values(
                'id', 'slug', 'course_name', 'image', 'end_date', 'total_enrollments',
                'avg_rating', 'review_count'
            )
            courses = list(courses)
            cache.set(cache_key_courses, courses, 60 * 5)

        # Calculate total courses and participants
        courses_count = len(courses)
        total_participants = sum(course['total_enrollments'] for course in courses)

        # Calculate total reviews across all courses
        total_reviews = sum(course['review_count'] for course in courses)

        # Pagination (6 courses per page)
        paginator = Paginator(courses, 6)
        page_number = request.GET.get('page', 1)
        try:
            page_number = int(page_number)
            if page_number < 1:
                page_number = 1
        except ValueError:
            page_number = 1

        try:
            page_obj = paginator.get_page(page_number)
        except EmptyPage:
            page_obj = paginator.get_page(1)

        # Process courses with price and review data
        courses_data = []
        for course in page_obj.object_list:
            try:
                # Fetch CoursePrice
                course_obj = Course.objects.filter(id=course['id']).prefetch_related('prices').first()
                course_price = course_obj.prices.first() if course_obj else None
                price = course_price.portal_price if course_price else Decimal('0.00')
                is_free = price == Decimal('0.00')
                discount_amount = course_price.discount_amount if course_price else Decimal('0.00')
                normal_price = course_price.normal_price if course_price else Decimal('0.00')
                discount_percent = course_price.discount_percent if course_price else Decimal('0.00')

                course_data = {
                    'id': course['id'],
                    'slug': course['slug'],
                    'course_name': course['course_name'],
                    'image': f"{settings.MEDIA_URL}{course['image']}" if course.get('image') else 'https://via.placeholder.com/400x180',
                    'end_date': course['end_date'],
                    'total_enrollments': course['total_enrollments'],
                    'avg_rating': round(course.get('avg_rating', 0) or 0, 1),
                    'review_count': course['review_count'],
                    'full_star_range': range(int(course.get('avg_rating', 0) or 0)),
                    'half_star': (course.get('avg_rating', 0) % 1) >= 0.5 if course.get('avg_rating') else False,
                    'empty_star_range': range(5 - int(course.get('avg_rating', 0) or 0) - (1 if (course.get('avg_rating', 0) % 1) >= 0.5 else 0)),
                    'price': float(price),
                    'is_free': is_free,
                    'discount_amount': float(discount_amount),
                    'normal_price': float(normal_price),
                    'discount_percent': float(discount_percent),
                }
                courses_data.append(course_data)
            except Exception as e:
                logger.error(f"Error processing course {course.get('id', 'unknown')}: {str(e)}")
                continue

        # Render template
        return render(request, 'home/instructor_profile.html', {
            'instructor': instructor,
            'page_obj': page_obj,
            'courses': courses_data,
            'courses_count': courses_count,
            'total_participants': total_participants,
            'total_reviews': total_reviews,
            'partner_slug': partner_slug,
        })

    except CourseStatus.DoesNotExist:
        logger.error("Published status not found")
        return HttpResponseNotFound("Status 'published' tidak ditemukan")
    except Exception as e:
        logger.exception(f"Unexpected error in instructor_profile: {str(e)}")
        return HttpResponseServerError("Terjadi kesalahan yang tidak terduga.")

logger = logging.getLogger(__name__)

@login_required
@require_POST
def enroll_course(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    partner = course.org_partner
    user = request.user
    today = timezone.now().date()

    # Cek apakah kursus gratis (atau via subscription)
    is_course_free = course.payment_model in ['free', 'subscription']

    # Cek apakah user punya lisensi aktif
    has_active_license = user.licenses.filter(
        start_date__lte=today,
        expiry_date__gte=today,
        status=True
    ).exists()

    logger.info(f"[Enroll] User: {user.email}, Course: {course.course_name}, Free: {is_course_free}, Has License: {has_active_license}")

    # Jika kursus berbayar dan user tidak punya lisensi aktif
    if not is_course_free and not has_active_license:
        logger.warning(f"[Enroll Blocked] {user.email} tidak punya lisensi aktif untuk course {course.course_name} yang berbayar")
        
        if course.payment_model == 'buy first':
            messages.info(request, "Anda perlu membayar untuk mengikuti kursus ini.")
            return redirect('payments:process_payment', course_id=course.id)

        # pay for exam atau pay for certificate: boleh lanjut, bayar nanti
        messages.info(request, "")

    # Tentukan tipe harga sesuai payment model
    # Optional alias if needed
    payment_model_aliases = {
        'subscription': 'free',
    }

    payment_model_name = payment_model_aliases.get(course.payment_model, course.payment_model)

    try:
        price_type = PricingType.objects.get(name=payment_model_name)
        logger.info(f"[Enroll] Price type found: {price_type.name}")
    except PricingType.DoesNotExist:
        logger.error(f"[Enroll Error] Price type not found for {payment_model_name}")
        messages.error(request, f"Tipe harga untuk model {course.payment_model} tidak ditemukan.")
        return redirect('courses:course_lms_detail', id=course_id, slug=course.slug)


    # Lanjutkan proses pendaftaran
    response = course.enroll_user(user, partner=partner, price_type=price_type)
    logger.info(f"[Enroll Result] {response}")

    if response["status"] == "success":
        messages.success(request, response["message"])
        return redirect('learner:course_learn', username=user.username, id=course.id, slug=course.slug)

    elif response["status"] == "error":
        if course.payment_model == 'buy first' and "Payment required" in response["message"]:
            return redirect('payments:process_payment', course_id=course.id)
        messages.error(request, response["message"])
    else:
        messages.info(request, response["message"])

    return redirect('courses:course_lms_detail', id=course_id, slug=course.slug)

def draft_lms(request, id):
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)  # Redirect to login if not authenticated

    user = request.user
    course = None
    team_member = None  # inisialisasi untuk aman

    # ==================== AUTHORIZATION ====================

    # 1️⃣ Prioritas superuser / curation
    if user.is_superuser or getattr(user, 'is_curation', False):
        course = get_object_or_404(Course, id=id)

    # 2️⃣ Partner
    if not course and getattr(user, 'is_partner', False):
        course = get_object_or_404(
            Course, id=id, org_partner__user_id=user.id
        )

    # 3️⃣ Instructor
    if not course and getattr(user, 'is_instructor', False):
        course = get_object_or_404(
            Course, id=id, instructor__user_id=user.id
        )

    # 4️⃣ Fallback: CourseTeam
    if not course:
        team_member = CourseTeam.objects.filter(
            course_id=id, user=user
        ).first()

        if team_member:
            course = team_member.course
        else:
            messages.error(request, "Anda tidak memiliki akses ke kursus ini.")
            return redirect('authentication:home')

    # If the course is found, render the course page
    return render(request, 'courses/course_draft_view.html', {'course': course})


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0]
    return request.META.get('REMOTE_ADDR')


#@ratelimit(key='ip', rate='30/h', method='GET', block=True)
def course_lms_detail(request, id, slug):
    if getattr(request, 'limited', False):
        return HttpResponse("Terlalu banyak permintaan. Coba lagi nanti.", status=429)
    
    course = get_object_or_404(
        Course.objects.select_related('category', 'instructor__user', 'status_course')
        .prefetch_related('enrollments', 'ratings'),
        id=id, slug=slug
    )

    try:
        published_status = CourseStatus.objects.get(status='published')
    except CourseStatus.DoesNotExist:
        return redirect('/')

    today = timezone.now().date()
    is_enrolled = request.user.is_authenticated and course.enrollments.filter(user=request.user).exists()

    if not is_enrolled and (course.status_course != published_status or course.end_enrol < today):
        return redirect('/')

    # View counter
    user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
    if 'bot' not in user_agent:
        ip = get_client_ip(request)
        if not CourseViewIP.objects.filter(course=course, ip_address=ip).exists():
            CourseViewIP.objects.create(course=course, ip_address=ip)
            Course.objects.filter(id=course.id).update(view_count=F('view_count') + 1)

        view_log, created = CourseViewLog.objects.get_or_create(course=course, date=today)
        if not created:
            CourseViewLog.objects.filter(pk=view_log.pk).update(count=F('count') + 1)

    # Course status (get_started, resume, completed)
    course_status = None
    if is_enrolled:
        user = request.user
        has_accessed = LastAccessCourse.objects.filter(user=user, course=course).exists()
        course_progress = CourseProgress.objects.filter(user=user, course=course).first()
        progress = course_progress.progress_percentage if course_progress else 0
        grade_range = GradeRange.objects.filter(course=course, name='Pass').first()
        passing_threshold = grade_range.min_grade if grade_range else Decimal('52.00')

        total_score = Decimal('0')
        total_max_score = Decimal('0')

        assessments = Assessment.objects.filter(section__courses=course).distinct()
        for assessment in assessments:
            score_value = Decimal('0')
            total_questions = assessment.questions.count()
            if total_questions > 0:
                total_correct = QuestionAnswer.objects.filter(
                    question__assessment=assessment,
                    user=user,
                    choice__is_correct=True
                ).count()
                score_value = (Decimal(total_correct) / Decimal(total_questions)) * Decimal(assessment.weight)
            else:
                submissions = Submission.objects.filter(askora__assessment=assessment, user=user)
                if submissions.exists():
                    latest = submissions.order_by('-submitted_at').first()
                    score_obj = AssessmentScore.objects.filter(submission=latest).first()
                    if score_obj:
                        score_value = Decimal(score_obj.final_score)
            total_score += score_value
            total_max_score += Decimal(assessment.weight)

        overall_percentage = (total_score / total_max_score * Decimal('100')) if total_max_score > 0 else Decimal('0')

        if progress >= 100 and overall_percentage >= passing_threshold:
            course_status = 'completed'
        elif has_accessed:
            course_status = 'resume'
        else:
            course_status = 'get_started'

    # Similar courses
    similar_courses = Course.objects.filter(
        category=course.category,
        status_course=published_status,
        end_enrol__gte=today
    ).exclude(id=course.id)[:5]

    # Comments dan replies
    comments = CourseComment.objects.filter(course=course, parent=None).order_by('-created_at')
    for comment in comments:
        for reply in comment.replies.all().order_by('-created_at'):
            reply.sub_replies = reply.replies.all().order_by('-created_at')

    section_data = Section.objects.filter(parent=None, courses=course).prefetch_related('materials')
    total_sections = section_data.count()
    total_materials = sum(section.materials.count() for section in section_data)
    total_students = course.enrollments.count()
    total_effort_hours = course.hour if course.hour else "N/A"

    instructor = course.instructor
    instructor_courses = Course.objects.filter(
        instructor=instructor,
        status_course=published_status,
        end_enrol__gte=today
    )
    instructor_total_courses = instructor_courses.count()
    instructor_total_students = sum(c.enrollments.count() for c in instructor_courses)
    instructor_total_effort_hours = sum(int(c.hour) for c in instructor_courses if c.hour and str(c.hour).isdigit())
    instructor_sections = Section.objects.filter(courses__in=instructor_courses, parent=None).prefetch_related('materials')
    instructor_total_sections = instructor_sections.count()
    instructor_total_materials = sum(s.materials.count() for s in instructor_sections)

    # Reviews
    reviews = CourseRating.objects.filter(course=course).order_by('-created_at')
    total_reviews = reviews.count()
    paginator = Paginator(reviews, 5)
    page_obj = paginator.get_page(request.GET.get('page'))
    user_has_rated = request.user.is_authenticated and CourseRating.objects.filter(user=request.user, course=course).exists()

    average_rating = course.average_rating
    full_stars = int(average_rating)
    half_star = (average_rating % 1) >= 0.5
    empty_stars = 5 - (full_stars + (1 if half_star else 0))

    # --- DYNAMIC PRICING PART ---
    partner = None
    if request.user.is_authenticated:
        partner = getattr(request.user, 'partner', None)  # Sesuaikan jika kamu punya cara lain

    course_prices_qs = CoursePrice.objects.filter(course=course)
    if partner:
        course_prices_qs = course_prices_qs.filter(partner=partner)

    course_prices = {}
    for cp in course_prices_qs.select_related('price_type'):
        course_prices[cp.price_type.name] = cp

    return render(request, 'home/course_detail.html', {
        'course': course,
        'is_enrolled': is_enrolled,
        'similar_courses': similar_courses,
        'comments': comments,
        'section_data': section_data,
        'total_sections': total_sections,
        'total_materials': total_materials,
        'total_students': total_students,
        'total_effort_hours': total_effort_hours,
        'instructor': instructor,
        'instructor_total_courses': instructor_total_courses,
        'instructor_total_students': instructor_total_students,
        'instructor_total_effort_hours': instructor_total_effort_hours,
        'instructor_total_sections': instructor_total_sections,
        'instructor_total_materials': instructor_total_materials,
        'reviews': page_obj,
        'user_has_rated': user_has_rated,
        'range': range(1, 6),
        'full_star_range': range(full_stars),
        'half_star': half_star,
        'empty_star_range': range(empty_stars),
        'average_rating': average_rating,
        'course_prices': course_prices,  # <-- di sini
        'total_reviews': total_reviews,
        'course_status': course_status,
    })

@login_required
def course_instructor(request, id):
    user = request.user
    course = None

    if user.is_superuser:
        course = get_object_or_404(Course, id=id)
    elif user.is_partner:
        course = get_object_or_404(Course, id=id, org_partner__user_id=user.id)
    elif user.is_instructor:
        messages.error(request, "You do not have permission to manage this course.")
        return redirect('/courses')

    if not course:
        messages.error(request, "Course not found or you do not have access.")
        return redirect('/courses')

    if request.method == 'POST':
        form = CourseInstructorForm(request.POST, instance=course, request=request)
        if form.is_valid():
            form.save()
            messages.success(request, "Instructor has been successfully added to the course.")
            return redirect('courses:course_instructor', id=course.id)
    else:
        form = CourseInstructorForm(instance=course, request=request)

    return render(request, 'instructor/course_instructor.html', {'course': course, 'form': form})

# Fungsi untuk pencarian instruktur menggunakan Select2 (AJAX)


class InstructorAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Instructor.objects.none()

        if user.is_superuser:
            qs = Instructor.objects.all()
        elif hasattr(user, 'is_partner') and user.is_partner:
            qs = Instructor.objects.filter(provider__user=user)
        else:
            qs = Instructor.objects.none()

        if self.q:
            q = self.q.strip()
            qs = qs.filter(
                Q(user__first_name__icontains=q) | Q(user__last_name__icontains=q)
            )

        return qs.order_by('user__first_name', 'user__last_name')[:20]


#create grade
@login_required
def course_grade(request, id):
    # Check if the user is authenticated
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)
    

    user = request.user
    course = None
    team_member = None  # inisialisasi untuk aman

    # ==================== AUTHORIZATION ====================

    # 1️⃣ Prioritas superuser / curation
    if user.is_superuser or getattr(user, 'is_curation', False):
        course = get_object_or_404(Course, id=id)

    # 2️⃣ Partner
    if not course and getattr(user, 'is_partner', False):
        course = get_object_or_404(
            Course, id=id, org_partner__user_id=user.id
        )

    # 3️⃣ Instructor
    if not course and getattr(user, 'is_instructor', False):
        course = get_object_or_404(
            Course, id=id, instructor__user_id=user.id
        )

    # 4️⃣ Fallback: CourseTeam
    if not course:
        team_member = CourseTeam.objects.filter(
            course_id=id, user=user
        ).first()

        if team_member:
            course = team_member.course
        else:
            messages.error(request, "Anda tidak memiliki akses ke kursus ini.")
            return redirect('authentication:home')
    
    course = get_object_or_404(Course, id=id)
     # Retrieve sections related to this course
    sections = Section.objects.filter(courses=course)  # Get all sections related to the course
   # Ensure grade ranges exist; create defaults if necessary
    grade_fail, created_fail = course.grade_ranges.get_or_create(
        name="Fail",
        defaults={"min_grade": 0, "max_grade": 59},
    )
    grade_pass, created_pass = course.grade_ranges.get_or_create(
        name="Pass",
        defaults={"min_grade": 60, "max_grade": 100},
    )

    # Compute widths for display
    total_grade_range = 100
    fail_width = (grade_fail.max_grade / total_grade_range) * 100
    pass_width = 100 - fail_width

    # Compute grade ranges
    fail_range_max = int(grade_fail.max_grade)
    pass_range_min = fail_range_max + 1

     # Retrieve the sections for the course
    sections = Section.objects.filter(courses=course)  # Get all sections related to this course

    # Retrieve all assessments associated with these sections
    assessments = Assessment.objects.filter(section__in=sections)
    total_weight = sum(assessment.weight for assessment in assessments)
    
    return render(request, 'courses/course_grade.html', {
        'course': course,
        'sections': sections,  # Pass the sections
        "fail_width": fail_width,
        "pass_width": pass_width,
        "fail_range_max": fail_range_max,
        "pass_range_min": pass_range_min,
        'assessments': assessments,  # Pass assessments to the template
        'total_weight': total_weight,
    })


#@login_required
def update_grade_range(request, id):
    # Check if the user is authenticated
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)
    
    user = request.user
    course = None
    team_member = None  # inisialisasi untuk aman

    # ==================== AUTHORIZATION ====================

    # 1️⃣ Prioritas superuser / curation
    if user.is_superuser or getattr(user, 'is_curation', False):
        course = get_object_or_404(Course, id=id)

    # 2️⃣ Partner
    if not course and getattr(user, 'is_partner', False):
        course = get_object_or_404(
            Course, id=id, org_partner__user_id=user.id
        )

    # 3️⃣ Instructor
    if not course and getattr(user, 'is_instructor', False):
        course = get_object_or_404(
            Course, id=id, instructor__user_id=user.id
        )

    # 4️⃣ Fallback: CourseTeam
    if not course:
        team_member = CourseTeam.objects.filter(
            course_id=id, user=user
        ).first()

        if team_member:
            course = team_member.course
        else:
            messages.error(request, "Anda tidak memiliki akses ke kursus ini.")
            return redirect('authentication:home')



    if request.method == "POST":
        try:
            # Fetch course
            course = get_object_or_404(Course, id=id)

            # Get Fail and Pass widths from the AJAX request
            fail_width = Decimal(request.POST.get("fail_width", 50))  # Example: 40.0
            pass_width = Decimal(request.POST.get("pass_width", 50))  # Example: 60.0

            # Get Fail and Pass grade ranges
            grade_fail = course.grade_ranges.filter(name="Fail").first()
            grade_pass = course.grade_ranges.filter(name="Pass").first()

            if not grade_fail or not grade_pass:
                return JsonResponse({"success": False, "message": "Fail or Pass grade range not found!"})

            # Dynamically calculate and update ranges
            grade_fail.max_grade = int((fail_width / 100) * 100)  # Fail max_grade = % of total grade
            grade_pass.min_grade = grade_fail.max_grade + 1  # Pass starts right after Fail's max_grade
            grade_pass.max_grade = 100  # Pass always ends at 100

            # Save updates
            grade_fail.save()
            grade_pass.save()

            return JsonResponse({"success": True, "message": "Grade ranges updated dynamically!"})

        except Exception as e:
            return JsonResponse({"success": False, "message": str(e)})
    return JsonResponse({"success": False, "message": "Invalid request"})


#creat assesment type name
#@login_required
#@csrf_protect
def create_assessment(request, idcourse, idsection):
    # Check if the user is authenticated
    # Check if the user is authenticated
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)
    
    user = request.user
    course = None
    team_member = None  # inisialisasi untuk aman

    # ==================== AUTHORIZATION ====================

    # 1️⃣ Prioritas superuser / curation
    if user.is_superuser or getattr(user, 'is_curation', False):
        course = get_object_or_404(Course, id=id)

    # 2️⃣ Partner
    if not course and getattr(user, 'is_partner', False):
        course = get_object_or_404(
            Course, id=id, org_partner__user_id=user.id
        )

    # 3️⃣ Instructor
    if not course and getattr(user, 'is_instructor', False):
        course = get_object_or_404(
            Course, id=id, instructor__user_id=user.id
        )

    # 4️⃣ Fallback: CourseTeam
    if not course:
        team_member = CourseTeam.objects.filter(
            course_id=id, user=user
        ).first()

        if team_member:
            course = team_member.course
        else:
            messages.error(request, "Anda tidak memiliki akses ke kursus ini.")
            return redirect('authentication:home')

    # Ensure the section belongs to the course
    section = get_object_or_404(Section, id=idsection, courses=course)

    if request.method == 'POST':
        form = AssessmentForm(request.POST)
        if form.is_valid():
            # Convert new_weight to Decimal
            new_weight = Decimal(form.cleaned_data['weight'])
            # Calculate total weight for the course
            total_weight = Assessment.objects.filter(section__courses=course).aggregate(Sum('weight'))['weight__sum']
            total_weight = total_weight if total_weight is not None else Decimal('0')

            if total_weight + new_weight > Decimal('100'):
                messages.error(request, "Total bobot untuk penilaian dalam course ini tidak boleh melebihi 100")
                return render(request, 'courses/course_assessement.html', {'form': form, 'course': course, 'section': section})

            # Create the assessment instance but don't save it yet
            assessment = form.save(commit=False)
            # Set the section field
            assessment.section = section
            # Save the assessment
            assessment.save()
            messages.success(request, "Assessment created successfully!")
            return redirect('courses:view-question', idcourse=course.id, idsection=section.id, idassessment=assessment.id)
    else:
        form = AssessmentForm()

    return render(request, 'courses/course_assessement.html', {'form': form, 'course': course, 'section': section})

#edit assesment type name
#@login_required
@csrf_protect
def edit_assessment(request, idcourse, idsection, idassessment):
    # Check if the user is authenticated
    # Check if the user is authenticated
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)
    
    user = request.user
    course = None
    team_member = None  # inisialisasi untuk aman

    # ==================== AUTHORIZATION ====================

    # 1️⃣ Prioritas superuser / curation
    if user.is_superuser or getattr(user, 'is_curation', False):
        course = get_object_or_404(Course, id=idcourse)

    # 2️⃣ Partner
    if not course and getattr(user, 'is_partner', False):
        course = get_object_or_404(
            Course, id=idcourse, org_partner__user_id=user.id
        )

    # 3️⃣ Instructor
    if not course and getattr(user, 'is_instructor', False):
        course = get_object_or_404(
            Course, id=idcourse, instructor__user_id=user.id
        )

    # 4️⃣ Fallback: CourseTeam
    if not course:
        team_member = CourseTeam.objects.filter(
            course_id=idcourse, user=user
        ).first()

        if team_member:
            course = team_member.course
        else:
            messages.error(request, "Anda tidak memiliki akses ke kursus ini.")
            return redirect('authentication:home')

    # Ensure the section belongs to the course
    section = get_object_or_404(Section, id=idsection, courses=course)

    # Fetch the assessment based on its ID
    assessment = get_object_or_404(Assessment, id=idassessment, section=section)

    if request.method == 'POST':
        form = AssessmentForm(request.POST, instance=assessment)  # Populate the form with current assessment data
        if form.is_valid():
            # Save without committing
            assessment = form.save(commit=False)

            # Check total weight
            total_weight = Assessment.objects.filter(section=section).exclude(id=idassessment).aggregate(Sum('weight'))['weight__sum'] or Decimal('0')
            if total_weight + Decimal(form.cleaned_data['weight']) > Decimal('100'):
                messages.error(request, "Total bobot untuk penilaian dalam section ini tidak boleh melebihi 100")
                return render(request, 'courses/course_assessement_edit.html', {
                    'form': form,
                    'course': course,
                    'section': section,
                    'assessment': assessment,
                })

            # Now save the assessment
            assessment.save()
            messages.warning(request, "Assessment updated successfully!")
            return redirect('courses:view-question', idcourse=course.id, idsection=section.id, idassessment=assessment.id)

    else:
        # Create an empty form or pre-populated form with existing data
        form = AssessmentForm(instance=assessment)

    return render(request, 'courses/course_assessement_edit.html', {
        'form': form,
        'course': course,
        'section': section,
        'assessment': assessment,
    })

#delete assesment type name
#@login_required
@csrf_protect
def delete_assessment(request, idcourse, idsection, idassessment):
    # Check if the user is authenticated
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)
    
    user = request.user
    course = None
    team_member = None  # inisialisasi untuk aman

    # ==================== AUTHORIZATION ====================

    # 1️⃣ Prioritas superuser / curation
    if user.is_superuser or getattr(user, 'is_curation', False):
        course = get_object_or_404(Course, id=idcourse)

    # 2️⃣ Partner
    if not course and getattr(user, 'is_partner', False):
        course = get_object_or_404(
            Course, id=idcourse, org_partner__user_id=user.id
        )

    # 3️⃣ Instructor
    if not course and getattr(user, 'is_instructor', False):
        course = get_object_or_404(
            Course, id=idcourse, instructor__user_id=user.id
        )

    # 4️⃣ Fallback: CourseTeam
    if not course:
        team_member = CourseTeam.objects.filter(
            course_id=idcourse, user=user
        ).first()

        if team_member:
            course = team_member.course
        else:
            messages.error(request, "Anda tidak memiliki akses ke kursus ini.")
            return redirect('authentication:home')

    # Ensure the section belongs to the course
    section = get_object_or_404(Section, id=idsection, courses=course)

    # Fetch the assessment
    assessment = get_object_or_404(Assessment, id=idassessment, section=section)

    if request.method == 'POST':
        # Perform the deletion
        assessment.delete()
        messages.success(request, "Assessment deleted successfully!")
        return redirect('courses:studio', id=course.id)

    # Render confirmation page for GET requests
    return render(request, 'courses/confirm_delete_assessment.html', {
        'course': course,
        'section': section,
        'assessment': assessment,
    })


#edit question and choice
#@login_required
#@csrf_exempt
@login_required
def edit_question(request, idcourse, idsection, idassessment, idquestion):
    # ==================== AUTHORIZATION ====================
    user = request.user
    course = None
    team_member = None  # inisialisasi untuk aman

    # ==================== AUTHORIZATION ====================

    # 1️⃣ Prioritas superuser / curation
    if user.is_superuser or getattr(user, 'is_curation', False):
        course = get_object_or_404(Course, id=idcourse)

    # 2️⃣ Partner
    if not course and getattr(user, 'is_partner', False):
        course = get_object_or_404(
            Course, id=idcourse, org_partner__user_id=user.id
        )

    # 3️⃣ Instructor
    if not course and getattr(user, 'is_instructor', False):
        course = get_object_or_404(
            Course, id=idcourse, instructor__user_id=user.id
        )

    # 4️⃣ Fallback: CourseTeam
    if not course:
        team_member = CourseTeam.objects.filter(
            course_id=idcourse, user=user
        ).first()

        if team_member:
            course = team_member.course
        else:
            messages.error(request, "Anda tidak memiliki akses ke kursus ini.")
            return redirect('authentication:home')

    section = get_object_or_404(Section, id=idsection, courses=course)
    assessment = get_object_or_404(Assessment, id=idassessment, section=section)
    question = get_object_or_404(Question, id=idquestion, assessment=assessment)

    # ==================== FORMS ====================
    question_form = QuestionForm(request.POST or None, instance=question, assessment=assessment)

    choice_formset = ChoiceFormSet(
        data=request.POST or None,
        instance=question,
        prefix='choices',
        form_kwargs={'assessment': assessment}
    )

    # Set CKEditor hanya jika flag True
    if assessment.flag:
        question_form.fields['text'].widget = CKEditor5Widget(config_name='extends')
    else:
        question_form.fields['text'].widget = forms.Textarea(attrs={
            'class': 'w-full px-6 py-5 border-2 border-gray-300 rounded-xl focus:border-indigo-500 focus:ring-0',
            'rows': 8,
            'placeholder': 'Tulis pertanyaan di sini...',
            'style': 'resize: vertical; min-height: 180px;'
        })

    # ==================== POST HANDLING ====================
    # ==================== POST HANDLING ====================
    if request.method == 'POST':
        if question_form.is_valid() and choice_formset.is_valid():

            question = question_form.save()

            choice_formset.instance = question
            choice_formset.save()

            messages.success(request, "Soal berhasil diperbarui!")

            return redirect('courses:view-question',
                            idcourse=course.id,
                            idsection=section.id,
                            idassessment=assessment.id)

        else:
            # ==================== LOG ERROR DETAIL ====================
            print("\n================= EDIT QUESTION ERRORS =================")
            print("QUESTION FORM ERRORS:", question_form.errors)
            print("QUESTION NON-FIELD ERRORS:", question_form.non_field_errors())

            print("\nFORMSET NON-FIELD ERRORS:", choice_formset.non_form_errors())

            for i, f in enumerate(choice_formset.forms):
                print(f"\n--- Choice Form {i} ---")
                print("Errors:", f.errors)
                print("Non-field:", f.non_field_errors())
            print("=========================================================\n")

            messages.error(request, "Terdapat kesalahan. Periksa kembali isian Anda.")


    # ==================== CONTEXT ====================
    context = {
        'course': course,
        'section': section,
        'assessment': assessment,
        'question': question,
        'question_form': question_form,
        'choice_formset': choice_formset,
        'edit_mode': True,
    }

    return render(request, 'courses/create_question.html', context)


#delete question
@csrf_exempt
def delete_question(request, idcourse, idquestion, idsection, idassessment):
    # Check if the user is authenticated
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)
    
    user = request.user
    course = None
    team_member = None  # inisialisasi untuk aman

    # ==================== AUTHORIZATION ====================

    # 1️⃣ Prioritas superuser / curation
    if user.is_superuser or getattr(user, 'is_curation', False):
        course = get_object_or_404(Course, id=idcourse)

    # 2️⃣ Partner
    if not course and getattr(user, 'is_partner', False):
        course = get_object_or_404(
            Course, id=idcourse, org_partner__user_id=user.id
        )

    # 3️⃣ Instructor
    if not course and getattr(user, 'is_instructor', False):
        course = get_object_or_404(
            Course, id=idcourse, instructor__user_id=user.id
        )

    # 4️⃣ Fallback: CourseTeam
    if not course:
        team_member = CourseTeam.objects.filter(
            course_id=idcourse, user=user
        ).first()

        if team_member:
            course = team_member.course
        else:
            messages.error(request, "Anda tidak memiliki akses ke kursus ini.")
            return redirect('authentication:home')

    # Ensure the section belongs to the course
    section = get_object_or_404(Section, id=idsection, courses=course)

    # Ensure the assessment belongs to the section
    assessment = get_object_or_404(Assessment, id=idassessment, section=section)

    # Ensure the question belongs to the assessment
    question = get_object_or_404(Question, id=idquestion, assessment=assessment)

    if request.method == 'POST':
        try:
            # Deleting the question
            question.delete()
            messages.success(request, "Question deleted successfully.")
        except Exception as e:
            messages.error(request, f"Error deleting question: {e}")

        # Redirecting back to the page with the list of questions
        return redirect('courses:view-question', idcourse=course.id, idsection=section.id, idassessment=assessment.id)

    return render(request, 'courses/view_question.html', {
        'course': course,
        'section': section,
        'assessment': assessment,
    })




@login_required
def create_question_view(request, idcourse, idsection, idassessment):

    user = request.user
    course = None
    team_member = None  # inisialisasi untuk aman

    # ==================== AUTHORIZATION ====================

    # 1️⃣ Prioritas superuser / curation
    if user.is_superuser or getattr(user, 'is_curation', False):
        course = get_object_or_404(Course, id=idcourse)

    # 2️⃣ Partner
    if not course and getattr(user, 'is_partner', False):
        course = get_object_or_404(
            Course, id=idcourse, org_partner__user_id=user.id
        )

    # 3️⃣ Instructor
    if not course and getattr(user, 'is_instructor', False):
        course = get_object_or_404(
            Course, id=idcourse, instructor__user_id=user.id
        )

    # 4️⃣ Fallback: CourseTeam
    if not course:
        team_member = CourseTeam.objects.filter(
            course_id=idcourse, user=user
        ).first()

        if team_member:
            course = team_member.course
        else:
            messages.error(request, "Anda tidak memiliki akses ke kursus ini.")
            return redirect('authentication:home')

    # ==================== VALIDATE SECTION & ASSESSMENT ====================

    section = get_object_or_404(Section, id=idsection, courses=course)
    assessment = get_object_or_404(Assessment, id=idassessment, section=section)

    # ==================== FORMS ====================
    question_form = QuestionForm(request.POST or None, assessment=assessment)

    choice_formset = ChoiceFormSet(
        data=request.POST or None,
        instance=Question(),              # dummy instance
        prefix='choices',
        form_kwargs={'assessment': assessment}  # penting!
    )

    # Set widget CKEditor jika flag = True
    if assessment.flag:
        question_form.fields['text'].widget = CKEditor5Widget(config_name='extends')
    else:
        question_form.fields['text'].widget = forms.Textarea(attrs={
            'class': 'w-full px-6 py-5 border-2 border-gray-300 rounded-xl focus:border-indigo-500 focus:ring-0',
            'rows': 8,
            'placeholder': 'Tulis pertanyaan di sini...',
            'style': 'resize: vertical; min-height: 180px;'
        })

    # ==================== POST HANDLING ====================
    if request.method == 'POST':
        if question_form.is_valid() and choice_formset.is_valid():

            # Simpan pertanyaan
            question = question_form.save(commit=False)
            question.section = section
            question.assessment = assessment
            question.save()

            # Simpan pilihan jawaban
            choice_formset.instance = question
            choice_formset.save()

            messages.success(request, "Soal dan pilihan jawaban berhasil dibuat!")

            # Save & Add Another
            if 'save_and_add_another' in request.POST:
                return redirect('courses:create_question',
                                idcourse=course.id,
                                idsection=section.id,
                                idassessment=assessment.id)

            # Save
            return redirect('courses:view-question',
                            idcourse=course.id,
                            idsection=section.id,
                            idassessment=assessment.id)

        else:
            messages.error(request, "Terdapat kesalahan. Silakan periksa kembali isian Anda.")

    # ==================== CONTEXT ====================
    context = {
        'course': course,
        'section': section,
        'assessment': assessment,
        'question_form': question_form,
        'choice_formset': choice_formset,
        'user_role': getattr(team_member, 'role', None),
    }

    return render(request, 'courses/create_question.html', context)



#view question

def question_view(request, idcourse, idsection, idassessment):
    # 1️⃣ Pastikan user login
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)

    user = request.user
    course = None
    team_member = None  # inisialisasi

    # 2️⃣ Prioritas superuser / curation
    if user.is_superuser or user.is_curation:
        course = get_object_or_404(Course, id=idcourse)

    # 3️⃣ Partner / instructor hanya jika course belum ditemukan
    if not course and user.is_partner:
        course = get_object_or_404(Course, id=idcourse, org_partner__user_id=user.id)

    if not course and user.is_instructor:
        course = get_object_or_404(Course, id=idcourse, instructor__user_id=user.id)

    # 4️⃣ Cek CourseTeam sebagai fallback
    if not course:
        team_member = CourseTeam.objects.filter(course_id=idcourse, user=user).first()
        if team_member:
            course = team_member.course
        else:
            messages.error(request, "You do not have permission to view questions for this course.")
            return redirect('authentication:home')

    # 5️⃣ Pastikan section benar-benar milik course
    section = get_object_or_404(Section, id=idsection, courses=course)

    # 6️⃣ Ambil assessment dan prefetch related untuk performance
    assessment = get_object_or_404(
        Assessment.objects
        .select_related('lti_tool')
        .prefetch_related(
            'questions__choices',
            'ask_oras',
            'quizzes',              # <--- Tambahkan ini
            'quizzes__options'      # <--- Penting kalau quiz MCQ
        ),
        id=idassessment,
        section=section
    )


    return render(request, 'courses/view_question.html', {
        'course': course,
        'section': section,
        'assessment': assessment,
        'user_role': getattr(team_member, 'role', None)  # bisa dipakai di template
    })






#upprove user request
#@login_required
def instructor_check(request, instructor_id):
    # Check if the user is authenticated
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)
    # Fetch the instructor object
    instructor = get_object_or_404(Instructor, id=instructor_id)
    
    # Check if the user has permission to approve (e.g., the user must be the provider)
    if request.user.is_partner and instructor.provider.user == request.user:
        # Update instructor status to "Approved"
        instructor.status = 'Approved'
        instructor.save()  # Save the status change

        # Now update the user's `is_partner` field to True
        user = instructor.user  # Get the related User object
        
        # Set is_partner to True
        user.is_instructor = True
        user.save()  # Save the user after the update

        # Success message
        messages.success(request, "Instructor has been approved.")
        
    else:
        # Error message if the user doesn't have permission
        messages.error(request, "You do not have permission to approve this instructor.")

    # Redirect to the instructor list or another page after approval
    return redirect('courses:instructor_view')  # Change this URL to your desired location


#instructor detail
#@login_required
def instructor_detail(request, id):
    user = request.user
    # Check if the user is authenticated
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)
    
    # Fetch the instructor object by the provided ID
    instructor = get_object_or_404(Instructor, id=id)
      # === 🔒 ACCESS VALIDATION ===
    allowed_roles = ['is_curation', 'is_finance']

    is_allowed = (
        user.is_superuser or
        user.is_staff or
        (hasattr(user, 'role') and user.role in allowed_roles) or
        user.groups.filter(name__in=allowed_roles).exists()
    )

    # Partner: hanya bisa akses instructor di bawah partner-nya sendiri
    is_partner_owner = (
        hasattr(user, 'partner_user') and
        instructor.provider and
        instructor.provider.user == user
    )

    # Instructor itu sendiri boleh akses profilnya
    is_self = hasattr(instructor, 'user') and instructor.user == user

    if not (is_allowed or is_partner_owner or is_self):
        messages.error(request, "Access denied. You do not have permission to view this instructor’s details.")
        return redirect('authentication:home')

    # Ensure that the instructor has a provider (Partner) with a slug in the related Universiti
    if not instructor.provider or not hasattr(instructor.provider.name, 'slug'):
        # Handle the case where there is no provider or slug
        partner_slug = None
    else:
        partner_slug = instructor.provider.name.slug  # Access slug from Universiti model

    # Get the search term from the GET request (if any)
    search_term = request.GET.get('search', '')

    # Filter courses based on the search term
    courses = instructor.courses.filter(
        Q(course_name__icontains=search_term)  # Search by course name only
    ).order_by('start_date')  # Optional: Order by start date or any other field

    # Get the count of filtered courses
    courses_count = courses.count()

    # Hitung jumlah total siswa yang terdaftar di semua kursus yang diberikan instruktur ini
    total_students = Enrollment.objects.filter(course__in=courses).values('user').annotate(num_students=Count('user')).count()

    # Hitung jumlah total ulasan untuk semua kursus instruktur
    total_reviews = CourseRating.objects.filter(course__in=courses).count()

    # Hitung rata-rata rating untuk semua kursus instruktur
    avg_rating = CourseRating.objects.filter(course__in=courses).aggregate(avg_rating=Avg('rating'))['avg_rating'] or 0

    # Add a participant count and review count for each course
    courses = courses.annotate(
        participants_count=Count('enrollments'),
        ratings_count=Count('ratings')  # Jumlah ulasan per kursus menggunakan related_name='ratings'
    )

    # Implement pagination: Show 6 courses per page
    paginator = Paginator(courses, 6)

    # Get the current page number from GET params (default to 1 if invalid)
    page_number = request.GET.get('page', 1)  # Default to page 1 if not specified

    # Ensure the page number is a positive integer
    try:
        page_number = int(page_number)
        if page_number < 1:
            page_number = 1  # If the page number is less than 1, set it to 1
    except ValueError:
        page_number = 1  # If the page number is not a valid integer, set it to 1

    # Get the page object
    try:
        page_obj = paginator.get_page(page_number)
    except EmptyPage:
        page_obj = paginator.get_page(1)  # If page number is out of range, show first page

    # Create the context dictionary to pass to the template
    context = {
        'instructor': instructor,
        'page_obj': page_obj,  # Pass the paginated courses to the template
        'courses_count': courses_count,  # Total number of filtered courses
        'search_term': search_term,  # Pass the search query to the template
        'partner_slug': partner_slug,  # Pass the partner slug to the template
        'total_students': total_students,
        'total_reviews': total_reviews,  # Total ulasan untuk semua kursus
        'avg_rating': round(avg_rating, 1) if avg_rating else 0,  # Rata-rata rating, dibulatkan ke 1 desimal
    }

    # Render the instructor_detail template with the context
    return render(request, 'instructor/instructor_detail.html', context)

#view instructor
#@login_required

def instructor_view(request):
    # Check if the user is authenticated
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)
    user = request.user
    required_fields = {
        'first_name': 'First Name',
        'last_name': 'Last Name',
        'email': 'Email',
        'phone': 'Phone Number',
        'gender': 'Gender',
        'birth': 'Date of Birth',

    }
    missing_fields = [label for field, label in required_fields.items() if not getattr(user, field)]

    if missing_fields:
        messages.warning(request, f"Please complete the following information: {', '.join(missing_fields)}")
        return redirect('authentication:edit-profile', pk=user.pk)
    # Get search query from GET parameters
    search_query = request.GET.get('q', '').strip()
    
    # Define base queryset based on user role
    if request.user.is_superuser:
        # Admin sees all instructors
        instructors = Instructor.objects.all().annotate(num_courses=Count('courses'))
    elif request.user.is_partner:
        # Partner sees instructors linked to their provider
        instructors = Instructor.objects.filter(provider__user=request.user).annotate(num_courses=Count('courses'))
    elif request.user.is_instructor:
        messages.error(request, "You do not have permission to view this instructor list.")
        return render(request, 'instructor/instructor_list.html', {'instructors': []})
    else:
        messages.error(request, "You do not have permission to view this instructor list.")
        return render(request, 'instructor/instructor_list.html', {'instructors': []})

    # Apply search filter if query exists
    if search_query:
        instructors = instructors.filter(
            Q(user__username__icontains=search_query) | Q(user__email__icontains=search_query)
        )  # Pencarian berdasarkan username atau email dari model User

    # Pagination
    items_per_page = 10  # Jumlah item per halaman
    paginator = Paginator(instructors, items_per_page)
    page_number = request.GET.get('page')

    try:
        instructors_page = paginator.page(page_number)
    except PageNotAnInteger:
        instructors_page = paginator.page(1)
    except EmptyPage:
        instructors_page = paginator.page(paginator.num_pages)

    # Context untuk template
    context = {
        'instructors': instructors_page,
        'search_query': search_query,
        'paginator': paginator,
    }

    return render(request, 'instructor/instructor_list.html', context)

#delete instructor
#@login_required
def delete_instructor(request, instructor_id):
    # Check if the user is authenticated
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)
   
    # Fetch the instructor object
    instructor = get_object_or_404(Instructor, id=instructor_id)
    
    # Ensure the user has permission to delete the instructor
    if request.user.is_partner and instructor.provider.user == request.user:
        instructor.delete()
        messages.success(request, "Instructor deleted successfully.")
    else:
        messages.error(request, "You do not have permission to delete this instructor.")

    # Redirect to the list of instructors
    return redirect('courses:instructor_view')

@login_required
def partner_autocomplete(request):
    query = request.GET.get('q', '').strip()
    page = int(request.GET.get('page', 1))
    page_size = 10
    offset = (page - 1) * page_size

    partners = Partner.objects.select_related('name')

    if query:
        partners = partners.filter(Q(name__name__icontains=query))

    total_count = partners.count()
    partners = partners.order_by('name__name')[offset:offset + page_size]

    results = [
        {
            'id': partner.id,
            'text': partner.name.name
        } for partner in partners
    ]

    return JsonResponse({
        'results': results,
        'pagination': {'more': total_count > offset + page_size}
    })

#intructor form for new request
#@login_required
def become_instructor(request):
    # Check if the user is authenticated
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)
    # Check if the user is already an instructor

    user = request.user

    # Validasi data diri wajib
    required_fields = {
        'first_name': 'First Name',
        'last_name': 'Last Name',
        'email': 'Email',
        'phone': 'Phone Number',
        'gender': 'Gender',
        'birth': 'Date of Birth',
    }

    missing_fields = [
        label for field, label in required_fields.items()
        if not getattr(user, field, None)
        or (isinstance(getattr(user, field), str) and not getattr(user, field).strip())
    ]

    if missing_fields:
        messages.warning(
            request,
            f"Please complete your profile before accessing microcredentials: {', '.join(missing_fields)}"
        )
        return redirect('authentication:edit-profile', pk=user.pk)
    
    try:
        application = Instructor.objects.get(user=request.user)
        if application.status == "Pending":
            
            messages.info(request, "Your application is under review.")
        elif application.status == "Approved":
            messages.success(request, "You are already an instructor!")
        return redirect('authentication:dasbord')
    except Instructor.DoesNotExist:
        if request.method == "POST":
            form = InstructorForm(request.POST)
            if form.is_valid():
                application = form.save(commit=False)
                application.user = request.user
                application.save()
                messages.success(request, "Your application has been submitted!")
                return redirect('authentication:dasbord')
        else:
            form = InstructorForm()

    return render(request, 'home/become_instructor.html', {'form': form})


class PartnerAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return Partner.objects.none()

        qs = Partner.objects.all()

        if self.q:
            qs = qs.filter(name__icontains=self.q)  # atau sesuaikan dengan field nama di Partner

        return qs



#remove team
#@login_required

def remove_team_member(request, member_id):
    # Check if the user is authenticated
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)
    # Check if the user is authorized to access the course
    team_member = get_object_or_404(TeamMember, id=member_id)

    course_id = team_member.course.id


    # Check if the user is the instructor or the organization partner

    is_instructor = getattr(team_member.course.instructor, 'user', None) == request.user

    is_partner = getattr(team_member.course.org_partner, 'user', None) == request.user
    is_superuser = request.user.is_superuser
    
    if is_instructor or is_partner or is_superuser:

        team_member.delete()  # Remove the team member


    return redirect('courses:course_team', id=course_id)  # Redir

#course profile
@csrf_protect
def course_profile(request, id):
    # Check if the user is authenticated
    user = request.user
    course = None
    team_member = None  # inisialisasi untuk aman

    # ==================== AUTHORIZATION ====================

    # 1️⃣ Prioritas superuser / curation
    if user.is_superuser or getattr(user, 'is_curation', False):
        course = get_object_or_404(Course, id=id)

    # 2️⃣ Partner
    if not course and getattr(user, 'is_partner', False):
        course = get_object_or_404(
            Course, id=id, org_partner__user_id=user.id
        )

    # 3️⃣ Instructor
    if not course and getattr(user, 'is_instructor', False):
        course = get_object_or_404(
            Course, id=id, instructor__user_id=user.id
        )

    # 4️⃣ Fallback: CourseTeam
    if not course:
        team_member = CourseTeam.objects.filter(
            course_id=id, user=user
        ).first()

        if team_member:
            course = team_member.course
        else:
            messages.error(request, "Anda tidak memiliki akses ke kursus ini.")
            return redirect('authentication:home')

    # Handle POST request to update course data
    if request.method == 'POST':
        form = ProfilForm(request.POST,request.FILES, instance=course)
        if form.is_valid():
            form.save()  # Save the updated course data
            
            #print(reverse('course_profile', kwargs={'id': course.id}))
            messages.success(request, "Course profile updated successfully!")
            return redirect('courses:course_profile', id=course.id)  # Redirect back to the updated course profile
    else:
        form = ProfilForm(instance=course)  # For GET requests, display the form with existing course data

    return render(request, 'courses/course_profile.html', {'course': course, 'form': form})




#add section
#@login_required
@csrf_protect
def create_section(request, idcourse):
    # Check if the user is authenticated
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)
    # Get the course based on the user's role
    if request.method == "POST":
        # Check user permissions
        if request.user.is_superuser:
            course = get_object_or_404(Course, id=idcourse)
        elif request.user.is_partner:
            course = get_object_or_404(Course, id=idcourse, org_partner__user_id=request.user.id)
        elif request.user.is_instructor:
            course = get_object_or_404(Course, id=idcourse, instructor__user_id=request.user.id)
        else:
            return JsonResponse({'status': 'error', 'message': 'Permission denied.'})

        form = SectionForm(request.POST)
        if form.is_valid():
            section = form.save(commit=False)
            section.courses = course
            section.save()
            return JsonResponse({'status': 'success', 'message': 'Section created successfully!'})
        else:
            return JsonResponse({'status': 'error', 'message': 'Form is not valid', 'errors': form.errors})

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'})



# Delete section
#@login_required
@csrf_protect
def delete_section(request, pk):
    # Check if the user is authenticated
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)
    # Fetch the section
    section = get_object_or_404(Section, pk=pk)
    course = section.courses  # Use the correct relationship field name

    # Check user roles
    if request.user.is_superuser:
        # Superusers can delete any section
        pass
    elif request.user.is_partner:
        # Partners can delete sections only for their associated courses
        if course.org_partner.user_id != request.user.id:
            return JsonResponse({'status': 'error', 'message': 'Permission denied.'})
    elif request.user.is_instructor:
        # Instructors can delete sections only for their own courses
        if course.instructor.user_id != request.user.id:
            return JsonResponse({'status': 'error', 'message': 'Permission denied.'})
    else:
        # Unauthorized user
        return JsonResponse({'status': 'error', 'message': 'Permission denied.'})

    # If role check passes, delete the section
    if request.method == 'POST':
        section.delete()
        return JsonResponse({'status': 'success', 'message': 'Section deleted!'})
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'})


# Update Section
# Update Section with Role-Based Access
#@login_required
@csrf_protect
def update_section(request, pk):
    # Check if the user is authenticated
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)
    # Fetch the section
    section = get_object_or_404(Section, pk=pk)
    course = section.courses  # Use the correct relationship field name

    # Check user roles
    if request.user.is_superuser:
        # Superusers can update any section
        pass
    elif request.user.is_partner:
        # Partners can update sections only for their associated courses
        if course.org_partner.user_id != request.user.id:
            return JsonResponse({'status': 'error', 'message': 'Permission denied.'})
    elif request.user.is_instructor:
        # Instructors can update sections only for their own courses
        if course.instructor.user_id != request.user.id:
            return JsonResponse({'status': 'error', 'message': 'Permission denied.'})
    else:
        # Unauthorized user
        return JsonResponse({'status': 'error', 'message': 'Permission denied.'})

    if request.method == "POST":
        # Handle form submission
        form = SectionForm(request.POST, instance=section)
        if form.is_valid():
            # Save the updated section
            form.save()
            return JsonResponse({'status': 'success', 'message': 'Section updated successfully!'})
        else:
            # Return specific form errors for debugging
            return JsonResponse({'status': 'error', 'message': 'Form is not valid', 'errors': form.errors})
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'})



@login_required
def add_matrial(request, idcourse, idsection):
    # Langsung ambil course dengan semua kondisi akses
    if request.user.is_superuser:
        course = get_object_or_404(Course, id=idcourse)
    elif request.user.is_partner:
        course = get_object_or_404(Course, id=idcourse, org_partner__user_id=request.user.id)
    elif request.user.is_instructor:
        course = get_object_or_404(Course, id=idcourse, instructor__user_id=request.user.id, instructor__status='Approved')
    else:
        messages.error(request, "Kamu tidak punya akses ke course ini.")
        return redirect('courses:home')

    # Ambil section (pastikan milik course ini)
    section = get_object_or_404(Section, id=idsection, courses=course)

    if request.method == 'POST':
        form = MatrialForm(request.POST, request.FILES)
        if form.is_valid():
            material = form.save(commit=False)
            material.section = section
            material.courses = course
            material.save()
            messages.success(request, "Material berhasil ditambahkan!")
            return redirect('courses:studio', id=course.id)
        else:
            messages.error(request, "Form tidak valid.")
    else:
        form = MatrialForm()

    return render(request, 'courses/course_matrial.html', {
        'form': form,
        'course': course,
        'section': section,
    })

#edit matrial course
#@login_required
@csrf_protect
def edit_matrial(request, idcourse, idmaterial):
    # Check the role of the user and determine access permissions
    # Check if the user is authenticated
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)
    # Superuser can access and edit any material
    if request.user.is_superuser:
        # Superuser can access any material, get the associated course via section
        material = get_object_or_404(Material, id=idmaterial)
        course = get_object_or_404(Course, id=idcourse)
    
    # Partner can only access materials related to their course
    elif request.user.is_partner:
        course = get_object_or_404(Course, id=idcourse, org_partner__user_id=request.user.id)
        # Ensure the material belongs to the course's section
        material = get_object_or_404(Material, id=idmaterial, section__courses=course)
    
    # Instructor can only access and edit materials related to their courses
    elif request.user.is_instructor:
        course = get_object_or_404(Course, id=idcourse, instructor__user_id=request.user.id)
        # Ensure the material belongs to the course's section
        material = get_object_or_404(Material, id=idmaterial, section__courses=course)
    
    else:
        # Unauthorized access for users who are not superuser, partner, or instructor
        messages.error(request, "You do not have permission to edit materials in this course.")
        return redirect('courses:home')

    # Handle POST request to update the material
    if request.method == 'POST':
        form = MatrialForm(request.POST, request.FILES, instance=material)
        if form.is_valid():
            form.save()  # Save the updated material
            messages.success(request, "Successfully updated material.")
            return redirect('courses:studio', id=course.id)  # Redirect to the course studio page
        else:
            messages.error(request, "Failed to update material. Please check the form for errors.")
            print(form.errors)  # Debugging (optional)
    else:
        # For GET requests, populate the form with existing material
        form = MatrialForm(instance=material)

    # Render the template with the form and context
    return render(request, 'courses/edit_matrial_course.html', {
        'form': form,
        'course': course,
        'material': material,
    })





#delete matrial course
#@login_required
@csrf_protect
def delete_matrial(request, pk):
    # Check if the user is authenticated
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)
    # Ensure the request is a POST request
    if request.method == 'POST':
        # Fetch the material and its section
        material = get_object_or_404(Material, id=pk)
        section = material.section
        course = section.courses  # Adjust this if the field name is different

        # Check user roles
        if request.user.is_superuser:
            # Superuser can delete any material
            pass
        elif request.user.is_partner:
            # Partner can delete material only for their associated courses
            if not course.org_partner or course.org_partner.user_id != request.user.id:
                return JsonResponse({'status': 'error', 'message': 'Permission denied. You do not own this course.'})
        elif request.user.is_instructor:
            # Instructor can delete material only for their own courses
            if not course.instructor or course.instructor.user_id != request.user.id:
                return JsonResponse({'status': 'error', 'message': 'Permission denied. This is not your course.'})
        else:
            # Unauthorized user
            return JsonResponse({'status': 'error', 'message': 'Permission denied.'})

        # Delete the material if the role check passes
        material.delete()
        return JsonResponse({'status': 'success', 'message': 'Material deleted successfully!'})
    else:
        # Handle invalid request methods
        return JsonResponse({'status': 'error', 'message': 'Invalid request method. Only POST requests are allowed.'})



#course view 
#@login_required



def courseView(request):
    # Check if the user is authenticated
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)

    user = request.user
    required_fields = {
        'first_name': 'First Name',
        'last_name': 'Last Name',
        'email': 'Email',
        'phone': 'Phone Number',
        'gender': 'Gender',
        'birth': 'Date of Birth',

    }
    missing_fields = [label for field, label in required_fields.items() if not getattr(user, field)]

    if missing_fields:
        messages.warning(request, f"Please complete the following information: {', '.join(missing_fields)}")
        return redirect('authentication:edit-profile', pk=user.pk)

    course_filter = request.GET.get('filter', 'all')  # Get filter from query string

    # Update status for published courses that have passed end_enrol
    try:
        published_status = CourseStatus.objects.get(status='published')
        archive_status = CourseStatus.objects.get(status='archived')
        
        # Find published courses where end_enrol has passed and update to archived
        Course.objects.filter(
            status_course=published_status,
            end_enrol__lt=timezone.now().date()  # Gunakan date untuk DateField
        ).update(status_course=archive_status)
    except CourseStatus.DoesNotExist:
        # Jika status tidak ditemukan, lanjutkan tanpa pembaruan
        pass

    # Filter courses based on the user's role and selected filter
    if user.is_superuser or user.is_curation:
        courses = Course.objects.all()
    elif user.is_partner:
        courses = Course.objects.filter(org_partner__user=user)
    elif user.is_instructor:
        courses = Course.objects.filter(instructor__user=user, instructor__status='Approved')
    else:
        courses = Course.objects.none()

    # Apply the filter for the course status
    if course_filter == 'draft':
        courses = courses.filter(status_course__status='draft')
    elif course_filter == 'published':
        courses = courses.filter(status_course__status='published')
    elif course_filter == 'archive':
        courses = courses.filter(status_course__status='archived')
    elif course_filter == 'curation':
        courses = courses.filter(status_course__status='curation')

    # Get search query if any
    search_query = request.GET.get('search', '').strip()
    if search_query:
        courses = courses.filter(course_name__icontains=search_query)

    # Annotate instructor_email and org_partner_name
    courses = courses.annotate(
        instructor_email=F('instructor__user__email'),
        org_partner_name=F('org_partner__name__name')
    )

    # Correctly annotate the enrolment count based on the relationship
    courses = courses.annotate(
        enrolment_count=Count('enrollments')  # Adjust based on your model
    )

    # Paginate the courses
    paginator = Paginator(courses, 10)  # 10 courses per page
    page_number = request.GET.get('page', 1)
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    # Fetch CourseStatus for counts
    try:
        draft_status = CourseStatus.objects.get(status='draft')
        published_status = CourseStatus.objects.get(status='published')
        archive_status = CourseStatus.objects.get(status='archived')
        curation_status = CourseStatus.objects.get(status='curation')
    except ObjectDoesNotExist:
        draft_status = published_status = archive_status = curation_status = None

    # Calculate counts based on filtered courses
    draft_count = courses.filter(status_course=draft_status).count() if draft_status else 0
    published_count = courses.filter(status_course=published_status).count() if published_status else 0
    archive_count = courses.filter(status_course=archive_status).count() if archive_status else 0
    curation_count = courses.filter(status_course=curation_status).count() if curation_status else 0

    # If there's a search query, update the counts to reflect only the filtered results
    if search_query:
        draft_count = courses.filter(status_course=draft_status).count() if draft_status else 0
        published_count = courses.filter(status_course=published_status).count() if published_status else 0
        archive_count = courses.filter(status_course=archive_status).count() if archive_status else 0
        curation_count = courses.filter(status_course=curation_status).count() if curation_status else 0

    # Pass the filtered courses count to the template
    return render(request, 'courses/course_view.html', {
        'page_obj': page_obj,
        'course_filter': course_filter,
        'all_count': courses.count(),
        'draft_count': draft_count,
        'published_count': published_count,
        'archive_count': archive_count,
        'curation_count': curation_count
    })



#kusus tim
def courseViewTim(request):
    # 1️⃣ Pastikan user login
    if not request.user.is_authenticated:
        return redirect(f"/login/?next={request.path}")

    user = request.user

    # 2️⃣ Periksa kelengkapan profil
    required_fields = {
        'first_name': 'First Name',
        'last_name': 'Last Name',
        'email': 'Email',
        'phone': 'Phone Number',
        'gender': 'Gender',
        'birth': 'Date of Birth',
    }
    missing_fields = [label for field, label in required_fields.items() if not getattr(user, field)]
    if missing_fields:
        messages.warning(request, f"Please complete the following information: {', '.join(missing_fields)}")
        return redirect('authentication:edit-profile', pk=user.pk)

    # 3️⃣ Filter dari query string
    course_filter = request.GET.get('filter', 'all')
    search_query = request.GET.get('search', '').strip()

    # 4️⃣ Update status course yang sudah habis enrol date
    try:
        published_status = CourseStatus.objects.get(status='published')
        archive_status = CourseStatus.objects.get(status='archived')
        Course.objects.filter(
            status_course=published_status,
            end_enrol__lt=timezone.now().date()
        ).update(status_course=archive_status)
    except CourseStatus.DoesNotExist:
        pass

    # 5️⃣ Ambil semua course yang user adalah anggota tim
    courses = Course.objects.filter(teams__user=user).distinct()

    # 6️⃣ Apply filter status
    if course_filter == 'draft':
        courses = courses.filter(status_course__status='draft')
    elif course_filter == 'published':
        courses = courses.filter(status_course__status='published')
    elif course_filter == 'archive':
        courses = courses.filter(status_course__status='archived')
    elif course_filter == 'curation':
        courses = courses.filter(status_course__status='curation')

    # 7️⃣ Apply search
    if search_query:
        courses = courses.filter(course_name__icontains=search_query)

    # 8️⃣ Annotate extra fields (opsional)
    courses = courses.annotate(
        instructor_email=F('instructor__user__email'),
        org_partner_name=F('org_partner__name__name'),
        enrolment_count=Count('enrollments')
    )

    # 9️⃣ Pagination
    paginator = Paginator(courses, 10)
    page_number = request.GET.get('page', 1)
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    # 10️⃣ Hitung jumlah berdasarkan status
    try:
        draft_status = CourseStatus.objects.get(status='draft')
        published_status = CourseStatus.objects.get(status='published')
        archive_status = CourseStatus.objects.get(status='archived')
        curation_status = CourseStatus.objects.get(status='curation')
    except CourseStatus.DoesNotExist:
        draft_status = published_status = archive_status = curation_status = None

    draft_count = courses.filter(status_course=draft_status).count() if draft_status else 0
    published_count = courses.filter(status_course=published_status).count() if published_status else 0
    archive_count = courses.filter(status_course=archive_status).count() if archive_status else 0
    curation_count = courses.filter(status_course=curation_status).count() if curation_status else 0

    # 11️⃣ Render
    return render(request, 'courses/course_view_tim.html', {
        'page_obj': page_obj,
        'course_filter': course_filter,
        'all_count': courses.count(),
        'draft_count': draft_count,
        'published_count': published_count,
        'archive_count': archive_count,
        'curation_count': curation_count
    })


@login_required
def user_detail(request, user_id):
    # Ambil pengguna berdasarkan user_id
    user = get_object_or_404(CustomUser, id=user_id)

    # Ambil daftar enrollment untuk pengguna ini
    enrollments = Enrollment.objects.filter(user=user).select_related('course')

    # Implementasi pencarian berdasarkan course_name
    search_query = request.GET.get('search', '')
    if search_query:
        enrollments = enrollments.filter(course__course_name__icontains=search_query)

    # Siapkan data untuk pagination
    course_details = []
    for enrollment in enrollments:
        course = enrollment.course

        # Ambil total skor dan status dari setiap kursus
        total_max_score = Decimal(0)
        total_score = Decimal(0)
        all_assessments_submitted = True  # Untuk memastikan semua asesmen diselesaikan

        # Ambil grade range untuk kursus tersebut
        grade_range = GradeRange.objects.filter(course=course).first()
        passing_threshold = grade_range.min_grade if grade_range else Decimal(50)  # Default jika tidak ada grade range

        # Hitung skor dari asesmen
        assessments = Assessment.objects.filter(section__courses=course)
        for assessment in assessments:
            score_value = Decimal(0)
            total_correct_answers = 0
            total_questions = assessment.questions.count()

            if total_questions > 0:  # Multiple choice
                answers_exist = False
                for question in assessment.questions.all():
                    answers = QuestionAnswer.objects.filter(question=question, user=user)
                    if answers.exists():
                        answers_exist = True
                    total_correct_answers += answers.filter(choice__is_correct=True).count()
                if not answers_exist:
                    all_assessments_submitted = False
                if total_questions > 0:
                    score_value = (Decimal(total_correct_answers) / Decimal(total_questions)) * Decimal(assessment.weight)

            total_max_score += assessment.weight
            total_score += score_value

        # Hitung persentase skor
        overall_percentage = (total_score / total_max_score) * 100 if total_max_score > 0 else 0

        # Ambil progress dari CourseProgress
        course_progress = CourseProgress.objects.filter(user=user, course=course).first()
        progress_percentage = course_progress.progress_percentage if course_progress else Decimal(0)

        # Tentukan status kelulusan
        status = "Fail"  # Default status
        if progress_percentage == 100 and all_assessments_submitted and overall_percentage >= passing_threshold:
            status = "Pass"

        # Tambahkan detail kursus ke daftar
        course_details.append({
            'course_name': course.course_name,
            'total_score': total_score,
            'total_max_score': total_max_score,
            'status': status,
            'progress_percentage': progress_percentage,  # Untuk debug atau tampilan
            'overall_percentage': overall_percentage,    # Untuk debug atau tampilan
        })

    # Pagination untuk hasil kursus
    paginator = Paginator(course_details, 5)  # 5 kursus per halaman
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'user': user,
        'course_details': page_obj,
        'search_query': search_query,
    }
    
    return render(request, 'authentication/user_detail.html', context)


def filter_courses_by_query(request, posts):
    """Filter courses based on search query."""
    query = request.GET.get('q')
    if query is not None and query !='':
        posts = posts.filter(Q(course_name__icontains=query) | Q(status_course__icontains=query)).distinct()
    return posts

def paginate_courses(request, posts):
    """Paginate the course list."""
    paginator = Paginator(posts, 5)
    page_number = request.GET.get('page')
    return paginator.get_page(page_number)


#create course
#@login_required

def course_create_view(request):
    # Check if the user is authenticated
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)

    if request.user.is_partner or request.user.is_superuser or request.user.is_instructor or request.user.is_curation:
        if request.method == 'POST':
            form = CourseForm(request.POST, user=request.user)  # Pass the logged-in user to the form

            if form.is_valid():
                course = form.save(commit=False)  # Create a Course instance but don't save to the database yet

                # Set the author to the logged-in user
                course.author = request.user
                
                # If the user is a partner or superuser, set the org_partner
                if request.user.is_superuser or request.user.is_partner or request.user.is_curation:
                    partner = form.cleaned_data['org_partner']  # Get the selected partner from the form
                    course.org_partner = partner  # Set the partner for the course

                # If the user is an instructor, set the instructor
                if request.user.is_instructor:
                    instructor = Instructor.objects.get(user=request.user)  # Assuming a one-to-one relationship
                    course.instructor = instructor

                # Set status_course programmatically (e.g., default to 'draft')
                try:
                    draft_status = CourseStatus.objects.get(status='draft')
                except CourseStatus.DoesNotExist:
                    draft_status = None  # Or provide a default value or take any other action

                #draft_status = CourseStatus.objects.get(status='draft')  # Assuming 'draft' exists in CourseStatus
                course.status_course = draft_status  # Set the default status

                # Save the course instance to the database
                course.save()

                return redirect('/courses/')  # Redirect to a course list page or success page
            else:
                print(form.errors)  # Print form errors to the console for debugging
        else:
            form = CourseForm(user=request.user)  # Pass the logged-in user to the form

    else:
        return redirect('/courses/')

    return render(request, 'courses/course_add.html', {'form': form})


#add new category
def category_create_view(request):
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)

    if request.method == "POST":
        form = CategoryForm(request.POST)
        if form.is_valid():
            category = form.save(commit=False)
            category.user = request.user  # <--- Tambahkan ini
            category.save()
            messages.success(request, "Category created successfully.") 
            return redirect('/course-add/')  # Redirect to a course list page or success page
    else:
        form = CategoryForm()

    return render(request, 'courses/category_add.html', {'form': form})

#studio detail courses


class CKEditorForm(forms.Form):
    description = forms.CharField(widget=CKEditor5Widget(config_name='extends'), required=False)


def studio(request, id):
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)
    
    UserActivityLog.objects.create(user=request.user, activity_type='course_learn')
    user = request.user
    course = None
    team_member = None  # inisialisasi
    
    # 1️⃣ Prioritas superuser / curation
    if user.is_superuser or user.is_curation:
        course = get_object_or_404(Course, id=id)
    
    # 2️⃣ Partner / instructor hanya jika course belum ditemukan
    if not course and user.is_partner:
        course = get_object_or_404(Course, id=id, org_partner__user_id=user.id)
    
    if not course and user.is_instructor:
        course = get_object_or_404(Course, id=id, instructor__user_id=user.id)

    # 3️⃣ CourseTeam sebagai fallback
    if not course:
        team_member = CourseTeam.objects.filter(course_id=id, user=user).first()
        if team_member:
            course = team_member.course
        else:
            return redirect('/courses')  # user tidak punya akses
    
    # Fetch sections
    sections = Section.objects.filter(
        parent=None, courses=course
    ).prefetch_related('materials', 'assessments')

    form = CKEditorForm()
    
    return render(request, 'courses/course_detail.html', {
        'course': course,
        'section': sections,
        'form': form,
        'user_role': getattr(team_member, 'role', None)
    })



@csrf_exempt
@require_http_methods(["POST"])
def ckeditor_delete_image(request):
    try:
        url = request.POST.get('url')
        if not url:
            return JsonResponse({'error': 'No URL provided'}, status=400)

        # Pastikan URL adalah absolute (dari CKEditor biasanya begitu)
        parsed = urlparse(url)
        if parsed.netloc:  # ada domain → absolute URL
            # Ambil hanya path-nya
            path = parsed.path
        else:
            path = url  # sudah path relatif

        # Hilangkan query string jika ada (kadang CKEditor nambah ?ckcsrf=xxx)
        path = path.split('?')[0]

        # Bangun path file di server
        file_path = os.path.join(settings.MEDIA_ROOT, path.lstrip('/'))

        if os.path.isfile(file_path):
            os.remove(file_path)
            return JsonResponse({'message': 'Deleted'})
        else:
            # Debug: lihat path yang salah
            return JsonResponse({'error': 'File not found', 'debug_path': file_path}, status=404)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)




def convert_image_to_webp(uploaded_image):
    img = Image.open(uploaded_image)
    img = img.convert('RGB')  # Ensure RGB
    buffer = BytesIO()
    img.save(buffer, format='WEBP', quality=85)
    buffer.seek(0)
    return ContentFile(buffer.read(), name='logo.webp')

@login_required
def update_partner(request, partner_id):
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)

    if not request.user.is_superuser and not request.user.is_staff:
        return redirect('/')

    partner = get_object_or_404(Partner, pk=partner_id)

    if not request.user.is_superuser and request.user != partner.user:
        return redirect('/')

    try:
        old_logo = partner.logo.path
    except (ValueError, AttributeError):
        old_logo = None

    old_user = partner.user

    if request.method == "POST":
        form = PartnerForm(request.POST, request.FILES, instance=partner)
        if form.is_valid():
            partner_instance = form.save(commit=False)

            # Handle logo conversion to WebP
            if 'logo' in request.FILES:
                uploaded_logo = request.FILES['logo']
                partner_instance.logo = convert_image_to_webp(uploaded_logo)

            partner_instance.save()

            # Update user relation if changed
            if old_user and old_user.id != partner_instance.user.id:
                old_user.is_partner = False
                old_user.save()

                partner_instance.user.is_partner = True
                partner_instance.user.save()

            # Delete old logo if updated
            try:
                if old_logo and old_logo != partner_instance.logo.path and os.path.exists(old_logo):
                    os.remove(old_logo)
            except (ValueError, AttributeError):
                pass

            return redirect('courses:partner_detail', partner_id=partner.id)
        else:
            logger.warning("Form errors: %s", form.errors)
    else:
        form = PartnerForm(instance=partner)

    return render(request, 'partner/update_partner.html', {
        'form': form,
        'partner': partner
    })

#partner view
#@cache_page(60 * 5)  # Aktifkan cache kalau sudah siap

def partnerView(request):
    if not request.user.is_authenticated:
        return redirect(f"/login/?next={request.path}")

    query = request.GET.get('q', '')

    # Filter partners by user role
    # Filter partners by user role
    if request.user.is_superuser or getattr(request.user, 'is_finance', False):
        partners = Partner.objects.all()
    else:
        partners = Partner.objects.filter(user_id=request.user.id)

    # Filter berdasarkan query pencarian
    if query:
        partners = partners.filter(
            Q(name__name__icontains=query) |  # ✅ name__name: akses nama universitas dari FK
            Q(user__email__icontains=query) |
            Q(phone__icontains=query)
        )

    # Subquery untuk hitung total saldo partner dari payment yang completed
    payments_subquery = Payment.objects.filter(
        course__org_partner=OuterRef('pk'),  # Pastikan field relasi ini benar sesuai model kamu
        status='completed'
    ).values('course__org_partner').annotate(
        total_earning=Sum('snapshot_partner_earning')
    ).values('total_earning')

    # Annotate partner dengan data statistik dan saldo
    partners = partners.annotate(
        total_courses=Count('courses', distinct=True),
        total_learners=Count('courses__enrollments__user', distinct=True),
        average_rating=Round(Avg('courses__ratings__rating'), 2),
        total_instructors=Count('instructors', distinct=True),
        balance_computed=Coalesce(
            Subquery(payments_subquery, output_field=DecimalField()),
            V(0),
            output_field=DecimalField()
        )
    )

    # Optimasi query relasi yang mungkin akan digunakan di template
    partners = partners.select_related('user').prefetch_related('courses', 'instructors')

    # Pagination
    paginator = Paginator(partners, 10)
    page_number = request.GET.get('page')
    page = paginator.get_page(page_number)

    context = {
        'count': partners.count(),
        'page': page,
        'query': query
    }

    return render(request, 'partner/partner_view.html', context)





@login_required
def partner_detail(request, partner_id):
    partner = get_object_or_404(Partner, id=partner_id)
    user = request.user

    # ==== 🔒 ACCESS CONTROL ====
    # Semua yang boleh lihat: superuser, staff, curation, finance
    has_role_access = (
        user.is_superuser or
        user.is_staff or
        getattr(user, 'is_curation', False) or
        getattr(user, 'is_finance', False)
    )

    # Partner hanya boleh akses data miliknya sendiri
    if not has_role_access:
        if hasattr(user, 'partner_user') and user.partner_user.id != partner.id:
            messages.error(request, "You are not authorized to view this partner detail.")
            return redirect('partner:verify_partner_list')
        elif not hasattr(user, 'partner_user'):
            messages.error(request, "You are not authorized to access this page.")
            return redirect('partner:verify_partner_list')

    # ==== 🧮 DATA AGGREGATION ====
    related_courses = Course.objects.filter(org_partner=partner)
    total_courses = related_courses.count()
    unique_learners = Enrollment.objects.filter(course__in=related_courses).values('user').distinct().count()
    course_ids = related_courses.values_list('id', flat=True)
    total_reviews = CourseRating.objects.filter(course_id__in=course_ids).count()
    average_rating = CourseRating.objects.filter(course_id__in=course_ids).aggregate(
        avg_rating=Avg('rating')
    )['avg_rating'] or 0
    total_instructors = Instructor.objects.filter(courses__org_partner=partner).distinct().count()
    payments = Payment.objects.filter(course__org_partner=partner, status='completed')
    total_payments = payments.count()
    total_payment_amount = payments.aggregate(total_amount=Sum('snapshot_partner_earning'))['total_amount'] or 0

    # ==== LEARNER CLASSIFICATION ====
    enrollments = Enrollment.objects.filter(course__in=related_courses).select_related('user', 'course')
    inbound_learners, outbound_learners, internal_learners = set(), set(), set()
    partner_univ_id = partner.name_id

    for enrollment in enrollments:
        user_univ_id = getattr(enrollment.user, 'university_id', None)
        course_univ_id = enrollment.course.org_partner.name_id if enrollment.course.org_partner else None

        if user_univ_id == partner_univ_id and course_univ_id == partner_univ_id:
            internal_learners.add(enrollment.user.id)
        elif user_univ_id == partner_univ_id and course_univ_id != partner_univ_id:
            outbound_learners.add(enrollment.user.id)
        elif user_univ_id != partner_univ_id and course_univ_id == partner_univ_id:
            inbound_learners.add(enrollment.user.id)

    # ==== CONTEXT ====
    context = {
        'partner': partner,
        'total_courses': total_courses,
        'unique_learners': unique_learners,
        'total_reviews': total_reviews,
        'average_rating': round(average_rating, 1),
        'total_instructors': total_instructors,
        'total_payments': total_payments,
        'total_payment_amount': total_payment_amount,
        'inbound_count': len(inbound_learners),
        'outbound_count': len(outbound_learners),
        'internal_count': len(internal_learners),
    }

    return render(request, 'partner/partner_detail.html', context)

#org partner from lms
logger = logging.getLogger(__name__)



logger = logging.getLogger(__name__)

def org_partner(request, slug):
    partner = get_object_or_404(Partner, name__slug=slug)
    search_query = request.GET.get('search', '')
    selected_category = request.GET.get('category', '')
    sort_by = request.GET.get('sort_by', 'name')

    try:
        published_status = CourseStatus.objects.get(status='published')
    except CourseStatus.DoesNotExist:
        published_status = None

    if published_status:
        now_time = now()  # ✅ Simpan agar tidak dipanggil berulang-ulang
        related_courses = Course.objects.filter(
            org_partner_id=partner.id,
            status_course=published_status,
            end_enrol__gte=now_time
        ).select_related(
            'category', 'instructor__user', 'org_partner'
        ).prefetch_related('enrollments')

        if search_query:
            related_courses = related_courses.filter(course_name__icontains=search_query)

        if selected_category:
            related_courses = related_courses.filter(category__name=selected_category)

        if sort_by == 'learners':
            related_courses = related_courses.annotate(
                total_enrollments=Count('enrollments')
            ).order_by('-total_enrollments')
        elif sort_by == 'date':
            related_courses = related_courses.order_by('created_at')
        else:
            related_courses = related_courses.order_by('course_name')

        categories = Category.objects.filter(
            category_courses__org_partner_id=partner.id,
            category_courses__status_course=published_status,
            category_courses__end_enrol__gte=now_time
        ).annotate(course_count=Count('category_courses')).distinct()
    else:
        related_courses = Course.objects.none()
        categories = Category.objects.none()

    # Pagination
    page_number = request.GET.get('page')
    paginator = Paginator(related_courses, 10)
    page_obj = paginator.get_page(page_number)

    unique_learners = related_courses.aggregate(
        unique_users=Count('enrollments__user', distinct=True)
    )['unique_users'] or 0

    total_reviews = 0
    total_rating_sum = 0
    courses_data = []
    total_enrollments = 0

    for course in page_obj:
        try:
            num_enrollments = course.enrollments.count()
        except AttributeError as e:
            logger.error(f"Error accessing enrollments for course {course.course_name}: {str(e)}")
            num_enrollments = 0

        total_enrollments += num_enrollments

        review_qs = CourseRating.objects.filter(course=course)
        review_count = review_qs.count()
        total_reviews += review_count
        total_rating_sum += review_qs.aggregate(total_rating=Sum('rating'))['total_rating'] or 0

        average_rating = round(total_rating_sum / review_count, 1) if review_count > 0 else 0
        full_stars = int(average_rating)
        half_star = (average_rating % 1) >= 0.5
        empty_stars = 5 - full_stars - (1 if half_star else 0)

        course_data = {
            'course_name': course.course_name,
            'hour': course.hour,
            'course_id': course.id,
            'num_enrollments': num_enrollments,
            'course_slug': course.slug,
            'course_image': course.image.url if course.image else None,
            'instructor': course.instructor.user.get_full_name() if course.instructor else None,
            'instructor_username': course.instructor.user.username if course.instructor else None,
            'photo': course.instructor.user.photo.url if course.instructor and course.instructor.user.photo else None,
            'partner': course.org_partner.name if course.org_partner else None,
            'partner_kode': course.org_partner.name.kode if course.org_partner else None,
            'category': course.category.name if course.category else None,
            'language': course.language,
            'average_rating': average_rating,
            'review_count': review_count,
            'full_star_range': range(full_stars),
            'half_star': half_star,
            'empty_star_range': range(empty_stars),
        }
        courses_data.append(course_data)

    average_rating_all_courses = round(total_rating_sum / total_reviews, 1) if total_reviews > 0 else 0

    context = {
        'partner': partner,
        'page_obj': page_obj,
        'courses': courses_data,
        'total_courses': related_courses.count(),
        'unique_learners': unique_learners,
        'total_enrollments': total_enrollments,
        'total_reviews': total_reviews,
        'average_rating': average_rating_all_courses,
        'search_query': search_query,
        'selected_category': selected_category,
        'categories': list(categories.values('id', 'name', 'course_count')),
        'sort_by': sort_by,
    }

    return render(request, 'partner/org_partner.html', context)







class UserAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return CustomUser.objects.none()

        qs = CustomUser.objects.filter(is_active=True)

        if self.q:
            qs = qs.filter(username__icontains=self.q)

        return qs.only('id', 'username')[:50]

class UniversitiAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return Universiti.objects.none()

        qs = Universiti.objects.all()

        if self.q:
            qs = qs.filter(name__icontains=self.q)

        return qs.only('id', 'name')[:50]

@login_required
def partner_create_view(request):
    # Hanya superuser dan staff yang diizinkan
    if not request.user.is_superuser and not request.user.is_staff:
        return redirect('/')

    if request.method == 'POST':
        form = PartnerForm(request.POST, request.FILES)  # Tambahkan request.FILES
        if form.is_valid():
            partner = form.save(commit=False)
            partner.author_id = request.user.id
            partner.save()

            # Set user sebagai partner
            user = partner.user
            user.is_partner = True
            user.save()

            return redirect('/partner')
    else:
        form = PartnerForm()

    return render(request, 'partner/partner_add.html', {'form': form})


#contoh ajax
def course_create(request):
    data = dict()
    
    # Check if it's a POST request
    if request.method == 'POST':
        form = CourseForm(request.POST)
        
        if form.is_valid():
            # Save the new course if the form is valid
            form.save()
            data['form_is_valid'] = True
            
            # Fetch the updated course list after adding a new course
            courses = Course.objects.all()  # Corrected from Course.all() to Course.objects.all()
            data['course_list'] = render_to_string('courses/course_list.html', {'courses': courses})
        else:
            # Form is not valid, send this info back
            data['form_is_valid'] = False
    else:
        # For GET request, create an empty form
        form = CourseForm()
    
    # Render the course creation form
    context = {'form': form}
    data['html_form'] = render_to_string('courses/course_create.html', context, request=request)
    
    return JsonResponse(data)

# Delete Book
def course_delete(request, pk):
    courses = get_object_or_404(Course, pk=pk)
    data = dict()
    if request.method == 'POST':
        courses.delete()
        data['form_is_valid'] = True
        books = Course.objects.all()
        data['course_list'] = render_to_string('courses/course_list.html', {'courses': courses})
    return JsonResponse(data)

# View to fetch the list of books (for initial load)
@cache_page(60 * 15)
def course_list(request):
    courses = Course.objects.all()[:100]
    return render(request, 'courses/course_list.html', {'courses': courses})


#add course team



def course_team(request, course_id):
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)

    course = get_object_or_404(Course, id=course_id)

    if request.user != course.instructor.user:
        messages.error(request, "You are not authorized to add team members to this course, instructor only.")
        return redirect('courses:course_view')

    if request.method == 'POST':
        form = CourseTeamForm(request.POST, course=course)
        if form.is_valid():
            form.save()
            messages.success(request, "Team members added successfully.")
            return redirect('courses:course_team', course_id=course.id)
    else:
        form = CourseTeamForm(course=course)

    # Ambil semua tim yang sudah ada
    team_members = CourseTeam.objects.filter(course=course)

    return render(request, 'courses/course_team.html', {
        'form': form,
        'course': course,
        'team_members': team_members,  # kirim ke template
    })

def course_team_remove(request, course_id, member_id):
    course = get_object_or_404(Course, id=course_id)
    
    # Pastikan user instruktur
    if request.user != course.instructor.user:
        messages.error(request, "You are not authorized to remove team members.")
        return redirect('courses:course_team', course_id=course.id)
    
    member = get_object_or_404(CourseTeam, id=member_id, course=course)
    member.delete()
    messages.success(request, f"{member.user.username} has been removed from the team.")
    return redirect('courses:course_team', course_id=course.id)

