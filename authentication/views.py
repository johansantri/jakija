# authentication/views.py
from django.shortcuts import render, redirect,get_object_or_404
import os
from math import ceil
import sys
import pickle
from datetime import timedelta
from django.utils.http import urlencode
import hashlib
from PIL import Image
from io import BytesIO
from django.core.files.base import ContentFile
from django.contrib.auth import authenticate, login,logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse,HttpResponseNotAllowed
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.contrib.auth.tokens import default_token_generator
from .forms import RegistrationForm,LoginForm
from django.conf import settings
from django.contrib import messages
from .models import CustomUser
from django.contrib.auth.forms import PasswordResetForm,SetPasswordForm
from django.contrib.auth.views import PasswordResetView, PasswordResetDoneView, PasswordResetConfirmView, PasswordResetCompleteView
from django.urls import reverse
from django.core.mail import send_mail
from authentication.forms import  UserProfileForm, UserPhoto,PasswordResetForms
from .models import Profile
from courses.models import QuizResult,Quiz,LTIResult,Certificate,Comment,LastAccessCourse,UserActivityLog,SearchHistory,Instructor,CourseRating,Partner,Assessment,GradeRange,AssessmentRead,Material, MaterialRead, Submission,AssessmentScore,QuestionAnswer,CourseStatus,Enrollment,MicroCredential, MicroCredentialEnrollment,Course, Enrollment, Category,CourseProgress
from .forms import CommentForm
from django.http import HttpResponse,JsonResponse
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import HttpResponseForbidden
from django.core.cache import cache
from .utils import get_client_ip, get_geo_from_ip
from django.db.models import Avg, Count,Q,FloatField,Case, When, CharField, Value
from django.core import serializers
import random
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect
from decimal import Decimal
from django.urls import reverse
from django_ratelimit.decorators import ratelimit
from django.http import HttpResponseNotAllowed, HttpResponseNotFound

from django.views.decorators.cache import cache_page
from django.db.models import Prefetch
from django.core.mail import EmailMultiAlternatives,EmailMessage
from django.db.models.functions import Coalesce
from blog.models import BlogPost
from django.views.decorators.http import require_GET
import html
import re
from django.utils.timezone import now
from django.views.decorators.http import require_http_methods
import logging
from django.views.decorators.vary import vary_on_headers
from django.core.exceptions import ValidationError
from django.http import HttpResponseServerError, HttpResponseBadRequest
from django.db import DatabaseError
from django.utils.text import slugify


from django.core.paginator import Paginator
from django.shortcuts import render
import time
from authentication.utils import calculate_course_status 
from django.views.decorators.http import require_POST
from authentication.utils import is_user_online,get_total_online_users  # fungsi cek online

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

# Placeholder validation functions (adjust based on your implementation)
def validate_category_ids(raw_categories):
    return [int(c) for c in raw_categories if c.isdigit()]

def validate_language(language):
    if language in dict(Course.choice_language):
        return language
    raise ValidationError("Invalid language")

def validate_level(level):
    if level in ['basic', 'middle', 'advanced']:
        return level
    raise ValidationError("Invalid level")

def validate_price_filter(price_filter):
    if price_filter in ['free', 'paid', '']:
        return price_filter
    raise ValidationError("Invalid price filter")


@custom_ratelimit
def about(request):
    return render(request, 'home/about.html')


logger = logging.getLogger(__name__)

@custom_ratelimit
@login_required
def mycourse(request):
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
        messages.warning(request, f"Please fill in the following required information: {', '.join(missing_fields)}")
        return redirect('authentication:edit-profile', pk=user.pk)

    if request.method != 'GET':
        return HttpResponseNotAllowed(['GET'])

    search_query = request.GET.get('search', '')
    enrollments_page = request.GET.get('enrollments_page', 1)

    enrollments = Enrollment.objects.filter(user=user).select_related('course').order_by('-enrolled_at')

    if search_query:
        enrollments = enrollments.filter(
            Q(user__username__icontains=search_query) |
            Q(course__course_name__icontains=search_query)
        )

    total_enrollments = enrollments.count()

    active_courses = Course.objects.filter(
        id__in=enrollments.values('course'),
        status_course__status='published',
        start_enrol__lte=timezone.now(),
        end_enrol__gte=timezone.now()
    )

    completed_courses = CourseProgress.objects.filter(user=user, progress_percentage=100)

    enrollments_data = []

    # ===========================================================
    # LOOP ENROLLMENTS — UPDATED SCORING LOGIC
    # ===========================================================
    for enrollment in enrollments:
        course = enrollment.course

        # ----------------------------------------
        # MATERIAL PROGRESS
        # ----------------------------------------
        materials = Material.objects.filter(section__courses=course)
        total_materials = materials.count()
        materials_read = MaterialRead.objects.filter(user=user, material__in=materials).count()

        materials_read_percentage = (
            (Decimal(materials_read) / Decimal(total_materials)) * 100
            if total_materials > 0 else Decimal('0')
        )

        # ----------------------------------------
        # ASSESSMENT PROGRESS
        # ----------------------------------------
        assessments = Assessment.objects.filter(section__courses=course)
        total_assessments = assessments.count()
        assessments_completed = AssessmentRead.objects.filter(
            user=user, assessment__in=assessments
        ).count()

        assessments_completed_percentage = (
            (Decimal(assessments_completed) / Decimal(total_assessments)) * 100
            if total_assessments > 0 else Decimal('0')
        )

        progress = (
            (materials_read_percentage + assessments_completed_percentage) / 2
            if (total_materials + total_assessments) > 0 else Decimal('0')
        )

        # UPDATE COURSE PROGRESS
        course_progress, _ = CourseProgress.objects.get_or_create(user=user, course=course)
        if course_progress.progress_percentage != progress:
            course_progress.progress_percentage = progress
            course_progress.save()
            logger.debug(f"Updated progress for user {user.id}, course {course.id}: {progress}%")

        # ----------------------------------------
        # SCORING — NEW LOGIC (SAMA DGN DASHBOARD)
        # ----------------------------------------
        total_score = Decimal('0')
        total_max_score = Decimal('0')

        for assessment in assessments:
            weight = Decimal(assessment.weight)
            score_value = Decimal('0')

            # ========== CASE 1: LTI ==========
            lti_res = LTIResult.objects.filter(user=user, assessment=assessment).first()
            if lti_res and lti_res.score is not None:
                raw_score = Decimal(lti_res.score)
                if raw_score > 1:
                    raw_score = raw_score / 100
                score_value = raw_score * weight

            else:
                # ========== CASE 2: In-Video Quiz ==========
                invideo_quizzes = Quiz.objects.filter(assessment=assessment)
                if invideo_quizzes.exists():
                    quiz_result = QuizResult.objects.filter(user=user, assessment=assessment).first()
                    if quiz_result and quiz_result.total_questions > 0:
                        raw_percent = Decimal(quiz_result.score) / Decimal(quiz_result.total_questions)
                        score_value = raw_percent * weight
                    else:
                        score_value = Decimal('0')

                else:
                    # ========== CASE 3: OLD MCQ ==========
                    total_questions = assessment.questions.count()
                    if total_questions > 0:
                        correct = 0
                        for q in assessment.questions.all():
                            correct += QuestionAnswer.objects.filter(
                                question=q, user=user, choice__is_correct=True
                            ).count()
                        score_value = (Decimal(correct) / Decimal(total_questions)) * weight

                    else:
                        # ========== CASE 4: ASKORA ==========
                        submissions = Submission.objects.filter(askora__assessment=assessment, user=user)
                        if submissions.exists():
                            latest = submissions.order_by('-submitted_at').first()
                            sc = AssessmentScore.objects.filter(submission=latest).first()
                            if sc:
                                score_value = Decimal(sc.final_score)

            # clamp max score
            score_value = min(score_value, weight)

            total_score += score_value
            total_max_score += weight

        # FINAL PERCENTAGE
        overall_percentage = (
            (total_score / total_max_score) * 100
            if total_max_score > 0 else Decimal('0')
        )

        grade_range = GradeRange.objects.filter(course=course, name='Pass').first()
        passing_threshold = grade_range.min_grade if grade_range else Decimal('52.00')

        certificate_eligible = (
            progress == Decimal('100') and overall_percentage >= passing_threshold
        )
        certificate_issued = getattr(enrollment, 'certificate_issued', False)

        has_reviewed = CourseRating.objects.filter(user=user, course=course).exists()

        # DEBUG LAST ACCESS
        last_access = LastAccessCourse.objects.filter(user=user, course=course).first()
        logger.debug(
            f"[MYCOURSE] Course {course.id}: progress={progress}%, "
            f"last_access_material={last_access.material_id if last_access and last_access.material else None}, "
            f"last_access_assessment={last_access.assessment_id if last_access and last_access.assessment else None}"
        )

        enrollments_data.append({
            'enrollment': enrollment,
            'progress': float(progress),
            'certificate_eligible': certificate_eligible,
            'certificate_issued': certificate_issued,
            'overall_percentage': float(overall_percentage),
            'passing_threshold': float(passing_threshold),
            'has_reviewed': has_reviewed,
        })

    # PAGINATE
    enrollments_paginator = Paginator(enrollments_data, 5)
    enrollments_page_obj = enrollments_paginator.get_page(enrollments_page)

    # LAST ACCESS MAP
    last_access_list = LastAccessCourse.objects.filter(user=user).select_related('material', 'assessment', 'course')
    last_access_map = {la.course_id: la for la in last_access_list}

    

    # LICENSE
    today = timezone.now().date()
    user_licenses = user.licenses.all()
    for lic in user_licenses:
        lic.is_active = lic.start_date <= today <= lic.expiry_date

    return render(request, 'learner/mycourse_list.html', {
        'page_obj': enrollments_page_obj,
        'search_query': search_query,
        'total_enrollments': total_enrollments,
        'active_courses': active_courses,
        'completed_courses': completed_courses,
        'last_access_map': last_access_map,
    })

@custom_ratelimit
@login_required
def microcredential_list(request):
    if request.method != 'GET':
        return HttpResponseNotAllowed(['GET'])

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

    # Ambil data microcredential user
    microcredentials = MicroCredentialEnrollment.objects.filter(user=user)

    # Pencarian
    search_query = request.GET.get('search', '')
    if search_query:
        microcredentials = microcredentials.filter(
            Q(microcredential__title__icontains=search_query)
        )

    microcredentials = microcredentials.order_by('microcredential__title')

    # Pagination
    paginator = Paginator(microcredentials, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'learner/microcredential_list.html', {
        'page_obj': page_obj,
        'search_query': search_query
    })

logger = logging.getLogger(__name__)

# Fungsi untuk menghasilkan kunci rate-limiting
def get_ratelimit_key(group, request):
    user_agent = request.META.get('HTTP_USER_AGENT', 'unknown')
    key = f"{request.META.get('REMOTE_ADDR')}:{user_agent}"
    logger.debug("Rate limit key generated: %s", key)
    return key

# Fungsi validasi untuk language
def validate_language(value):
    if value not in dict(Course.choice_language):
        raise ValidationError(f"Invalid language: {value}")
    return value

# Fungsi validasi untuk level
def validate_level(value):
    valid_levels = ['beginner', 'intermediate', 'advanced']  # Sesuaikan dengan model
    if value not in valid_levels:
        raise ValidationError(f"Invalid level: {value}")
    return value

# Fungsi validasi untuk category_filter
def validate_category_ids(category_ids):
    try:
        # Konversi ke integer dan pastikan valid
        valid_ids = [int(cat_id) for cat_id in category_ids if cat_id.strip()]
        # Verifikasi bahwa ID ada di database
        existing_ids = set(Category.objects.filter(id__in=valid_ids).values_list('id', flat=True))
        return [cat_id for cat_id in valid_ids if cat_id in existing_ids]
    except (ValueError, TypeError):
        return []


logger = logging.getLogger(__name__)


def validate_level(level):
    valid_levels = [choice[0] for choice in Course._meta.get_field('level').choices]
    if level in valid_levels:
        return level
    raise ValidationError(f"Invalid level: {level}")

@custom_ratelimit
def course_list(request):
    try:
        if request.method != 'GET':
            return HttpResponseNotAllowed(['GET'])

        # Get filter parameters
        raw_category_filter = request.GET.getlist('category')[:10]
        language_filter = request.GET.get('language', '').strip()
        level_filter = request.GET.get('level', '').strip()
        price_filter = request.GET.get('price', '').strip()

        # Validate filters
        category_filter = validate_category_ids(raw_category_filter)
        if raw_category_filter and not category_filter:
            logger.warning(f"Invalid category filter: {raw_category_filter}")
            return HttpResponseBadRequest("Invalid category filter")

        if language_filter:
            try:
                language_filter = validate_language(language_filter)
            except ValidationError as e:
                logger.warning(f"Invalid language filter: {language_filter}")
                return HttpResponseBadRequest(str(e))
        else:
            language_filter = None

        if level_filter:
            try:
                level_filter = validate_level(level_filter)
            except ValidationError as e:
                logger.warning(f"Invalid level filter: {level_filter}")
                return HttpResponseBadRequest(str(e))
        else:
            level_filter = None

        if price_filter:
            try:
                price_filter = validate_price_filter(price_filter)
            except ValidationError as e:
                logger.warning(f"Invalid price filter: {price_filter}")
                return HttpResponseBadRequest(str(e))
        else:
            price_filter = None

        # Validate page number
        try:
            page_number = int(request.GET.get('page', 1))
            if page_number < 1 or page_number > 100:
                raise ValueError
        except ValueError:
            logger.warning(f"Invalid page number: {request.GET.get('page')}")
            return HttpResponseBadRequest("Invalid page number")

        # Get published status
        try:
            published_status = CourseStatus.objects.filter(status='published').first()
            if not published_status:
                raise CourseStatus.DoesNotExist
        except CourseStatus.DoesNotExist:
            logger.warning("Published status 'published' tidak ditemukan.")
            messages.error(request, "Status 'published' belum tersedia. Silakan coba lagi nanti.")
            return redirect('authentication:home')


        # Query courses
        courses = Course.objects.filter(
            status_course=published_status,
            end_date__gte=timezone.now()
        ).select_related(
            'category', 'instructor__user', 'org_partner'
        ).prefetch_related('enrollments', 'prices')

        # Apply filters
        if category_filter:
            courses = courses.filter(category__id__in=category_filter)
        if language_filter:
            courses = courses.filter(language=language_filter)
        if level_filter:
            courses = courses.filter(level=level_filter)
        if price_filter == 'free':
            courses = courses.filter(prices__portal_price=0)
        elif price_filter == 'paid':
            courses = courses.filter(prices__portal_price__gt=0)

        courses = courses.annotate(
            avg_rating=Avg('ratings__rating', default=0),
            enrollment_count=Count('enrollments', distinct=True),
            review_count=Count('ratings', distinct=True),
            language_display=Case(
                *[When(language=k, then=Value(v)) for k, v in Course.choice_language],
                output_field=CharField(),
                default=Value('Unknown')
            )
        ).values(
            'course_name', 'hour', 'id', 'slug', 'image',
            'instructor__user__first_name', 'instructor__user__last_name', 'instructor__user__username',
            'instructor__user__photo', 'org_partner__name__name', 'org_partner__name__slug', 'org_partner__logo',
            'category__name', 'language', 'level', 'avg_rating', 'enrollment_count', 'review_count', 'language_display'
        )
        courses = list(courses)

        # Get total courses
        total_courses = len(courses)

        # Pagination
        paginator = Paginator(courses, 9)
        try:
            page_obj = paginator.get_page(page_number)
        except (PageNotAnInteger, EmptyPage):
            page_obj = paginator.get_page(1)

        # Get categories
        categories = Category.objects.filter(
            category_courses__status_course=published_status,
            category_courses__end_enrol__gte=timezone.now()
        ).annotate(course_count=Count('category_courses')).distinct().order_by('name')[:50].values('id', 'name', 'course_count')
        categories = list(categories)

        # Get language options
        language_codes = sorted(set(c['language'] for c in courses if c['language']))[:50]
        all_languages = dict(Course.choice_language)
        language_options = [{'code': code, 'name': all_languages.get(code, code)} for code in language_codes]

        # Get level options from model choices
        LEVEL_CHOICES = [
            ('basic', 'Basic'),
            ('middle', 'Middle'),
            ('advanced', 'Advanced'),
        ]
        all_levels = dict(LEVEL_CHOICES)
        level_options = [{'code': k, 'name': v} for k, v in all_levels.items()]

        # Process courses_data with price information
        courses_data = []
        for course in page_obj.object_list:
            try:
                # Fetch CoursePrice for the course
                course_obj = Course.objects.filter(id=course['id']).prefetch_related('prices').first()
                course_price = course_obj.prices.first() if course_obj else None
                price = course_price.portal_price if course_price else Decimal('0.00')
                is_free = price == Decimal('0.00')
                discount_amount = course_price.discount_amount if course_price else Decimal('0.00')
                normal_price = course_price.normal_price if course_price else Decimal('0.00')
                discount_percent = course_price.discount_percent if course_price else Decimal('0.00')

                course_data = {
                    'course_name': course.get('course_name', 'Unknown'),
                    'hour': course.get('hour', 0),
                    'course_id': course.get('id'),
                    'num_enrollments': course.get('enrollment_count', 0),
                    'course_slug': course.get('slug', ''),
                    'course_image': f"{settings.MEDIA_URL}{course['image']}" if course.get('image') else '/media/default.jpg',
                    'instructor': f"{course.get('instructor__user__first_name', '')} {course.get('instructor__user__last_name', '')}".strip() or 'Unknown',
                    'instructor_username': course.get('instructor__user__username', ''),
                    'photo': f"{settings.MEDIA_URL}{course['instructor__user__photo']}" if course.get('instructor__user__photo') else '/media/default.jpg',
                    'partner': course.get('org_partner__name__name'),
                    'partner_kode': course.get('org_partner__name__kode'),
                    'partner_slug': course.get('org_partner__name__slug'),
                    'org_logo': f"{settings.MEDIA_URL}{course['org_partner__logo']}" if course.get('org_partner__logo') else '/media/default.jpg',
                    'category': course.get('category__name', 'Uncategorized'),
                    'language': course.get('language_display', 'Unknown'),
                    'level': course.get('level', 'Unknown'),
                    'average_rating': round(course.get('avg_rating', 0) or 0, 1),
                    'review_count': course.get('review_count', 0),
                    'full_star_range': range(int(course.get('avg_rating', 0) or 0)),
                    'half_star': (course.get('avg_rating', 0) % 1) >= 0.5 if course.get('avg_rating') else False,
                    'empty_star_range': range(5 - int(course.get('avg_rating', 0) or 0) - (1 if (course.get('avg_rating', 0) % 1) >= 0.5 else 0)),
                    'price': float(price),
                    'is_free': is_free,
                    'discount_amount': float(discount_amount),
                    'normal_price': float(normal_price),
                    'discount_percent': float(discount_percent),
                }

                if not course_data['partner_slug']:
                    logger.debug(f"Course {course_data['course_id']} has no partner_slug or partner_kode")
                courses_data.append(course_data)
            except Exception as e:
                logger.error(f"Error processing course {course.get('id', 'unknown')}: {str(e)}")
                continue

        total_enrollments = sum(c.get('enrollment_count', 0) for c in page_obj.object_list)

        context = {
            'courses': courses_data,
            'page_obj': page_obj,
            'total_courses': total_courses,
            'total_enrollments': total_enrollments,
            'total_pages': paginator.num_pages,
            'current_page': page_obj.number,
            'start_index': page_obj.start_index(),
            'end_index': page_obj.end_index(),
            'category_filter': category_filter,
            'language_filter': language_filter,
            'level_filter': level_filter,
            'price_filter': price_filter,
            'categories': categories,
            'language_options': language_options,
            'level_options': level_options,  # <-- level options here
        }

        return render(request, 'home/course_list.html', context)

    except CourseStatus.DoesNotExist:
        logger.warning("Published status not found")
        messages.warning(request, "Status 'published' belum tersedia.")
        return redirect('authentication:home')

    except DatabaseError:
        logger.exception("Database error in partner_list_view")
        messages.error(request, "Terjadi kesalahan pada server. Silakan coba lagi nanti.")
        return redirect('authentication:home')

    except KeyError as e:
        logger.exception(f"KeyError in partner_list_view: {str(e)}")
        messages.error(request, "Terjadi kesalahan data. Silakan coba lagi nanti.")
        return redirect('authentication:home')

    except Exception as e:
        logger.exception(f"Unexpected error in partner_list_view: {str(e)}")
        messages.error(request, "Terjadi kesalahan yang tidak terduga.")
        return redirect('authentication:home')



@custom_ratelimit
@login_required
@ratelimit(key='ip', rate='100/h')
def user_detail(request, user_id):
    target_user = get_object_or_404(CustomUser, id=user_id)
    current_user = request.user

    # === Validasi akses (tetap sama) ===
    partner_instance = getattr(current_user, 'partner_user', None)
    target_partner_instance = getattr(target_user, 'partner_user', None)
    is_partner_same_org = False
    if partner_instance:
        if target_partner_instance:
            is_partner_same_org = partner_instance.name_id == target_partner_instance.name_id
        else:
            if target_user.university:
                is_partner_same_org = partner_instance.name_id == target_user.university.id

    allowed = (current_user == target_user or current_user.is_superuser or 
               current_user.is_staff or is_partner_same_org)
    if not allowed:
        messages.warning(request, "Access denied.")
        return redirect('authentication:dashbord')

    # === Enrollments ===
    enrollments = Enrollment.objects.filter(user=target_user).select_related('course')
    search_query = request.GET.get('search', '')
    if search_query:
        enrollments = enrollments.filter(course__course_name__icontains=search_query)

    course_details = []
    for enrollment in enrollments:
        course = enrollment.course
        detail = calculate_course_status(target_user, course)  # dict atau object

        # TAMBAHKAN PERSENTASE
        if hasattr(detail, 'total_max_score'):  # kalau object
            max_score = detail.total_max_score or 0
            score = detail.total_score or 0
        else:  # kalau dict
            max_score = detail.get('total_max_score', 0) or 0
            score = detail.get('total_score', 0) or 0

        percentage = (score / max_score * 100) if max_score > 0 else 0
        if hasattr(detail, '__dict__'):  # object
            detail.percentage = round(percentage, 1)
        else:  # dict
            detail['percentage'] = round(percentage, 1)

        course_details.append(detail)

    # === Pagination ===
    paginator = Paginator(course_details, 5)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'user': target_user,
        'course_details': page_obj,
        'search_query': search_query,
    }
    return render(request, 'authentication/user_detail.html', context)
# Fungsi safe_cache_set
def safe_cache_set(key, value, timeout=300):
    try:
        cache.set(key, value, timeout)
    except Exception:
        pass

@ratelimit(key='user', rate='500/h')
@login_required
def all_user(request):
    if not request.user.is_authenticated:
        return redirect(f"/login/?next={request.path}")

    page_number = int(request.GET.get('page', 1))
    PAGE_SIZE = 50

    query_params = request.GET.copy()
    query_params.pop('page', None)
    query_string = urlencode(sorted(query_params.items()))
    query_hash = hashlib.md5(query_string.encode()).hexdigest()
    user_id = request.user.id

    # Cache keys
    cache_key_count = f"user_count:{user_id}:{query_hash}"
    cache_key_page = f"user_page:{user_id}:{query_hash}:{page_number}"
    cache_key_partners = f"user_partners:{user_id}"

    # Ambil dari cache
    total_user_count = cache.get(cache_key_count)
    users = cache.get(cache_key_page)
    partners = cache.get(cache_key_partners)

    if users is None:
        # ========== 1️⃣ Base Query ==============
        base_qs = CustomUser.objects.select_related('university').only(
            'id', 'username', 'email', 'first_name', 'gender', 'date_joined',
            'last_login', 'is_active', 'is_staff', 'is_superuser',
            'is_partner', 'is_instructor', 'is_subscription',
            'university__name'
        )

        # ========== 2️⃣ Role Logic ==============
        if request.user.is_superuser:
            # Superuser bisa lihat semua data
            users_qs = base_qs

            # Cache daftar partner
            if partners is None:
                partners = list(Partner.objects.values('id', 'name'))
                safe_cache_set(cache_key_partners, partners, timeout=300)

        elif request.user.is_partner and request.user.university:
            # Partner: hanya lihat learner di universitasnya sendiri
            users_qs = base_qs.filter(
                university=request.user.university,
                is_superuser=False,
                is_staff=False,      # tidak boleh lihat staff/admin
                is_learner=True
            )
            partners = None

        else:
            # Role lain: hanya lihat dirinya sendiri
            users_qs = base_qs.filter(
                id=request.user.id,
                is_superuser=False,
                is_staff=False
            )
            partners = None

        # ========== 3️⃣ Filter Dinamis ==============
        q = Q()
        search_query = request.GET.get('search', '').strip()
        if search_query:
            q &= (
                Q(username__icontains=search_query)
                | Q(email__icontains=search_query)
                | Q(first_name__icontains=search_query)
            )

        status_filter = request.GET.get('status')
        if status_filter == 'active':
            q &= Q(is_active=True)
        elif status_filter == 'inactive':
            q &= Q(is_active=False)

        date_from = request.GET.get('date_from', '').strip()
        date_to = request.GET.get('date_to', '').strip()
        if date_from:
            q &= Q(date_joined__gte=date_from)
        if date_to:
            q &= Q(date_joined__lte=date_to)

        gender_filter = request.GET.get('gender')
        if gender_filter:
            q &= Q(gender=gender_filter)

        partner_filter = request.GET.get('partner')
        if request.user.is_superuser and partner_filter:
            partner = Partner.objects.filter(id=partner_filter).first()
            if partner:
                q &= Q(university__name=partner.name)

        users_qs = users_qs.filter(q)

        # ========== 4️⃣ Annotate dan Sorting ==============
        users_qs = users_qs.annotate(total_courses=Count('enrollments'))

        sort_courses = request.GET.get('sort_courses')
        if sort_courses == 'most':
            users_qs = users_qs.order_by('-total_courses')
        elif sort_courses == 'least':
            users_qs = users_qs.order_by('total_courses')
        else:
            users_qs = users_qs.order_by('-date_joined')

        # ========== 5️⃣ Cache + Pagination ==============
        if total_user_count is None:
            total_user_count = users_qs.count()
            safe_cache_set(cache_key_count, total_user_count, timeout=300)

        paginator = Paginator(users_qs, PAGE_SIZE)
        page_obj = paginator.get_page(page_number)

        users = list(page_obj.object_list.values(
            'id', 'email', 'first_name', 'gender',
            'date_joined', 'last_login', 'is_active',
            'is_staff', 'is_superuser', 'is_partner', 'is_instructor', 'is_subscription',
            'university__name', 'total_courses'
        ))

        safe_cache_set(cache_key_page, users, timeout=300)

    else:
        paginator = Paginator(range(total_user_count), PAGE_SIZE)
        page_obj = paginator.get_page(page_number)

    # ========== 6️⃣ Render ==============
    context = {
        'users': users,
        'page_obj': page_obj,
        'total_user_count': total_user_count,
        'search_query': request.GET.get('search', ''),
        'status_filter': request.GET.get('status', ''),
        'date_from': request.GET.get('date_from', ''),
        'date_to': request.GET.get('date_to', ''),
        'gender_filter': request.GET.get('gender', ''),
        'partner_filter': request.GET.get('partner', ''),
        'sort_courses': request.GET.get('sort_courses', ''),
        'partners': partners,
    }

    return render(request, 'authentication/all_user.html', context)


@custom_ratelimit
@login_required
@ratelimit(key='ip', rate='100/h')
def dasbord(request):

    user = request.user

    # ======================================================
    # VALIDASI PROFIL LENGKAP (CEPAT, TANPA QUERY TAMBAHAN)
    # ======================================================
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
    ]

    if missing_fields:
        messages.warning(
            request,
            f"Please complete the following information: {', '.join(missing_fields)}"
        )
        return redirect('authentication:edit-profile', pk=user.pk)

    courses_page = request.GET.get('courses_page', 1)
    today = timezone.now().date()

    # ======================================================
    # CACHE STATUS PUBLISHED (JARANG BERUBAH)
    # ======================================================
    publish_status = cache.get('publish_status')
    if publish_status is None:
        publish_status = CourseStatus.objects.filter(status='published').only('id').first()
        cache.set('publish_status', publish_status, 600)

    # ======================================================
    # DEFAULT VALUE (AMAN)
    # ======================================================
    partner_courses = Course.objects.none()
    total_enrollments = 0
    total_courses = 0
    total_instructors = 0
    total_learners = 0
    total_partners = 0
    total_published_courses = 0
    total_certificates = 0
    total_online = 0
    total_offline = 0
    courses_created_today = []

    # ======================================================
    # SUPERUSER / CURATION (GLOBAL DATA)
    # ======================================================
    if user.is_superuser or getattr(user, 'is_curation', False):

        stats = cache.get('dashboard_global_stats')

        if not stats:
            stats = {
                'total_enrollments': Enrollment.objects.count(),
                'total_courses': Course.objects.count(),
                'total_instructors': Instructor.objects.count(),
                'total_learners': CustomUser.objects.filter(is_learner=True).count(),
                'total_partners': Partner.objects.count(),
                'total_certificates': Certificate.objects.count(),
            }
            cache.set('dashboard_global_stats', stats, 600)

        total_enrollments = stats['total_enrollments']
        total_courses = stats['total_courses']
        total_instructors = stats['total_instructors']
        total_learners = stats['total_learners']
        total_partners = stats['total_partners']
        total_certificates = stats['total_certificates']

        if publish_status:
            total_published_courses = Course.objects.filter(
                status_course=publish_status
            ).count()

        partner_courses = Course.objects.only(
            'id', 'course_name', 'created_at'
        )

    # ======================================================
    # PARTNER
    # ======================================================
    elif user.is_partner:
        partner = Partner.objects.filter(user=user).only('id').first()

        if partner:
            partner_courses = Course.objects.filter(
                org_partner=partner
            ).only('id', 'course_name', 'created_at')

            total_courses = partner_courses.count()
            total_enrollments = Enrollment.objects.filter(
                course__org_partner=partner
            ).count()

            total_instructors = Instructor.objects.filter(
                courses__org_partner=partner
            ).distinct().count()

            total_learners = CustomUser.objects.filter(
                enrollments__course__org_partner=partner,
                is_learner=True
            ).distinct().count()

            if publish_status:
                total_published_courses = partner_courses.filter(
                    status_course=publish_status
                ).count()

    # ======================================================
    # INSTRUCTOR
    # ======================================================
    elif user.is_instructor:
        instructor = Instructor.objects.filter(user=user).only('id').first()

        if instructor:
            partner_courses = Course.objects.filter(
                instructor=instructor
            ).only('id', 'course_name', 'created_at')

            total_courses = partner_courses.count()
            total_enrollments = Enrollment.objects.filter(
                course__instructor=instructor
            ).count()

            total_instructors = 1

            total_learners = CustomUser.objects.filter(
                enrollments__course__instructor=instructor,
                is_learner=True
            ).distinct().count()

            if publish_status:
                total_published_courses = partner_courses.filter(
                    status_course=publish_status
                ).count()

    # ======================================================
    # COURSE CREATED TODAY (RINGAN + PAGINATION)
    # ======================================================
    courses_today_qs = partner_courses.filter(
        created_at__date=today
    ).order_by('-created_at')

    paginator = Paginator(courses_today_qs, 5)
    courses_created_today = paginator.get_page(courses_page)

    # ======================================================
    # ONLINE / OFFLINE USER (NO PYTHON LOOP)
    # ======================================================
    if user.is_superuser or user.is_partner:
        online_threshold = timezone.now() - timedelta(minutes=30)

        total_online = CustomUser.objects.filter(
            last_login__gte=online_threshold
        ).count()

        total_users = CustomUser.objects.count()
        total_offline = total_users - total_online

    # ======================================================
    # CONTEXT
    # ======================================================
    context = {
        'courses_page': courses_page,
        'total_enrollments': total_enrollments,
        'total_courses': total_courses,
        'total_instructors': total_instructors,
        'total_learners': total_learners,
        'total_partners': total_partners,
        'total_published_courses': total_published_courses,
        'courses_created_today': courses_created_today,
        'total_online': total_online,
        'total_offline': total_offline,
        'total_certificates': total_certificates,
    }

    return render(request, 'home/dasbord.html', context)



@custom_ratelimit
@login_required
def comments_dashboard(request):
    user = request.user

    if not (user.is_superuser or user.is_partner or user.is_instructor):
        return HttpResponseForbidden("You don't have permission to view this page.")

    try:
        if user.is_superuser:
            comments = Comment.objects.filter(parent=None).select_related(
                'user', 'material', 'material__section', 'material__section__courses'
            ).order_by('-created_at')

        elif user.is_partner:
            partner = Partner.objects.get(user=user)
            comments = Comment.objects.filter(
                material__section__courses__org_partner=partner,
                parent=None
            ).select_related(
                'user', 'material', 'material__section', 'material__section__courses'
            ).order_by('-created_at')

        elif user.is_instructor:
            instructor = Instructor.objects.get(user=user)
            comments = Comment.objects.filter(
                material__section__courses__instructor=instructor,
                parent=None
            ).select_related(
                'user', 'material', 'material__section', 'material__section__courses'
            ).order_by('-created_at')

    except (Partner.DoesNotExist, Instructor.DoesNotExist):
        comments = Comment.objects.none()

    # Pagination setup
    page_number = request.GET.get('page', 1)
    paginator = Paginator(comments, 20)  # 20 comments per page

    try:
        page_obj = paginator.page(page_number)
    except:
        page_obj = paginator.page(1)

    context = {
        'comments_to_review': page_obj.object_list,
        'page_obj': page_obj,
        'form': CommentForm(),
    }

    # If HTMX request, return partial with comments + load more button
    if request.headers.get('Hx-Request') == 'true':
        return render(request, 'admin/partials/comments_load_more.html', context)

    # Normal full page render
    return render(request, 'admin/comments_section.html', context)


@custom_ratelimit
@login_required
@require_POST
@login_required
def reply_comment(request, comment_id):
    parent_comment = get_object_or_404(Comment, id=comment_id)
    content = request.POST.get('content')

    if content:
        reply = Comment.objects.create(
            user=request.user,
            content=content,
            material=parent_comment.material,
            parent=parent_comment,
        )
        return render(request, 'admin/partials/comment_item.html', {'comment': reply})
    else:
        return HttpResponseBadRequest("Isi komentar tidak boleh kosong.")


@custom_ratelimit
@login_required
@require_POST
def delete_comment(request, comment_id):
    comment = get_object_or_404(Comment, id=comment_id)

    if request.user.is_superuser or request.user.is_instructor:
        comment.delete()
        return HttpResponse("", status=200)  # HTMX will use outerHTML to remove it
    return HttpResponseForbidden("You don't have permission to delete this comment.")



def get_recommended_courses(user):
    now = timezone.now()

    # Kursus yang sudah diambil user
    enrolled_courses = Enrollment.objects.filter(user=user).values_list('course_id', flat=True)

    # Kategori dari kursus yang sudah diambil
    enrolled_categories = Course.objects.filter(id__in=enrolled_courses).values_list('category_id', flat=True)

    # Kursus yang sesuai kategori + belum diambil + enrolment masih aktif
    category_courses = Course.objects.annotate(
        avg_rating=Avg('ratings__rating')
    ).filter(
        category_id__in=enrolled_categories,
        status_course__status='published',
        start_enrol__lte=now,
        end_enrol__gte=now
    ).exclude(id__in=enrolled_courses)

    # Kursus populer dan berkualitas (tidak tergantung kategori)
    popular_courses = Course.objects.annotate(
        avg_rating=Avg('ratings__rating')
    ).filter(
        status_course__status='published',
        start_enrol__lte=now,
        end_enrol__gte=now,
        avg_rating__gte=4.0
    ).exclude(id__in=enrolled_courses)

    # Gabungkan dua sumber rekomendasi (tanpa error union)
    combined_courses = (category_courses | popular_courses).distinct()

    # Urutkan berdasarkan kombinasi popularitas dan waktu terbaru
    recommended_courses = combined_courses.order_by('-view_count', '-avg_rating', '-start_enrol')[:10]

    return recommended_courses


@custom_ratelimit
@login_required
@ratelimit(key='ip', rate='100/h')
def dashbord(request):
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
        messages.warning(request, f"Please fill in: {', '.join(missing_fields)}")
        return redirect('authentication:edit-profile', pk=user.pk)

    search_query = request.GET.get('search', '')
    enrollments_page = request.GET.get('enrollments_page', 1)

    enrollments = Enrollment.objects.filter(user=user).order_by('-enrolled_at')

    if search_query:
        enrollments = enrollments.filter(
            Q(user__username__icontains=search_query) |
            Q(course__course_name__icontains=search_query)
        )

    total_enrollments = enrollments.count()

    active_courses = Course.objects.filter(
        id__in=enrollments.values('course'),
        status_course__status='published',
        start_enrol__lte=timezone.now(),
        end_enrol__gte=timezone.now()
    )

    completed_courses = CourseProgress.objects.filter(user=user, progress_percentage=100)

    enrollments_data = []

    # ==========================================================
    # LOOP ENROLLMENT & SCORE PER COURSE
    # ==========================================================
    for enrollment in enrollments:
        course = enrollment.course

        # ---------------------------
        # MATERIAL PROGRESS
        # ---------------------------
        materials = Material.objects.filter(section__courses=course)
        total_materials = materials.count()
        materials_read = MaterialRead.objects.filter(user=user, material__in=materials).count()

        materials_read_percentage = (
            (Decimal(materials_read) / Decimal(total_materials)) * 100
            if total_materials > 0 else Decimal('0')
        )

        assessments = Assessment.objects.filter(section__courses=course)
        total_assessments = assessments.count()
        assessments_completed = AssessmentRead.objects.filter(
            user=user, assessment__in=assessments
        ).count()

        assessments_completed_percentage = (
            (Decimal(assessments_completed) / Decimal(total_assessments)) * 100
            if total_assessments > 0 else Decimal('0')
        )

        progress = (
            (materials_read_percentage + assessments_completed_percentage) / 2
            if (total_materials + total_assessments) > 0 else Decimal('0')
        )

        course_progress, _ = CourseProgress.objects.get_or_create(user=user, course=course)
        course_progress.progress_percentage = progress
        course_progress.save()

        # ---------------------------
        # SCORING (UPDATED VERSION)
        # ---------------------------
        total_score = Decimal('0')
        total_max_score = Decimal('0')

        for assessment in assessments:
            weight = Decimal(assessment.weight)
            score_value = Decimal('0')

            # ==========================
            # CASE 1 — LTI RESULT
            # ==========================
            lti_result = LTIResult.objects.filter(user=user, assessment=assessment).first()

            if lti_result and lti_result.score is not None:
                lti_score = Decimal(lti_result.score)
                if lti_score > 1:
                    lti_score = lti_score / 100
                score_value = lti_score * weight

            else:
                # ==========================
                # CASE 2 — IN-VIDEO QUIZ
                # ==========================
                invideo_quizzes = Quiz.objects.filter(assessment=assessment)

                if invideo_quizzes.exists():
                    quiz_result = QuizResult.objects.filter(user=user, assessment=assessment).first()

                    if quiz_result:
                        if quiz_result.total_questions > 0:
                            raw_percentage = Decimal(quiz_result.score) / Decimal(quiz_result.total_questions)
                            score_value = raw_percentage * weight
                        else:
                            score_value = Decimal('0')
                    else:
                        score_value = Decimal('0')

                else:
                    # ==========================
                    # CASE 3 — OLD MCQ MODEL
                    # ==========================
                    total_questions = assessment.questions.count()

                    if total_questions > 0:
                        total_correct = 0
                        for q in assessment.questions.all():
                            total_correct += QuestionAnswer.objects.filter(
                                question=q, user=user, choice__is_correct=True
                            ).count()

                        score_value = (
                            (Decimal(total_correct) / Decimal(total_questions)) * weight
                            if total_questions > 0 else Decimal('0')
                        )
                    else:
                        # ==========================
                        # CASE 4 — ASKORA
                        # ==========================
                        submissions = Submission.objects.filter(askora__assessment=assessment, user=user)

                        if submissions.exists():
                            latest = submissions.order_by('-submitted_at').first()
                            score_obj = AssessmentScore.objects.filter(submission=latest).first()

                            if score_obj:
                                score_value = Decimal(score_obj.final_score)
                            else:
                                score_value = Decimal('0')
                        else:
                            score_value = Decimal('0')

            # Clamp score ke MAX = weight
            score_value = min(score_value, weight)

            total_score += score_value
            total_max_score += weight

        # ---------------------------
        # FINAL SCORE & CERTIFICATE
        # ---------------------------
        overall_percentage = (
            (total_score / total_max_score) * 100
            if total_max_score > 0 else Decimal('0')
        )

        grade_range = GradeRange.objects.filter(course=course, name='Pass').first()
        passing_threshold = grade_range.min_grade if grade_range else Decimal('52.00')

        certificate_eligible = (
            progress == Decimal('100') and overall_percentage >= passing_threshold
        )

        certificate_issued = getattr(enrollment, 'certificate_issued', False)

        has_reviewed = CourseRating.objects.filter(user=user, course=course).exists()

        enrollments_data.append({
            'enrollment': enrollment,
            'progress': float(progress),
            'certificate_eligible': certificate_eligible,
            'certificate_issued': certificate_issued,
            'overall_percentage': float(overall_percentage),
            'passing_threshold': float(passing_threshold),
            'has_reviewed': has_reviewed,
        })

    # PAGINATION
    enrollments_paginator = Paginator(enrollments_data, 5)
    enrollments_page_obj = enrollments_paginator.get_page(enrollments_page)

    # LICENSES
    today = timezone.now().date()
    user_licenses = user.licenses.all()
    for lic in user_licenses:
        lic.is_active = lic.start_date <= today <= lic.expiry_date

    recommended_courses = get_recommended_courses(user)

    return render(request, 'learner/dashbord.html', {
        'enrollments': enrollments_page_obj,
        'search_query': search_query,
        'enrollments_page': enrollments_page,
        'total_enrollments': total_enrollments,
        'active_courses': active_courses,
        'completed_courses': completed_courses,
        'user_licenses': user_licenses,
        'recommended_courses': recommended_courses,
        'user': user,
    })

@custom_ratelimit
@login_required
@ratelimit(key='ip', rate='100/h')
def pro(request,username):
    if request.user.is_authenticated:
        username=CustomUser.objects.get(username=username)
        instructor = Instructor.objects.filter(user=username).first()

        return render(request,'home/profile.html',{

            'user': username,

            'instructor': instructor,  # This will be None if the user is not an instructor

        })
    return redirect("/login/?next=%s" % request.path)



@custom_ratelimit
@login_required
@ratelimit(key='ip', rate='100/h')
def edit_profile(request, pk):
    profile = get_object_or_404(CustomUser, pk=pk)

    # Pastikan hanya pemilik profil yang bisa mengedit
    if request.user.pk != pk:
        messages.error(request, "You are not authorized to edit this profile.")
        return redirect('authentication:dashbord')

    if request.method == "POST":
        form = UserProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile has been updated.")
            return redirect('authentication:dashbord')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = UserProfileForm(instance=profile)

    return render(request, 'home/edit_profile_form.html', {'form': form, 'user': profile})
#convert image before update

# Fungsi untuk memproses gambar menjadi format WebP
def process_image_to_webp(uploaded_photo):
    # Menggunakan PIL untuk membuka gambar yang diunggah
    img = Image.open(uploaded_photo)
    
    # Membuat buffer untuk menyimpan gambar dalam format WebP
    buffer = BytesIO()
    img.save(buffer, format="WEBP")
    webp_image = buffer.getvalue()  # Ambil data gambar dalam format WebP
    
    # Mengembalikan file gambar dalam format WebP
    return ContentFile(webp_image, name=uploaded_photo.name.split('.')[0] + '.webp')


#update image
@custom_ratelimit
@login_required
@ratelimit(key='ip', rate='100/h')
def edit_photo(request, pk):
    # Mendapatkan pengguna berdasarkan primary key (ID)
    user = get_object_or_404(CustomUser, pk=pk)

    if request.method == "GET":
        # Menampilkan formulir pengeditan foto
        form = UserPhoto(instance=user)
        return render(request, 'home/edit_photo.html', {'form': form})

    elif request.method == "POST":
        # Menyimpan jalur foto lama untuk penghapusan nanti
        old_photo_path = user.photo.path if user.photo else None
        
        # Membuat instance formulir dengan data POST dan file yang diunggah
        form = UserPhoto(request.POST, request.FILES, instance=user)

        if form.is_valid():
            # Simpan perubahan formulir tanpa menyimpan langsung ke DB
            user_profile = form.save(commit=False)

            # Cek jika ada file foto yang diunggah
            if 'photo' in request.FILES:
                uploaded_photo = request.FILES['photo']
                # Proses gambar menjadi format WebP
                processed_photo = process_image_to_webp(uploaded_photo)
                # Update foto pengguna
                user_profile.photo = processed_photo

            # Simpan perubahan pengguna
            user_profile.save()

            # Jika ada foto lama, hapus file lama tersebut
            if old_photo_path and os.path.exists(old_photo_path):
                os.remove(old_photo_path)

            # Redirect setelah berhasil menyimpan perubahan
            return redirect(reverse('authentication:edit-photo', args=[pk]))

        else:
            # Jika form tidak valid, tampilkan kembali form dengan status 400
            return render(request, 'home/edit_photo.html', {'form': form}, status=400)

@custom_ratelimit
@login_required
@ratelimit(key='ip', rate='100/h')
def edit_profile(request, pk):
    profile = get_object_or_404(CustomUser, pk=pk)

    # Pastikan hanya pemilik profil yang bisa mengedit
    if request.user.pk != pk:
        messages.error(request, "Anda tidak memiliki izin untuk mengedit profil ini.")
        return redirect('authentication:dashbord')

    if request.method == "POST":
        form = UserProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Profil berhasil diperbarui.")
            return redirect('authentication:dashbord')
        else:
            messages.error(request, "Silakan perbaiki kesalahan di bawah ini.")
    else:
        form = UserProfileForm(instance=profile)

    return render(request, 'home/edit_profile_form.html', {'form': form, 'user': profile})

@custom_ratelimit
#populercourse
@ratelimit(key='ip', rate='100/h')
@require_GET
def popular_courses(request):
    now = timezone.now().date()
    
    try:
        published_status = CourseStatus.objects.get(status='published')
    except CourseStatus.DoesNotExist:
        return JsonResponse({'error': 'Published status not found.'}, status=404)

    # Query dengan distinct=True pada num_enrollments untuk menghindari duplikasi
    courses = Course.objects.filter(
        status_course=published_status,
        end_date__gte=now
    ).annotate(
        num_enrollments=Count('enrollments', distinct=True),
        avg_rating=Coalesce(Avg('ratings__rating'), 0.0),
        num_ratings=Count('ratings'),
        unique_raters=Count('ratings__user', distinct=True)
    ).order_by('-num_enrollments').select_related(
        'instructor__user', 'org_partner__name', 'org_partner'
    )

    paginator = Paginator(courses, 4)
    page_number = request.GET.get('page', 1)
    try:
        page_obj = paginator.get_page(page_number)
    except (PageNotAnInteger, EmptyPage):
        page_obj = paginator.get_page(1)

    courses_list = []
    for course in page_obj:
        avg_rating = course.avg_rating
        full_stars = int(avg_rating)
        half_star = (avg_rating % 1) >= 0.5
        empty_stars = 5 - full_stars - (1 if half_star else 0)

        # Ambil label bahasa dari choices
        language_label = dict(Course.choice_language).get(course.language, course.language)

        # Ambil harga user (jika ada)
        course_price = course.get_course_price()
        portal_price = float(course_price.portal_price) if course_price else 0.0

        courses_list.append({
            'id': course.id,
            'course_name': course.course_name,
            'slug': course.slug,
            'image': course.image.url if course.image else '',
            'instructor_name': f"{course.instructor.user.first_name} {course.instructor.user.last_name}".strip(),
            'instructor_photo': course.instructor.user.photo.url if course.instructor.user.photo else '',
            'org_name': course.org_partner.name.name,
            'org_kode': course.org_partner.name.kode,
            'org_slug': course.org_partner.name.slug,
            'org_logo': course.org_partner.logo.url if course.org_partner.logo else '',
            'num_enrollments': course.num_enrollments,
            'avg_rating': float(avg_rating),
            'num_ratings': course.unique_raters,
            'full_stars': full_stars,
            'half_star': half_star,
            'empty_stars': empty_stars,
            'language': language_label,
            'user_payment': portal_price,
        })

    return JsonResponse({'courses': courses_list})

@custom_ratelimit
@ratelimit(key='ip', rate='1000/h', block=True)
@require_GET
def home(request):
    if request.method != 'GET':
        return HttpResponseNotAllowed(['GET'])

    published_status = CourseStatus.objects.filter(status='published').first()
    now_time = timezone.now()
    # Inisialisasi variabel default
    popular_categories = []
    popular_microcredentials = []
    partners = []
    instructors_page = None
    latest_articles = []

    total_instructors = 0
    total_partners = 0
    total_users = 0
    total_courses = 0

    if published_status:
        # Kategori populer dengan jumlah kursus aktif
        popular_categories = Category.objects.annotate(
            num_courses=Count(
                'category_courses',
                filter=Q(
                    category_courses__status_course=published_status,
                    category_courses__end_enrol__gte=timezone.now()
                )
            )
        ).order_by('-num_courses')[:4]

        # Microcredential aktif
        popular_microcredentials = MicroCredential.objects.filter(
            status='active'
        ).order_by('-created_at')[:6]

        # ✅ Hanya partner yang punya course publish & open enrollment
        partners = Partner.objects.annotate(
            active_courses=Count(
                'courses',
                filter=Q(
                    courses__status_course=published_status,
                    courses__end_enrol__gte=now_time
                )
            )
        ).filter(active_courses__gt=0).order_by('id')

        # Instruktur disetujui dengan urutan
        instructors = Instructor.objects.filter(status='Approved').order_by('id')

        if instructors.exists():
            instructor_paginator = Paginator(instructors, 6)
            page_number = request.GET.get('instructor_page')
            instructors_page = instructor_paginator.get_page(page_number)
            total_instructors = instructors.count()

        total_partners = partners.count()
        total_users = CustomUser.objects.count()
        total_courses = Course.objects.filter(
            status_course=published_status,
            end_date__gte=timezone.now()
        ).count()

        latest_articles = BlogPost.objects.filter(
            status='published'
        ).order_by('-date_posted')[:3]

    # Pagination untuk partners
    partner_paginator = Paginator(partners, 14)
    page_number = request.GET.get('partner_page')
    page_obj = partner_paginator.get_page(page_number)

    tw_colors = [
    "bg-green-100 text-green-700 hover:border-green-500",
    "bg-blue-100 text-blue-700 hover:border-blue-500",
    "bg-yellow-100 text-yellow-700 hover:border-yellow-500",
    "bg-teal-100 text-teal-700 hover:border-teal-500",
    "bg-purple-100 text-purple-700 hover:border-purple-500",
    ]

    total_certificates = Certificate.objects.count()

    return render(request, 'home/index.html', {
        'popular_categories': popular_categories,
        'popular_microcredentials': popular_microcredentials,
        'partners': page_obj,
        'total_instructors': total_instructors,
        'total_partners': total_partners,
        'total_users': total_users,
        'total_courses': total_courses,
        'instructors': instructors_page,
        'latest_articles': latest_articles,
        'tw_colors': tw_colors,
        'total_certificates': total_certificates,  
    })

logger = logging.getLogger(__name__)
@custom_ratelimit
@csrf_protect
@ratelimit(key='ip', rate='100/h')  # Bisa diperbarui ke 'user:ip' jika memungkinkan
@require_http_methods(["GET", "POST"])  # Gantikan pengecekan manual metode
def search(request):
    # Pengecekan Referer
    referer = request.headers.get('Referer', '')
    if not referer.startswith(settings.ALLOWED_REFERER):
        logger.warning(f"Invalid referer: {referer} from IP {request.META.get('REMOTE_ADDR')}")
        return HttpResponseForbidden("Akses ditolak: sumber tidak sah")

    # Handle penghapusan riwayat (POST request)
    if request.method == 'POST' and request.user.is_authenticated:
        if request.POST.get('clear_history') == '1':
            SearchHistory.objects.filter(user=request.user).delete()
            logger.info(f"User {request.user.id} deleted their search history.")
            messages.success(request, "Riwayat pencarian berhasil dihapus.")
            return redirect(reverse('authentication:home'))

    # Sanitasi dan validasi input
    query = html.escape(request.GET.get('q', '').strip()[:255])  # Batasi panjang query
    query = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[email]', query)
    query = re.sub(r'\b\d{10,}\b', '[number]', query)

    try:
        page_number = int(request.GET.get('page', 1))
        if page_number < 1:
            page_number = 1
    except (ValueError, TypeError):
        page_number = 1

    results = {
        'courses': [],
        'instructors': [],
        'partners': [],
        'blog_posts': [],
    }
    search_history = []
    base_url = request.build_absolute_uri('/')

    if query:
        # Pencarian Courses
        results['courses'] = Course.objects.filter(
            Q(course_name__icontains=query) | 
            Q(description__icontains=query),
            status_course__status='published',
            end_enrol__gte=timezone.now()
        ).select_related('instructor', 'org_partner')[:5]

        # Pencarian Instructors
        results['instructors'] = Instructor.objects.filter(
            Q(user__email__icontains=query) | 
            Q(bio__icontains=query)
        ).select_related('user')[:5]

        # Pencarian Partners
        results['partners'] = Partner.objects.filter(
            Q(name__name__icontains=query) | 
            Q(description__icontains=query)
        ).select_related('name')[:5]

        # Pencarian Blog Posts
        blog_posts = BlogPost.objects.filter(
            Q(title__icontains=query) |
            Q(content__icontains=query) |
            Q(tags__name__icontains=query) |
            Q(related_courses__course_name__icontains=query),
            status='published'
        ).select_related('author', 'category').prefetch_related('tags', 'related_courses')[:50]

        # Simpan kata kunci pencarian
        if request.user.is_authenticated:
            if not SearchHistory.objects.filter(user=request.user, keyword=query).exists():
                SearchHistory.objects.create(user=request.user, keyword=query)
        else:
            if not request.session.session_key:
                request.session.create()
            cache_key = f"search_history_anonymous_{request.session.session_key}"
            history = cache.get(cache_key, [])
            if query not in history:
                history.append(query)
                history = history[-10:]  # Batasi 10 entri
                cache.set(cache_key, history, timeout=24*60*60)

    # Ambil riwayat pencarian
    if request.user.is_authenticated:
        search_history = SearchHistory.objects.filter(user=request.user).order_by('-search_date')[:10]
    else:
        cache_key = f"search_history_anonymous_{request.session.session_key}"
        search_history = cache.get(cache_key, [])

    # Pagination untuk blog posts
    paginator = Paginator(results['blog_posts'], 6)
    page_number = min(page_number, paginator.num_pages)  # Batasi halaman maksimum
    page_obj = paginator.get_page(page_number)
    results['blog_posts'] = page_obj

    return render(request, 'home/results.html', {
        'query': query,
        'results': results,
        'search_history': search_history,
        'base_url': base_url,
        'page_obj': page_obj,
    })


# Logout view
@custom_ratelimit
def logout_view(request):
    logout(request)
    messages.error(request, 'You have been logged out.')
    return redirect('authentication:home')  # Redirect to home page after logout

#login view
@ratelimit(key='ip', rate='5/m', block=False)
def login_view(request):
    if request.user.is_authenticated:
        return redirect('authentication:home')

    was_limited = getattr(request, 'limited', False)

    if request.method == 'POST':
        form = LoginForm(request.POST)

        if was_limited:
            messages.error(request, 'Too many login attempts. Please try again later.')
            return render(request, 'authentication/login.html', {'form': form})

        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            user = authenticate(request, username=email, password=password)

            if user is not None:
                if not user.is_active:
                    messages.error(request, 'Your account has not been activated. Please check your email for activation.')
                    return render(request, 'authentication/login.html', {'form': form})

                login(request, user)

                # Ambil IP, Geo, User Agent
                ip = get_client_ip(request)
                geo = get_geo_from_ip(ip)
                user_agent = request.META.get('HTTP_USER_AGENT', '')

                UserActivityLog.objects.create(
                    user=user,
                    activity_type='login_view',
                    ip_address=ip,
                    location=f"{geo.get('city', '')}, {geo.get('country', '')}" if geo else None,
                    user_agent=user_agent,
                )

                next_url = request.POST.get('next') or request.GET.get('next')
                messages.success(request, 'Login successful.')
                return redirect(next_url or 'authentication:home')

            else:
                messages.error(request, 'Email or password is incorrect.')
                return render(request, 'authentication/login.html', {'form': form})
    else:
        form = LoginForm()

    return render(request, 'authentication/login.html', {'form': form})



@custom_ratelimit
# Register view
@ratelimit(key='ip', rate='100/h')
def register_view(request):
    if request.user.is_authenticated:
        return redirect('authentication:home')  # Ganti dengan nama URL home-mu
    
    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data["password1"])
            user.is_active = False
            user.save()

            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(str(user.pk).encode())

            current_site = get_current_site(request)
            mail_subject = 'Activate your account'
            html_message = render_to_string('authentication/email_activation/activate_email_message.html', {
                'user': user,
                'domain': current_site.domain,
                'uid': uid,
                'token': token,
            })
            # Versi teks biasa sebagai fallback
            plain_message = f"Hi {user.username},\nPlease activate your account by visiting: https://{current_site.domain}/activate/{uid}/{token}/"

            # Menggunakan EmailMultiAlternatives
            email = EmailMultiAlternatives(
                subject=mail_subject,
                body=plain_message,  # Teks biasa
                from_email='noreply@yourdomain.com',
                to=[user.email],
            )
            email.attach_alternative(html_message, "text/html")  # Menambahkan versi HTML
            email.send()

            messages.success(request, 'Registration successful! Please check your email to activate your account.')
            return redirect('authentication:login')  # Ganti 'login' dengan nama URL pattern halaman login kamu
    else:
        form = RegistrationForm()
    return render(request, 'authentication/register.html', {'form': form})


@custom_ratelimit
@ratelimit(key='ip', rate='100/h')
# Account activation view
def activate_account(request, uidb64, token):
    try:
        # Decode uidb64 to get the user ID
        uid = urlsafe_base64_decode(uidb64).decode('utf-8')  # Decode back to string
        user = CustomUser.objects.get(pk=uid)
    except (TypeError, ValueError, CustomUser.DoesNotExist):
        user = None
    
    if user is not None and default_token_generator.check_token(user, token):
        user.is_active = True  # Set user to active
        user.save()
        user.backend = 'django.contrib.auth.backends.ModelBackend'
        login(request, user)  # Automatically log the user in after activation
        return redirect('authentication:home')  # Redirect to the home page after login
    else:
        return HttpResponse('Activation link is invalid or expired.')

@custom_ratelimit
@ratelimit(key='ip', rate='100/h')
# Custom Password Reset View
def custom_password_reset(request):
    if request.user.is_authenticated:
        return redirect('authentication:home')  # Ganti dengan nama URL home-mu
    form = PasswordResetForms(request.POST or None)

    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data['email']

        # Cari pengguna berdasarkan email
        try:
            user = CustomUser.objects.get(email=email)  # Gunakan CustomUser langsung
            uid = urlsafe_base64_encode(str(user.pk).encode())
            token = default_token_generator.make_token(user)
        except CustomUser.DoesNotExist:
            # Tetap lanjutkan ke halaman done agar tidak membocorkan info
            return render(request, 'authentication/password_reset_done.html')

        # Tentukan protokol secara dinamis
        protocol = 'https' if request.is_secure() else 'http'
        domain = get_current_site(request).domain

        # Siapkan konteks untuk email
        context = {
            'protocol': protocol,
            'domain': domain,
            'uid': uid,
            'token': token,
        }

        # Render isi email dari template
        email_subject = "Password Reset Request"
        email_message = render_to_string('authentication/password_reset_email.html', context)

        # Kirim email sebagai HTML
        email = EmailMessage(
            subject=email_subject,
            body=email_message,
            from_email='no-reply@yourdomain.com',
            to=[email],
        )
        email.content_subtype = 'html'  # Pastikan email dirender sebagai HTML

        # Tangani error pengiriman email
        try:
            email.send()
        except Exception as e:
            # Log error jika perlu, tapi tetap tampilkan halaman sukses untuk UX
            return HttpResponse("Terjadi kesalahan saat mengirim email. Silakan coba lagi nanti.")

        # Tampilkan halaman konfirmasi
        return render(request, 'authentication/password_reset_done.html')

    # Tampilkan form jika bukan POST atau form tidak valid
    return render(request, 'authentication/password_reset.html', {'form': form})

@ratelimit(key='ip', rate='100/h')
# Custom Password Reset Done View
def custom_password_reset_done(request):
    return render(request, 'x/password_reset_done.html')

@custom_ratelimit
@ratelimit(key='ip', rate='100/h')
# Custom Password Reset Confirm View
def custom_password_reset_confirm(request, uidb64, token):
    try:
        uid = urlsafe_base64_decode(uidb64).decode('utf-8')
        user = CustomUser.objects.get(pk=uid)
    except (TypeError, ValueError, CustomUser.DoesNotExist):
        user = None
    
    if user and default_token_generator.check_token(user, token):
        if request.method == 'POST':
            form = SetPasswordForm(user, request.POST)
            if form.is_valid():
                form.save()
                return redirect('authentication:password_reset_complete')
            # Jika form tidak valid, tetap render form dengan error
        else:
            form = SetPasswordForm(user)

        return render(request, 'authentication/password_reset_confirm.html', {'form': form})
    
    else:
        return render(request, 'authentication/password_reset_invalid.html')

@custom_ratelimit
@ratelimit(key='ip', rate='100/h')
# Custom Password Reset Complete View
def custom_password_reset_complete(request):
    return render(request, 'authentication/password_reset_complete.html')


def faq(request):
    return render(request, 'home/JakIja/faq.html')

def contact(request):
    return render(request, 'home/JakIja/contact.html')

def terms(request):
    return render(request, 'home/JakIja/terms.html')

def privacy(request):
    return render(request, 'home/JakIja/privacy.html')

def instructor_agreement(request):
    return render(request, 'home/JakIja/instructor_agreement.html')

def partnership_agreement(request):
    return render(request, 'home/JakIja/partnership_agreement.html')

def cookie_policy(request):
    return render(request, 'home/JakIja/cookie_policy.html')

def refund_policy(request):
    return render(request, 'home/JakIja/refund_policy.html')

def security(request):
    return render(request, 'home/JakIja/security.html')

def partner_info(request):
    return render(request, 'home/JakIja/partner_info.html')
