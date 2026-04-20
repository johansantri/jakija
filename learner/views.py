try:
    from pylti.common import ToolConsumer  # Coba ToolConsumer sebagai alternatif
except ImportError:
    from pylti import common  # Impor modul utama jika LTI tidak ada
import csv
import logging
from multiprocessing import context
from urllib import request
import uuid
import base64
from django.contrib.contenttypes.models import ContentType
from django.conf import settings
import xml.etree.ElementTree as ET
import oauthlib.oauth1
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import hmac
import hashlib
from django.core.mail import send_mail, BadHeaderError, EmailMessage, EmailMultiAlternatives, get_connection
import urllib.parse
from urllib.parse import urlparse, urlunparse,quote, urlencode,parse_qsl
from datetime import datetime
import time
import pytz
from learner.tasks import send_invite_email
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Prefetch, F,Q
from django.db import transaction
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse,HttpResponseBadRequest,HttpResponseForbidden
from django.shortcuts import get_object_or_404, render,redirect
from django.urls import reverse, NoReverseMatch
from django.utils import timezone
from django.template.defaultfilters import linebreaks
from collections import OrderedDict
from django.middleware.csrf import get_token
from authentication.models import CustomUser, Universiti
from notification.models import Notification
from django.template.loader import render_to_string
from django.db.models.functions import TruncMonth
from django.utils.timezone import now,timedelta
import datetime
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import models
from django.core.cache import cache
from django.views.decorators.cache import cache_page
import json
from courses.models import (
    Assessment, AssessmentRead, AssessmentScore, AssessmentSession,
    AskOra, Choice, Comment, Course, CourseProgress, CourseStatusHistory,
    Enrollment, GradeRange, Instructor, LTIExternalTool1, Material,
    MaterialRead, Payment, PeerReview, Question, QuestionAnswer,LTIResult,
    Score, Section, Submission, UserActivityLog,Certificate, CommentReaction, 
    AttemptedQuestion,LastAccessCourse,CourseSessionLog,QuizResult,Video,Quiz,
    SectionReport,AssessmentResult
)
from django.views.decorators.csrf import csrf_exempt
from django.template import loader
from django.conf import settings
from oauthlib.oauth1 import Client
from .lti_utils import verify_oauth_signature, parse_lti_grade_xml
from geoip2.database import Reader as GeoIP2Reader
import geoip2.errors
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from decimal import Decimal, ROUND_HALF_UP
from audit.models import AuditLog
import smtplib
from django.core.mail import send_mail, BadHeaderError
from django.db.models import F, Value
logger = logging.getLogger(__name__)
from django.core.validators import validate_email
from django.core.exceptions import ValidationError




@login_required
def submit_report(request, username, course_id, section_id):
    if request.user.username != username:
        return HttpResponse(status=403)

    user = request.user
    section = get_object_or_404(Section, id=section_id)

    material_id = request.GET.get('material_id')
    assessment_id = request.GET.get('assessment_id')

    material = Material.objects.filter(id=material_id).first() if material_id else None
    assessment = Assessment.objects.filter(id=assessment_id).first() if assessment_id else None

    if request.method == 'POST':
        # ✅ Cek apakah user sudah pernah report
        exists = SectionReport.objects.filter(
            section=section,
            material=material,
            assessment=assessment,
            user=user
        ).exists()

        if exists:
            # Jika sudah ada, kembalikan pesan HTMX
            if request.headers.get('HX-Request') == 'true':
                return HttpResponse('<span class="text-warning">You have already reported this!</span>')
            else:
                messages.warning(request, "You have already reported this!")
                return redirect('learner:my_course', username=username, id=course_id, slug=section.courses.slug)

        # Jika belum ada, buat report baru
        SectionReport.objects.create(
            section=section,
            material=material,
            assessment=assessment,
            user=user,
            status=SectionReport.STATUS_PENDING
        )
        if request.headers.get('HX-Request') == 'true':
            return HttpResponse('<span class="text-success">Report submitted successfully!</span>')
        else:
            messages.success(request, "Report submitted successfully!")
            return redirect('learner:my_course', username=username, id=course_id, slug=section.courses.slug)

    return HttpResponseBadRequest("Invalid request")




@login_required
def invite_learner(request, course_id):
    course = get_object_or_404(Course, id=course_id)

    if request.method != "POST":
        return redirect('courses:detail', course_id=course.id)

    emails_raw = request.POST.get("emails", "").strip()

    if not emails_raw:
        messages.error(request, "Please provide at least one email.")
        return redirect(request.META.get('HTTP_REFERER', '/'))

    # Support comma, space, newline
    emails = [e.strip() for e in emails_raw.replace(",", " ").split() if e.strip()]

    if not emails:
        messages.error(request, "No valid emails found.")
        return redirect(request.META.get('HTTP_REFERER', '/'))

    success_count = 0
    skipped_count = 0

    for email in emails:

        # Validasi email Django
        try:
            validate_email(email)
        except ValidationError:
            messages.warning(request, f"{email} is not a valid email. Skipped.")
            skipped_count += 1
            continue

        user = CustomUser.objects.filter(email=email).first()

        if not user:
            messages.warning(request, f"{email} is not registered. Skipped.")
            skipped_count += 1
            continue

        enrollment, created = Enrollment.objects.get_or_create(
            user=user,
            course=course
        )

        if not created:
            messages.info(request, f"{user.username} is already enrolled.")
            skipped_count += 1
            continue

        # Kirim email async (Celery)
        try:
            send_invite_email.delay(email, user.username, course.course_name)
        except Exception as e:
            messages.error(request, f"Failed to queue email for {email}: {str(e)}")
            continue

        success_count += 1

    if success_count:
        messages.success(request, f"{success_count} learner(s) successfully invited.")

    if skipped_count:
        messages.info(request, f"{skipped_count} email(s) skipped.")

    return redirect(request.META.get('HTTP_REFERER', '/'))


@login_required
def my_activity(request):
    # Hanya log model tertentu yang user boleh lihat
    allowed_models = ['customuser', 'coursesessionlog', 'lastaccesscourse']
    logs = AuditLog.objects.filter(
        user=request.user,
        content_type__model__in=allowed_models
    ).order_by('-timestamp')

    paginator = Paginator(logs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, "learner/my_activity.html", {"page_obj": page_obj})


@login_required
def score_summary_view_detail(request, course_id):
    """
    View untuk admin/instructor/partner melihat ringkasan skor seluruh user di sebuah course.
    Mendukung:
        - LTI assessments
        - In-video quizzes
        - MCQ (AssessmentResult)
        - Askora submissions
    """
    user = request.user
    course = get_object_or_404(Course, id=course_id)

    # === ACCESS CONTROL ===
    allowed_roles = ['curation', 'finance']

    is_allowed = (
        user.is_superuser or
        user.is_staff or
        (hasattr(user, 'role') and user.role in allowed_roles) or
        user.groups.filter(name__in=allowed_roles).exists()
    )

    is_partner_owner = (
        hasattr(user, 'partner_user') and
        course.org_partner and
        course.org_partner.user == user
    )

    is_instructor = (
        hasattr(course, 'instructor') and
        course.instructor and
        course.instructor.user == user
    )

    if not (is_allowed or is_partner_owner or is_instructor):
        messages.error(request, "Access denied.")
        return redirect('authentication:home')

    # Semua enrolled users di course
    enrollments = course.enrollments.all()
    users = [enrollment.user for enrollment in enrollments]

    # 🔹 Passing grade threshold
    grade_ranges = GradeRange.objects.filter(course=course)
    if grade_ranges.exists():
        grade_fail = grade_ranges.order_by('max_grade').first()
        passing_threshold = grade_fail.max_grade + 1 if grade_fail else Decimal('60')
    else:
        passing_threshold = Decimal('60')

    assessments = Assessment.objects.filter(section__courses=course)

    user_scores = []

    # 🔹 Loop semua user untuk hitung skor
    for target_user in users:
        assessment_scores = []
        total_max_score = Decimal('0')
        total_score = Decimal('0')
        all_assessments_submitted = True

        for assessment in assessments:
            score_value = Decimal('0')
            is_submitted = True

            # === CASE 1: LTI ===
            lti_result = LTIResult.objects.filter(user=target_user, assessment=assessment).first()
            if lti_result and lti_result.score is not None:
                lti_score = Decimal(lti_result.score)
                if lti_score > 1.0:
                    lti_score = lti_score / 100
                score_value = lti_score * Decimal(assessment.weight)

            else:
                # === CASE 2: IN-VIDEO QUIZ ===
                invideo_quizzes = Quiz.objects.filter(assessment=assessment)
                if invideo_quizzes.exists():
                    quiz_result = QuizResult.objects.filter(user=target_user, assessment=assessment).first()
                    if quiz_result and quiz_result.total_questions > 0:
                        raw_percentage = Decimal(quiz_result.score) / Decimal(quiz_result.total_questions)
                        score_value = raw_percentage * Decimal(assessment.weight)
                    else:
                        is_submitted = False
                        all_assessments_submitted = False
                        score_value = Decimal('0')

                else:
                    # === CASE 3: MCQ (AssessmentResult) ===
                    mcq_result = AssessmentResult.objects.filter(user=target_user, assessment=assessment).first()
                    if mcq_result and mcq_result.total_questions > 0:
                        raw_percentage = Decimal(mcq_result.correct_answers) / Decimal(mcq_result.total_questions)
                        score_value = raw_percentage * Decimal(assessment.weight)
                    else:
                        # Jika tidak ada submission MCQ
                        is_submitted = False
                        all_assessments_submitted = False
                        score_value = Decimal('0')

                    # === CASE 4: ASKORA ===
                    askora_subs = Submission.objects.filter(askora__assessment=assessment, user=target_user)
                    if askora_subs.exists():
                        latest_submission = askora_subs.order_by('-submitted_at').first()
                        assessment_score = AssessmentScore.objects.filter(submission=latest_submission).first()
                        if assessment_score:
                            score_value = Decimal(assessment_score.final_score)
                        else:
                            is_submitted = False
                            all_assessments_submitted = False
                    else:
                        # Jika tidak ada submit MCQ maupun Askora
                        if not mcq_result:
                            is_submitted = False
                            all_assessments_submitted = False

            # Clamp score agar tidak melebihi weight
            score_value = min(score_value, Decimal(assessment.weight))

            # Simpan per-assessment
            assessment_scores.append({
                'assessment': assessment,
                'score': score_value,
                'weight': assessment.weight,
                'is_submitted': is_submitted,
            })

            # Akumulasi total
            total_max_score += Decimal(assessment.weight)
            total_score += score_value

        # Finalisasi total
        total_score = min(total_score, total_max_score)
        overall_percentage = (total_score / total_max_score * 100) if total_max_score > 0 else Decimal('0')

        # Progress
        course_progress = CourseProgress.objects.filter(user=target_user, course=course).first()
        progress_percentage = course_progress.progress_percentage if course_progress else 0

        passing_criteria_met = overall_percentage >= passing_threshold and progress_percentage == 100
        status = "Pass" if all_assessments_submitted and passing_criteria_met else "Fail"

        # Grade letter
        grade_range = GradeRange.objects.filter(
            course=course,
            min_grade__lte=overall_percentage,
            max_grade__gte=overall_percentage
        ).first()

        # Simpan ke list user
        user_scores.append({
            'user': target_user,
            'assessment_results': [
                {'name': score['assessment'].name, 'max_score': score['weight'], 'score': score['score']}
                for score in assessment_scores
            ] + [{'name': 'Total', 'max_score': total_max_score, 'score': total_score}],
            'overall_percentage': round(overall_percentage, 2),
            'status': status,
            'grade': grade_range.name if grade_range else "N/A",
            'passing_threshold': passing_threshold,
        })

    # Render template
    return render(request, 'learner/score_summary_detail.html', {
        'course': course,
        'user_scores': user_scores
    })


@login_required
def score_summary_view(request, username, course_id):
    """
    Menampilkan ringkasan nilai semua assessment pada sebuah course.
    Menghitung total score, persentase, status Pass/Fail, dan grade.
    Mendukung LTI, In-Video Quiz, MCQ, dan Askora submissions.
    """

    user = request.user

    # 🔐 Akses hanya untuk user sendiri
    if username != user.username:
        return HttpResponseForbidden("Access denied.")
    if not getattr(user, 'is_learner', False):
        return HttpResponseForbidden("Access denied: learner only.")

    # 📚 Ambil course & assessments
    course = get_object_or_404(Course, id=course_id)
    assessments = Assessment.objects.filter(section__courses=course)

    # 🎯 Tentukan passing threshold
    grade_ranges = GradeRange.objects.filter(course=course).order_by('max_grade')

    if grade_ranges.exists():
        lowest_range = grade_ranges.first()
        passing_threshold = lowest_range.max_grade + 1
    else:
        passing_threshold = Decimal('60')

    # 🔢 Variabel akumulasi
    assessment_scores = []
    total_max_score = Decimal('0')
    total_score = Decimal('0')
    all_assessments_submitted = True

    # ==============================
    # 🔁 LOOP SEMUA ASSESSMENT
    # ==============================
    for assessment in assessments:

        score_value = Decimal('0')
        is_submitted = True

        # ========= CASE 1: LTI =========
        lti_result = LTIResult.objects.filter(
            user=user,
            assessment=assessment
        ).first()

        if lti_result and lti_result.score is not None:
            lti_score = Decimal(lti_result.score)

            if lti_score > 1:
                lti_score = lti_score / 100

            score_value = lti_score * Decimal(assessment.weight)

        else:

            # ========= CASE 2: IN-VIDEO QUIZ =========
            quiz_exists = Quiz.objects.filter(assessment=assessment).exists()

            if quiz_exists:
                quiz_result = QuizResult.objects.filter(
                    user=user,
                    assessment=assessment
                ).first()

                if quiz_result and quiz_result.total_questions > 0:
                    raw_percentage = (
                        Decimal(quiz_result.score) /
                        Decimal(quiz_result.total_questions)
                    )
                    score_value = raw_percentage * Decimal(assessment.weight)
                else:
                    is_submitted = False
                    all_assessments_submitted = False

            else:
                # ========= CASE 3: MCQ =========
                mcq_result = AssessmentResult.objects.filter(
                    user=user,
                    assessment=assessment
                ).first()

                if mcq_result and mcq_result.total_questions > 0:
                    raw_percentage = (
                        Decimal(mcq_result.correct_answers) /
                        Decimal(mcq_result.total_questions)
                    )
                    score_value = raw_percentage * Decimal(assessment.weight)
                else:
                    is_submitted = False
                    all_assessments_submitted = False

                # ========= CASE 4: ASKORA =========
                askora_sub = Submission.objects.filter(
                    askora__assessment=assessment,
                    user=user
                ).order_by('-submitted_at').first()

                if askora_sub:
                    score_obj = AssessmentScore.objects.filter(
                        submission=askora_sub
                    ).first()

                    if score_obj:
                        score_value = Decimal(score_obj.final_score)
                    else:
                        is_submitted = False
                        all_assessments_submitted = False

        # 🔒 Clamp agar tidak melebihi weight
        score_value = min(score_value, Decimal(assessment.weight))

        assessment_scores.append({
            'assessment': assessment,
            'score': score_value,
            'weight': assessment.weight,
            'is_submitted': is_submitted,
        })

        total_max_score += Decimal(assessment.weight)
        total_score += score_value

    # ==============================
    # 🔢 HITUNG TOTAL
    # ==============================
    total_score = min(total_score, total_max_score)

    overall_percentage = (
        (total_score / total_max_score) * 100
        if total_max_score > 0 else Decimal('0')
    )

    # 📈 Progress hanya untuk informasi
    course_progress = CourseProgress.objects.filter(
        user=user,
        course=course
    ).first()

    progress_percentage = (
        Decimal(course_progress.progress_percentage)
        if course_progress else Decimal('0')
    )

    # ==============================
    # ✅ STATUS BERDASARKAN NILAI SAJA
    # ==============================
    status = "Pass" if overall_percentage >= passing_threshold else "Fail"

    # 🎓 Grade letter
    grade_range = GradeRange.objects.filter(
        course=course,
        min_grade__lte=overall_percentage,
        max_grade__gte=overall_percentage
    ).first()

    # 📋 Data untuk template
    assessment_results = [
        {
            'name': s['assessment'].name,
            'max_score': s['weight'],
            'score': s['score']
        }
        for s in assessment_scores
    ]

    assessment_results.append({
        'name': 'Total',
        'max_score': total_max_score,
        'score': total_score
    })

    return render(request, 'learner/score_summary.html', {
        'course': course,
        'username': user.username,
        'assessment_results': assessment_results,
        'overall_percentage': round(overall_percentage, 2),
        'status': status,
        'grade': grade_range.name if grade_range else "N/A",
        'passing_threshold': passing_threshold,
        'progress_percentage': progress_percentage,
        'all_submitted': all_assessments_submitted,
    })




def percent_encode(s):
    return quote(str(s), safe='~')

def generate_oauth_signature(params, consumer_secret, launch_url):
    # 1. Parse launch_url to get base_url and query params
    parsed_url = urlparse(launch_url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
    query_params = dict(parse_qsl(parsed_url.query))

    # 2. Gabungkan query params dari URL ke dalam params
    full_params = {**params, **query_params}

    # 3. Sort & percent encode parameter (RFC 5849)
    encoded_params = []
    for k, v in sorted(full_params.items()):
        encoded_k = percent_encode(k)
        encoded_v = percent_encode(v)
        encoded_params.append(f"{encoded_k}={encoded_v}")

    param_string = '&'.join(encoded_params)

    # 4. Bangun base string
    base_string = '&'.join([
        "POST",
        percent_encode(base_url),
        percent_encode(param_string)
    ])

    # 5. Generate signature
    key = f"{percent_encode(consumer_secret)}&"  # token secret kosong
    raw = base_string.encode('utf-8')
    hashed = hmac.new(key.encode('utf-8'), raw, hashlib.sha1)
    signature = base64.b64encode(hashed.digest()).decode()

    # Debug log
    logger.debug("Base URL: %s", base_url)
    logger.debug("Base String: %s", base_string)
    logger.debug("Signing Key: %s", key)
    logger.debug("OAuth Signature: %s", signature)

    return signature

#@login_required

logger = logging.getLogger(__name__)

#@csrf_exempt
def lti_consume_course(request, assessment_id):
    # Get assessment and LTI tool
    assessment = get_object_or_404(Assessment, id=assessment_id)
    lti_tool = getattr(assessment, 'lti_tool', None)
    if not lti_tool:
        logger.error("LTI tool not configured for assessment %s", assessment_id)
        return HttpResponse("LTI tool belum dikonfigurasi.", status=400)

    launch_url = lti_tool.launch_url
    consumer_key = lti_tool.consumer_key
    shared_secret = lti_tool.shared_secret

    # Handle user
    user = request.user
    user_id = str(user.id) if user.is_authenticated else str(uuid.uuid4())
    user_full_name = user.get_full_name() if user.is_authenticated else "Anonymous User"
    user_email = user.email if user.is_authenticated else "anonymous@example.com"

    # Basic OAuth and LTI parameters
    oauth_params = {
        "oauth_consumer_key": consumer_key,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_version": "1.0",
        "oauth_nonce": uuid.uuid4().hex,
        "oauth_timestamp": str(int(time.time())),
        "resource_link_id": f"res-{assessment.id}",
        "user_id": user_id,
        "roles": "Learner",
        "lis_person_name_full": user_full_name,
        "lis_person_contact_email_primary": user_email,
        "context_id": f"course-{assessment.id}",
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
            logger.info("Initialized LTIResult for user %s, assessment %s", user_id, assessment_id)
        except Exception as e:
            logger.error("Failed to initialize LTIResult: %s", e)

    return render(request, "learner/lti_launch_form.html", {
        "launch_url": launch_url,
        "params": oauth_params,
    })



logger = logging.getLogger(__name__)

@csrf_exempt
def lti_grade_callback(request):
    """
    Menangani callback dari LMS untuk menerima skor melalui LTI Outcome Service.
    """
    if request.method != "POST":
        logger.error("Invalid request method: %s", request.method)
        return HttpResponse("Metode tidak diizinkan.", status=405)

    # Parse XML dari body
    try:
        body = request.body.decode('utf-8')
        logger.debug("Received LTI callback body: %s", body)
        root = ET.fromstring(body)
        ns = {'ims': 'http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0'}

        # Ambil lis_result_sourcedid dan skor
        sourcedid = root.find('.//ims:sourcedGUID/ims:sourcedId', ns).text
        score_element = root.find('.//ims:resultScore/ims:textString', ns)
        score = float(score_element.text) if score_element is not None else None

        if not sourcedid or score is None:
            logger.error("Missing lis_result_sourcedid or score in callback request")
            return HttpResponse("Missing lis_result_sourcedid or score.", status=400)

    except ET.ParseError:
        logger.error("Failed to parse XML body")
        return HttpResponse("Invalid XML format.", status=400)

    # Ambil LTIResult berdasarkan lis_result_sourcedid
    try:
        lti_result = get_object_or_404(LTIResult, result_sourcedid=sourcedid)
    except Exception as e:
        logger.error("LTIResult not found for sourcedid %s: %s", sourcedid, e)
        return HttpResponse("LTIResult tidak ditemukan.", status=404)

    # Validasi OAuth (opsional, jika LMS memerlukannya)
    consumer_key = lti_result.consumer_key
    shared_secret = lti_result.assessment.lti_tool.shared_secret
    oauth_client = oauthlib.oauth1.Client(
        consumer_key,
        client_secret=shared_secret,
        signature_method=oauthlib.oauth1.SIGNATURE_HMAC_SHA1,
        signature_type='body'
    )
    # Verifikasi tanda tangan (jika diperlukan)
    try:
        uri = request.build_absolute_uri()
        headers = {"Content-Type": "application/xml"}
        valid = oauth_client.verify_request(uri, http_method="POST", body=body, headers=request.headers)
        if not valid:
            logger.error("OAuth signature verification failed")
            return HttpResponse("OAuth signature verification failed.", status=401)
    except Exception as e:
        logger.warning("OAuth verification skipped or failed: %s", e)

    # Simpan skor ke LTIResult
    try:
        lti_result.score = score * 100  # Konversi ke skala 0-100 (jika LMS mengirim 0.0-1.0)
        lti_result.last_sent_at = timezone.now()
        lti_result.save()
        logger.info("Score %s saved for LTIResult %s", score, sourcedid)
    except Exception as e:
        logger.error("Failed to save score for LTIResult %s: %s", sourcedid, e)
        return HttpResponse("Gagal menyimpan skor.", status=500)

    # Kembalikan respons XML sesuai spesifikasi LTI
    response_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <imsx_POXEnvelopeResponse xmlns="http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0">
        <imsx_POXHeader>
            <imsx_POXResponseHeaderInfo>
                <imsx_version>V1.0</imsx_version>
                <imsx_messageIdentifier>{uuid.uuid4().hex}</imsx_messageIdentifier>
                <imsx_statusInfo>
                    <imsx_codeMajor>success</imsx_codeMajor>
                    <imsx_severity>status</imsx_severity>
                    <imsx_description>Score received successfully</imsx_description>
                    <imsx_messageRefIdentifier>{root.find('.//ims:imsx_messageIdentifier', ns).text}</imsx_messageIdentifier>
                </imsx_statusInfo>
            </imsx_POXResponseHeaderInfo>
        </imsx_POXHeader>
        <imsx_POXBody>
            <replaceResultResponse/>
        </imsx_POXBody>
    </imsx_POXEnvelopeResponse>
    """

    return HttpResponse(response_xml, content_type="application/xml", status=200)



@login_required
@user_passes_test(lambda u: u.is_staff)
@cache_page(60 * 5)
def user_analytics_view(request):
    gender_filter = request.GET.get('gender')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    download = request.GET.get('download')

    # Base queryset with filter
    users = CustomUser.objects.only(
        'id', 'first_name', 'last_name', 'email', 'gender', 'education',
        'country', 'birth', 'date_joined', 'last_login', 'photo', 'address',
        'is_learner', 'is_instructor', 'is_partner', 'is_subscription', 'is_audit', 'is_member',
        'tiktok', 'youtube', 'facebook', 'instagram', 'linkedin', 'twitter'
    )

    filters = Q()
    if gender_filter in ['male', 'female']:
        filters &= Q(gender=gender_filter)
    if start_date:
        filters &= Q(date_joined__gte=start_date)
    if end_date:
        filters &= Q(date_joined__lte=end_date)
    users = users.filter(filters)

    # Download CSV (langsung iterate tanpa optimasi, karena hanya export)
    if download == "csv":
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="user_analytics.csv"'
        writer = csv.writer(response)
        writer.writerow(['Full Name', 'Email', 'Gender', 'Education', 'Country', 'Birthdate', 'Last Login'])
        for u in users.iterator(chunk_size=1000):
            writer.writerow([u.get_full_name(), u.email, u.gender, u.education, u.country, u.birth, u.last_login])
        return response

    # Warna chart
    genders = ['male', 'female']
    colors = ['#60A5FA', '#F472B6']

    # ----- Agregasi data -----

    # 1. Gender counts
    gender_counts = users.values('gender').annotate(total=Count('id'))
    gender_count_map = {g['gender']: g['total'] for g in gender_counts}

    # 2. Education counts
    education_counts = users.values('education').annotate(total=Count('id'))
    edu_labels = sorted(set(e['education'] for e in education_counts if e['education']))
    # Masukkan juga empty / Unspecified jika ada
    if any(e['education'] == '' or e['education'] is None for e in education_counts):
        edu_labels.append('Unspecified')

    # 3. Education by Gender (menggunakan satu query)
    edu_gender_counts = users.values('gender', 'education').annotate(total=Count('id'))
    edu_gender_dict = {}
    for item in edu_gender_counts:
        key_edu = item['education'] if item['education'] else 'Unspecified'
        edu_gender_dict[(item['gender'], key_edu)] = item['total']

    edu_gender_data = []
    for i, gender in enumerate(genders):
        data = [edu_gender_dict.get((gender, edu), 0) for edu in edu_labels]
        edu_gender_data.append({
            'label': gender.capitalize(),
            'data': data,
            'backgroundColor': colors[i]
        })

    # 4. Top countries
    country_counts = users.values('country').annotate(total=Count('id')).order_by('-total')[:10]
    country_labels = [c['country'].upper() if c['country'] else 'UN' for c in country_counts]
    country_data = [c['total'] for c in country_counts]

    # 5. Role counts by gender - satu query aggregate
    role_fields = ['is_learner', 'is_instructor', 'is_partner', 'is_subscription', 'is_audit', 'is_member']
    role_labels = ['Learner', 'Instructor', 'Partner', 'Subscription', 'Audit', 'Member']

    role_agg = users.values('gender').annotate(
        learner_count=Count('id', filter=Q(is_learner=True)),
        instructor_count=Count('id', filter=Q(is_instructor=True)),
        partner_count=Count('id', filter=Q(is_partner=True)),
        subscription_count=Count('id', filter=Q(is_subscription=True)),
        audit_count=Count('id', filter=Q(is_audit=True)),
        member_count=Count('id', filter=Q(is_member=True)),
    )

    # Buat dict untuk lookup
    role_gender_dict = {}
    for item in role_agg:
        g = item['gender']
        role_gender_dict[g] = {
            'Learner': item['learner_count'],
            'Instructor': item['instructor_count'],
            'Partner': item['partner_count'],
            'Subscription': item['subscription_count'],
            'Audit': item['audit_count'],
            'Member': item['member_count'],
        }

    # Total role count tanpa gender filter (aggregate langsung)
    role_total_counts = users.aggregate(
        learner_total=Count('id', filter=Q(is_learner=True)),
        instructor_total=Count('id', filter=Q(is_instructor=True)),
        partner_total=Count('id', filter=Q(is_partner=True)),
        subscription_total=Count('id', filter=Q(is_subscription=True)),
        audit_total=Count('id', filter=Q(is_audit=True)),
        member_total=Count('id', filter=Q(is_member=True)),
    )
    role_data_count = [
        role_total_counts.get(f'{r}_total') or 0 for r in ['learner', 'instructor', 'partner', 'subscription', 'audit', 'member']
    ]

    role_gender_data_sets = []
    for i, gender in enumerate(genders):
        data = [role_gender_dict.get(gender, {}).get(label, 0) for label in role_labels]
        role_gender_data_sets.append({
            'label': gender.capitalize(),
            'data': data,
            'backgroundColor': colors[i]
        })

    # 6. Social media usage (exclude empty and None)
    social_fields = ['tiktok', 'youtube', 'facebook', 'instagram', 'linkedin', 'twitter']
    social_data_count = []
    for f in social_fields:
        count = users.exclude(**{f: ""}).exclude(**{f: None}).count()
        social_data_count.append(count)

    # 7. Growth (per bulan) dengan TruncMonth dan aggregate
    growth = users.annotate(month=TruncMonth('date_joined')).values('month').annotate(total=Count('id')).order_by('month')
    months = [g['month'] for g in growth]

    growth_gender_agg = users.annotate(month=TruncMonth('date_joined')).values('month', 'gender').annotate(total=Count('id')).order_by('month')

    # Buat dict lookup growth per gender per month
    growth_gender_dict = {}
    for item in growth_gender_agg:
        growth_gender_dict[(item['month'], item['gender'])] = item['total']

    growth_gender_data_sets = []
    for i, gender in enumerate(genders):
        data = [growth_gender_dict.get((m, gender), 0) for m in months]
        growth_gender_data_sets.append({
            'label': gender.capitalize(),
            'data': data,
            'fill': False,
            'borderColor': colors[i]
        })

    # 8. Age group counts (hitung sekali dengan range filter)
    today = datetime.date.today()
    age_bins = [(0, 17), (18, 24), (25, 34), (35, 44), (45, 54), (55, 64), (65, 120)]
    age_bin_counts = []
    for s, e in age_bins:
        # Hitung jumlah birthdate dengan rentang umur (konversi tahun ke timedelta)
        lower_date = today - datetime.timedelta(days=e * 365)
        upper_date = today - datetime.timedelta(days=s * 365)
        count = users.filter(birth__isnull=False, birth__lte=upper_date, birth__gt=lower_date).count()
        age_bin_counts.append(count)

    # 9. Profile completion counts
    profile_completion_count = [
        users.exclude(photo="").exclude(photo=None).count(),
        users.exclude(birth=None).count(),
        users.exclude(address="").exclude(address=None).count()
    ]

    # 10. Active vs inactive users
    threshold = now() - datetime.timedelta(days=30)
    active_count = users.filter(last_login__gte=threshold).count()
    inactive_count = users.exclude(last_login__gte=threshold).count()

    # ----- Buat chart list -----
    chart_list = [
        {
            'id': 'genderChart',
            'title': 'Gender Distribution',
            'type': 'pie',
            'data': json.dumps({
                'labels': [g['gender'].capitalize() if g['gender'] else 'Unspecified' for g in gender_counts],
                'datasets': [{'data': [g['total'] for g in gender_counts], 'backgroundColor': colors + ['#D1D5DB']}]
            })
        },
        {
            'id': 'educationChart',
            'title': 'Education Level',
            'type': 'bar',
            'index_axis': 'y',
            'data': json.dumps({
                'labels': [e['education'] if e['education'] else 'Unspecified' for e in education_counts],
                'datasets': [{'label': 'Users', 'data': [e['total'] for e in education_counts], 'backgroundColor': '#34D399'}]
            })
        },
        {
            'id': 'eduGenderChart',
            'title': 'Education by Gender',
            'type': 'bar',
            'data': json.dumps({'labels': edu_labels, 'datasets': edu_gender_data})
        },
        {
            'id': 'countryChart',
            'title': 'Top Countries',
            'type': 'bar',
            'index_axis': 'y',
            'data': json.dumps({
                'labels': country_labels,
                'datasets': [{'label': 'Users', 'data': country_data, 'backgroundColor': '#FBBF24'}]
            })
        },
        {
            'id': 'roleChart',
            'title': 'Role Distribution',
            'type': 'bar',
            'index_axis': 'y',
            'data': json.dumps({'labels': role_labels, 'datasets': [{'label': 'Users', 'data': role_data_count, 'backgroundColor': '#818CF8'}]})
        },
        {
            'id': 'roleGenderChart',
            'title': 'Role Distribution by Gender',
            'type': 'bar',
            'data': json.dumps({'labels': role_labels, 'datasets': role_gender_data_sets})
        },
        {
            'id': 'socialChart',
            'title': 'Social Media Usage',
            'type': 'bar',
            'index_axis': 'y',
            'data': json.dumps({'labels': [f.capitalize() for f in social_fields], 'datasets': [{'label': 'Users with Account', 'data': social_data_count, 'backgroundColor': '#A78BFA'}]})
        },
        {
            'id': 'growthChart',
            'title': 'User Growth (Last 12 Months)',
            'type': 'line',
            'data': json.dumps({'labels': [m.strftime('%b %Y') for m in months], 'datasets': [{'label': 'New Users', 'data': [g['total'] for g in growth], 'borderColor': '#4F46E5'}]})
        },
        {
            'id': 'growthGenderChart',
            'title': 'User Growth by Gender',
            'type': 'line',
            'data': json.dumps({'labels': [m.strftime('%b %Y') for m in months], 'datasets': growth_gender_data_sets})
        },
        {
            'id': 'ageChart',
            'title': 'Age Group Distribution',
            'type': 'bar',
            'data': json.dumps({'labels': [f"{s}-{e}" for s, e in age_bins], 'datasets': [{'label': 'Users by Age Group', 'data': age_bin_counts, 'backgroundColor': '#F87171'}]})
        },
        {
            'id': 'activeChart',
            'title': 'Active vs Inactive Users',
            'type': 'doughnut',
            'data': json.dumps({'labels': ['Active', 'Inactive'], 'datasets': [{'data': [active_count, inactive_count], 'backgroundColor': ['#10B981', '#F87171']}]})
        },
        {
            'id': 'profileChart',
            'title': 'Profile Completion',
            'type': 'bar',
            'data': json.dumps({'labels': ['Photo', 'Birthdate', 'Address'], 'datasets': [{'label': 'Field Filled', 'data': profile_completion_count, 'backgroundColor': '#10B981'}]})
        },
    ]

    context = {
        'chart_list': chart_list,
        'gender_filter': gender_filter,
        'start_date': start_date,
        'end_date': end_date,
    }
    return render(request, 'learner/analytics.html', context)

def _build_combined_content(sections, combined=None):
    """
    Flatten content in EXACT order as sidebar:
    section -> sub -> unit -> materials -> assessments
    """
    if combined is None:
        combined = []

    for section in sections:
        for sub in section.children.all():
            for unit in sub.children.all():
                for material in unit.materials.all():
                    combined.append(('material', material, unit))
                for assessment in unit.assessments.all():
                    combined.append(('assessment', assessment, unit))

    return combined








def _build_assessment_context(assessment, user):
    """
    Membangun context untuk tampilan assessment.
    Termasuk dukungan untuk AskOra, kuis, peer review, dan LTI 1.1.
    """

    from django.utils import timezone
    from django.db.models import Count, Avg

    # =============================
    # LTI CHECK
    # =============================
    lti_tool = getattr(assessment, 'lti_tool', None)

    if lti_tool:
        return {
            'ask_oras': [],
            'user_submissions': [],
            'askora_submit_status': {},
            'askora_can_submit': {},
            'can_review': False,
            'submissions': [],
            'has_other_submissions': False,
            'is_quiz': False,
            'peer_review_stats': None,
            'score_released': False,
            'is_lti': True,
            'lti_tool': lti_tool,
        }

    # =============================
    # NON-LTI (AskOra / Quiz)
    # =============================
    ask_oras = AskOra.objects.filter(assessment=assessment)
    user_submissions = Submission.objects.filter(
        askora__assessment=assessment,
        user=user
    )

    submitted_askora_ids = set(
        user_submissions.values_list('askora_id', flat=True)
    )

    now = timezone.now()

    submissions = Submission.objects.filter(
        askora__assessment=assessment
    ).exclude(user=user).exclude(
        id__in=PeerReview.objects.filter(
            reviewer=user
        ).values('submission__id')
    )

    has_other_submissions = Submission.objects.filter(
        askora__assessment=assessment
    ).exclude(user=user).exists()

    context = {
        'ask_oras': ask_oras,
        'user_submissions': user_submissions,
        'askora_submit_status': {
            askora.id: (askora.id in submitted_askora_ids)
            for askora in ask_oras
        },
        'askora_can_submit': {
            askora.id: (
                askora.id not in submitted_askora_ids and
                askora.is_responsive and
                (askora.response_deadline is None or askora.response_deadline > now)
            )
            for askora in ask_oras
        },
        'can_review': submissions.exists(),
        'submissions': submissions,
        'has_other_submissions': has_other_submissions,
        'is_quiz': assessment.questions.exists(),
        'peer_review_stats': None,
        'score_released': False,  # default aman
        'is_lti': False,
    }

    # =============================
    # PEER REVIEW STATS
    # =============================
    if user_submissions.exists():

        total_participants = Submission.objects.filter(
            askora__assessment=assessment
        ).values('user').distinct().count()

        user_reviews = PeerReview.objects.filter(
            submission__in=user_submissions
        ).aggregate(
            total_reviews=Count('id'),
            distinct_reviewers=Count('reviewer', distinct=True)
        )

        distinct_reviewers = user_reviews['distinct_reviewers'] or 0
        total_reviews = user_reviews['total_reviews'] or 0

        context['peer_review_stats'] = {
            'total_reviews': total_reviews,
            'distinct_reviewers': distinct_reviewers,
            'total_participants': max(total_participants - 1, 0),
            'completed': distinct_reviewers >= max(total_participants - 1, 0)
        }

        # =============================
        # HITUNG RATA-RATA NILAI
        # =============================
        if total_reviews > 0:
            avg_score = PeerReview.objects.filter(
                submission__in=user_submissions
            ).aggregate(avg_score=Avg('score'))['avg_score']

            context['peer_review_stats']['avg_score'] = (
                round(avg_score, 2) if avg_score else None
            )

        # =============================
        # LOCK SCORE LOGIC
        # =============================

        # Total submission yang harus direview user
        total_to_review = Submission.objects.filter(
            askora__assessment=assessment
        ).exclude(user=user).count()

        # Berapa yang sudah direview user
        user_review_count = PeerReview.objects.filter(
            reviewer=user,
            submission__askora__assessment=assessment
        ).count()

        has_completed_review = (
            total_to_review > 0 and
            user_review_count >= total_to_review
        )

        # Tentukan minimal review yang harus diterima
        participants_minus_self = max(total_participants - 1, 0)

        if participants_minus_self <= 1:
            min_required_reviews = 0
        elif participants_minus_self == 1:
            min_required_reviews = 1
        elif participants_minus_self == 2:
            min_required_reviews = 2
        else:
            min_required_reviews = 3

        score_released = (
            has_completed_review and
            distinct_reviewers >= min_required_reviews
        )

        context['score_released'] = score_released

    return context



@login_required
def toggle_reaction(request, comment_id, reaction_type):
    if request.method != 'POST':
       # logger.warning(f"Invalid request method: {request.method} for toggle_reaction")
        return HttpResponse(status=400)

    if reaction_type not in ['like', 'dislike']:
        #logger.warning(f"Invalid reaction_type: {reaction_type}")
        return HttpResponse(status=400)

    comment = get_object_or_404(Comment, id=comment_id)
    material = comment.material
    reaction_value = CommentReaction.REACTION_LIKE if reaction_type == 'like' else CommentReaction.REACTION_DISLIKE

    try:
        with transaction.atomic():
            existing_reaction = CommentReaction.objects.filter(user=request.user, comment=comment).first()
            if existing_reaction:
                if existing_reaction.reaction_type == reaction_value:
                    existing_reaction.delete()
                    if reaction_value == CommentReaction.REACTION_LIKE:
                        Comment.objects.filter(id=comment_id).update(likes=F('likes') - 1)
                    else:
                        Comment.objects.filter(id=comment_id).update(dislikes=F('dislikes') - 1)
                else:
                    existing_reaction.delete()
                    CommentReaction.objects.create(user=request.user, comment=comment, reaction_type=reaction_value)
                    if reaction_value == CommentReaction.REACTION_LIKE:
                        Comment.objects.filter(id=comment_id).update(likes=F('likes') + 1, dislikes=F('dislikes') - 1)
                    else:
                        Comment.objects.filter(id=comment_id).update(dislikes=F('dislikes') + 1, likes=F('likes') - 1)
            else:
                CommentReaction.objects.create(user=request.user, comment=comment, reaction_type=reaction_value)
                if reaction_value == CommentReaction.REACTION_LIKE:
                    Comment.objects.filter(id=comment_id).update(likes=F('likes') + 1)
                else:
                    Comment.objects.filter(id=comment_id).update(dislikes=F('dislikes') + 1)

        is_htmx = request.headers.get('HX-Request') == 'true'
        if is_htmx:
            comment.refresh_from_db()
            user_reactions = {
                r.comment_id: r.reaction_type
                for r in CommentReaction.objects.filter(user=request.user, comment__material=material)
            }
            level = int(request.GET.get('level', 0))
            html = render_to_string(
                'learner/partials/comment.html',
                {
                    'comment': comment,
                    'material': material,
                    'user_reactions': user_reactions,
                    'level': level,
                },
                request=request
            )
            return HttpResponse(html)

        redirect_url = reverse('learner:load_content', kwargs={
            'username': request.user.username,
            'slug': material.section.course.slug,
            'content_type': 'material',
            'content_id': material.id
        })
        return HttpResponseRedirect(redirect_url)

    except Exception as e:
        #logger.error(f"Error toggling reaction for comment {comment_id}: {str(e)}", exc_info=True)
        if request.headers.get('HX-Request') == 'true':
            return HttpResponse("Terjadi kesalahan saat memproses reaksi.", status=500)
        return HttpResponse(status=500)


logger = logging.getLogger(__name__)

def _get_navigation_urls(username, id, slug, combined_content, current_index):
    previous_url = None
    next_url = None
    try:
        if current_index > 0:
            prev_content = combined_content[current_index - 1]
            previous_url = reverse('learner:load_content', kwargs={
                'username': username,
                'id': id,
                'slug': slug,
                'content_type': prev_content[0],
                'content_id': prev_content[1].id
            })
        if current_index < len(combined_content) - 1:
            next_content = combined_content[current_index + 1]
            next_url = reverse('learner:load_content', kwargs={
                'username': username,
                'id': id,
                'slug': slug,
                'content_type': next_content[0],
                'content_id': next_content[1].id
            })# + '?from_next=1'  # Tambahkan parameter from_next
    except NoReverseMatch as e:
        logger.error(f"NoReverseMatch di _get_navigation_urls: {str(e)}")
        previous_url = None
        next_url = None
    return previous_url, next_url

@login_required
def my_course(request, username, id, slug):
    if request.user.username != username:
        logger.warning(f"Upaya akses tidak sah oleh {request.user.username} untuk {username}")
        return HttpResponse(status=403)
    
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

    course = get_object_or_404(Course, id=id, slug=slug)
    if not Enrollment.objects.filter(user=user, course=course).exists():
        logger.warning(f"Pengguna {user.username} tidak terdaftar di kursus {slug}")
        return HttpResponse(status=403)

    sections = Section.objects.filter(
        courses=course,
        parent__isnull=True
    ).order_by('order').prefetch_related(
        Prefetch(
            'children',
            queryset=Section.objects.order_by('order').prefetch_related(
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

    # ✅ FIX: pastikan combined_content selalu terdefinisi
    combined_content = []

    # Periksa apakah ini akses pertama
    last_access = LastAccessCourse.objects.filter(user=user, course=course).first()
    is_first_access = not last_access

    if is_first_access:
        request.session['show_welcome_modal'] = True

    if not last_access and combined_content:
        content_type, content_obj, _ = combined_content[0]
        last_access, created = LastAccessCourse.objects.get_or_create(
            user=user,
            course=course,
            defaults={
                'material': content_obj if content_type == 'material' else None,
                'assessment': content_obj if content_type == 'assessment' else None,
                'last_viewed_at': timezone.now()
            }
        )
        logger.debug(
            f"Created LastAccessCourse for user {user.id}, course {course.id}, "
            f"{content_type} {content_obj.id}"
        )

    if last_access and (last_access.material or last_access.assessment):
        content_type = 'material' if last_access.material else 'assessment'
        content_id = (
            last_access.material.id
            if last_access.material
            else last_access.assessment.id
        )
    elif combined_content:
        content_type, content_obj, _ = combined_content[0]
        content_id = content_obj.id
    else:
        content_type, content_id = None, None

    if content_type and content_id:
        redirect_url = reverse('learner:load_content', kwargs={
            'username': username,
            'id': id,
            'slug': slug,
            'content_type': content_type,
            'content_id': content_id
        })
        logger.info(f"Redirecting to load_content: {redirect_url}")
        return HttpResponseRedirect(redirect_url)

    user_progress, _ = CourseProgress.objects.get_or_create(
        user=user,
        course=course,
        defaults={'progress_percentage': 0}
    )

    context = {
        'course': course,
        'is_first_access': is_first_access,
        'course_name': course.course_name,
        'username': username,
        'slug': slug,
        'sections': sections,
        'current_content': None,
        'material': None,
        'assessment': None,
        'comments': None,
        'assessment_locked': False,
        'payment_required_url': None,
        'is_started': False,
        'is_expired': False,
        'remaining_time': 0,
        'answered_questions': {},
        'course_progress': user_progress.progress_percentage,
        'previous_url': None,
        'next_url': None,
        'ask_oras': [],
        'user_submissions': Submission.objects.none(),
        'askora_submit_status': {},
        'askora_can_submit': {},
        'peer_review_stats': None,
        'submissions': [],
        'can_submit': False,
        'can_review': False,
        'is_quiz': False,
        'is_lti': False,
        'show_timer': False,
        'lti_tool': None,
    }

    response = render(request, 'learner/my_course.html', context)
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


@login_required
def load_content(request, username, id, slug, content_type, content_id):
    if request.user.username != username:
        return HttpResponse(status=403)

    # Reset video quiz kalau ada parameter ?reset=1
    if request.GET.get('reset') == '1':
        QuizResult.objects.filter(user=request.user, assessment_id=content_id).delete()

    course = get_object_or_404(Course, id=id, slug=slug)
    if not Enrollment.objects.filter(user=request.user, course=course).exists():
        return HttpResponse(status=403)

    # ==================== LOGGING SESSION & IP ====================
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    ip = request.META.get('REMOTE_ADDR', '')
    if 'HTTP_X_FORWARDED_FOR' in request.META:
        ip = request.META['HTTP_X_FORWARDED_FOR'].split(',')[0].strip()

    try:
        from geoip2.database import Reader
        reader = Reader('/path/to/GeoLite2-City.mmdb')  # sesuaikan path jika perlu
        response = reader.city(ip)
        country = response.country.name
        city = response.city.name
    except Exception:
        country = city = None

    # Tutup session lama, buat baru
    CourseSessionLog.objects.filter(user=request.user, course=course, ended_at__isnull=True).update(ended_at=timezone.now())
    CourseSessionLog.objects.create(
        user=request.user, course=course, started_at=timezone.now(),
        user_agent=user_agent, ip_address=ip,
        location_country=country, location_city=city
    )

    # ==================== LAST ACCESS ====================
    LastAccessCourse.objects.update_or_create(
        user=request.user, course=course,
        defaults={
            'material_id': content_id if content_type == 'material' else None,
            'assessment_id': content_id if content_type == 'assessment' else None,
            'last_viewed_at': timezone.now()
        }
    )

    # ==================== PENANDAAN "READ" & UPDATE PROGRESS SAAT KLIK NEXT ====================
    if request.GET.get('from_next') == '1':
        prev_type = request.session.get('prev_content_type')
        prev_id = request.session.get('prev_content_id')
        if prev_type == 'material' and prev_id:
            MaterialRead.objects.get_or_create(user=request.user, material_id=prev_id)
        elif prev_type == 'assessment' and prev_id:
            AssessmentRead.objects.get_or_create(user=request.user, assessment_id=prev_id)

        prog, _ = CourseProgress.objects.get_or_create(user=request.user, course=course)
        prog.progress_percentage = calculate_course_progress(request.user, course)
        prog.save()

        # ================= CHECK COMPLETION =================
        grade_ranges = GradeRange.objects.filter(course=course).order_by('max_grade')
        if grade_ranges.exists():
            lowest_range = grade_ranges.first()
            passing_threshold = Decimal(lowest_range.max_grade) + Decimal(1)
        else:
            passing_threshold = Decimal('60')

        overall_percentage = Decimal(prog.progress_percentage)

        if overall_percentage >= passing_threshold:

            already_notified = Notification.objects.filter(
                user=request.user,
                notif_type='progress_milestone',
                actor=request.user,
                course=course  # 🔥 paling penting
            ).exists()

            if not already_notified:

                notif = Notification.objects.create(
                    user=request.user,
                    actor=request.user,
                    course=course,  # 🔥 tambahkan ini
                    notif_type='progress_milestone',
                    priority='high',
                    title=f"You completed {course.course_name} 🎉",
                    message=f"Congratulations! You have successfully completed {course.course_name}.",
                    link=f'/learner/{request.user.username}/{course.id}/score-summary/'
                )

                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    f"user_{request.user.id}",
                    {
                        "type": "send_notification",
                        "id": notif.id,
                        "notif_type": notif.notif_type,
                        "title": notif.title,
                        "message": notif.message,
                        "link": notif.link,
                        "created_at": notif.created_at.isoformat(),
                        "actor_username": request.user.username,
                    }
                )


    # Simpan konten saat ini untuk next time
    request.session['prev_content_type'] = content_type
    request.session['prev_content_id'] = content_id

    # ==================== BASE CONTEXT ====================
    sections = Section.objects.filter(courses=course).prefetch_related(
        Prefetch('materials'), Prefetch('assessments')
    ).order_by('order')
    combined_content = _build_combined_content(sections)
    show_welcome_modal = request.session.pop('show_welcome_modal', False)

    context = {
        'course': course,
        'username': username,
        'slug': slug,
        'sections': sections,
        'current_content': None,
        'material': None,
        'assessment': None,
        'comments': None,
        'assessment_locked': False,
        'payment_required_url': None,
        'is_quiz': False,
        'is_video_quiz': False,
        'is_lti': False,
        'lti_tool': None,
        'video': None,
        'quizzes_json': '[]',
        'result_json': None,
        'ask_oras': [],
        'askora_can_submit': {},  # {askora_id: True/False}
        'course_progress': CourseProgress.objects.get_or_create(user=request.user, course=course)[0].progress_percentage,
        'previous_url': None,
        'next_url': None,
        'show_welcome_modal': show_welcome_modal,
    }

    current_index = 0

    # ===================================================================
    # MATERIAL
    # ===================================================================
    if content_type == 'material':
        material = get_object_or_404(Material, id=content_id)
        # !!! TIDAK LAGI OTOMATIS TANDAI READ DI SINI !!!
        # MaterialRead hanya dibuat saat klik NEXT (lihat di atas)

        context.update({
            'material': material,
            'current_content': ('material', material, next((s for s in sections if material in s.materials.all()), None)),
            'comments': Comment.objects.filter(material=material, parent=None)
                              .select_related('user').prefetch_related('children').order_by('-created_at'),
        })
        current_index = next((i for i, (t, obj, _) in enumerate(combined_content)
                             if t == 'material' and obj.id == content_id), 0)

    # ===================================================================
    # ASSESSMENT – DETEKSI TIPE DENGAN TEPAT
    # ===================================================================
    elif content_type == 'assessment':
        assessment = get_object_or_404(Assessment, id=content_id)
        context['assessment'] = assessment
        context['current_content'] = ('assessment', assessment, next((s for s in sections if assessment in s.assessments.all()), None))
        current_index = next((i for i, (t, obj, _) in enumerate(combined_content)
                             if t == 'assessment' and obj.id == content_id), 0)

        # LTI Tool
        context['lti_tool'] = getattr(assessment, 'lti_tool', None)
        context['is_lti'] = bool(context['lti_tool'])

        # Payment lock (buy_take_exam)
        if course.payment_model and course.payment_model.code == 'buy_take_exam':
            if not Payment.objects.filter(user=request.user, course=course,
                                          status='completed', payment_model='buy_take_exam').exists():
                context['assessment_locked'] = True
                context['payment_required_url'] = reverse('payments:process_payment', kwargs={
                    'course_id': course.id, 'payment_type': 'exam'
                })

        # Kalau terkunci, skip semua logika di bawah
        if context['assessment_locked']:
            pass
        else:
            # 1. IN-VIDEO QUIZ (prioritas tertinggi)
            if assessment.quizzes.exists():
                context['is_video_quiz'] = True

                video = assessment.quizzes.first().video
                result = QuizResult.objects.filter(user=request.user, video=video, assessment=assessment).first()
                if result:
                    # Hanya tandai read jika quiz sudah selesai
                    AssessmentRead.objects.get_or_create(user=request.user, assessment=assessment)

                quizzes_data = []
                for q in assessment.quizzes.all().order_by('time_in_video'):
                    d = {
                        "time": float(q.time_in_video),
                        "question": q.question,
                        "explanation": q.explanation or "",
                    }
                    if q.question_type == "MC":
                        d["type"] = "multiple-choice"
                        d["options"] = [o.text for o in q.options.all()]
                        d["correct"] = next((i for i, o in enumerate(q.options.all()) if o.is_correct), 0)
                    elif q.question_type == "TF":
                        d["type"] = "true-false"
                        d["correct"] = str(q.correct_answer_text or "").strip().lower() in ["true", "benar", "1", "yes"]
                    elif q.question_type in ["FB", "ES"]:
                        d["type"] = "fill-blank"
                        d["correct"] = (q.correct_answer_text or "").strip()
                    elif q.question_type == "DD":
                        d["type"] = "drag-and-drop"
                        d["items"] = [o.text for o in q.options.all()]
                        d["correct"] = q.correct_answer_text or ""
                    quizzes_data.append(d)

                result_json = None
                if result:
                    result_json = {
                        "score": result.score,
                        "total_questions": result.total_questions,
                        "answers": result.answers or {}
                    }

                context.update({
                    'video': video,
                    'quizzes_json': json.dumps(quizzes_data, ensure_ascii=False),
                    'result_json': json.dumps(result_json, ensure_ascii=False) if result_json else None,
                })

            # 2. OPEN RESPONSE ASSESSMENT (ORA)
            elif AskOra.objects.filter(assessment=assessment).exists():
                ask_oras = AskOra.objects.filter(assessment=assessment).order_by('created_at')

                can_submit_dict = {}
                user_submissions_dict = {}

                for ao in ask_oras:
                    submission = Submission.objects.filter(user=request.user, askora=ao).first()

                    if submission:
                        can_submit_dict[ao.id] = False
                        user_submissions_dict[ao.id] = submission
                    else:
                        is_still_open = timezone.now() <= ao.response_deadline if ao.response_deadline else True
                        can_submit_dict[ao.id] = is_still_open
                        user_submissions_dict[ao.id] = None

                user_has_submitted = any(user_submissions_dict.values())
                submissions_to_review = []
                peer_review_stats = {
                    'total_participants': 0,
                    'distinct_reviewers': 0,
                    'avg_score': None,
                }

                if user_has_submitted:
                    all_submissions = Submission.objects.filter(askora__assessment=assessment).exclude(user=request.user)
                    total_enrolled = Enrollment.objects.filter(course=course).count()
                    peer_review_stats['total_participants'] = max(1, total_enrolled - 1)

                    for subm in all_submissions:
                        if not PeerReview.objects.filter(submission=subm, reviewer=request.user).exists():
                            submissions_to_review.append(subm)

                    user_reviews = PeerReview.objects.filter(
                        submission__user=request.user,
                        submission__askora__assessment=assessment
                    )
                    distinct = user_reviews.values('reviewer').distinct().count()
                    avg = user_reviews.aggregate(Avg('score'))['score__avg']

                    peer_review_stats.update({
                        'distinct_reviewers': distinct,
                        'avg_score': round(avg, 2) if avg else None,
                    })

                context.update({
                    'ask_oras': ask_oras,
                    'askora_can_submit': can_submit_dict,
                    'user_submissions': [s for s in user_submissions_dict.values() if s],
                    'submissions': submissions_to_review,
                    'can_review': len(submissions_to_review) > 0 and user_has_submitted,
                    'peer_review_stats': peer_review_stats,
                    'has_other_submissions': Submission.objects.filter(askora__assessment=assessment).exclude(user=request.user).exists(),
                })

            # 3. KUIS PILIHAN GANDA BIASA (fallback)
            else:
                context['is_quiz'] = True

                session = AssessmentSession.objects.filter(user=request.user, assessment=assessment).first()
                if session:
                    context['is_started'] = True
                    if session.end_time:
                        remaining = int((session.end_time - timezone.now()).total_seconds())
                        context['remaining_time'] = max(0, remaining)
                        context['is_expired'] = remaining <= 0
                        context['show_timer'] = remaining > 0
                        context['is_readonly'] = remaining <= 0

                    context['answered_questions'] = {
                        ans.question.id: ans for ans in QuestionAnswer.objects.filter(
                            user=request.user, question__assessment=assessment
                        ).select_related('question', 'choice')
                    }

                context.update(_build_assessment_context(assessment, request.user))

    # ===================================================================
    # NAVIGASI PREV / NEXT
    # ===================================================================
    context['previous_url'], context['next_url'] = _get_navigation_urls(
        username, id, slug, combined_content, current_index
    )

    # ===================================================================
    # RENDER
    # ===================================================================
    template = 'learner/partials/content.html' if request.headers.get('HX-Request') else 'learner/my_course.html'
    response = render(request, template, context)
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response




@login_required
def save_invideo_quiz(request, video_id, assessment_id):
    if request.method == "POST":
        import json
        data = json.loads(request.body)

        video = get_object_or_404(Video, id=video_id)
        assessment = get_object_or_404(Assessment, id=assessment_id)

        answers = data.get("answers", {})
        score = data.get("score", 0)

        # jumlah soal yang benar-benar muncul untuk video + assessment ini
        total_questions = Quiz.objects.filter(
            video=video,
            assessment=assessment
        ).count()

        # simpan atau update
        QuizResult.objects.update_or_create(
            user=request.user,
            video=video,
            assessment=assessment,
            defaults={
                "answers": answers,
                "score": score,
                "total_questions": total_questions,
            }
        )

        return JsonResponse({"status": "saved"}, status=200)

    return JsonResponse({"error": "invalid request"}, status=400)



logger = logging.getLogger(__name__)

#@csrf_exempt
@login_required
@require_POST
def mark_progress(request):
    try:
        if not request.body:
            logger.warning("Empty request body in mark_progress")
            return JsonResponse({'error': 'Empty request body'}, status=400)

        try:
            data = json.loads(request.body)
            logger.debug(f"Parsed JSON data: {data}")  # For debugging
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON in mark_progress: {e}")
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        content_type = data.get('content_type')
        content_id = data.get('content_id')

        if not content_type or not content_id:
            logger.warning(f"Missing content_type or content_id: {data}")
            return JsonResponse({'error': 'Missing content_type or content_id'}, status=400)

        user = request.user
        course = None

        with transaction.atomic():  # Ensures atomicity for progress calc
            if content_type == 'material':
                material = Material.objects.filter(id=content_id).select_related('section').first()
                if not material:
                    return JsonResponse({'error': 'Material not found'}, status=404)
                MaterialRead.objects.get_or_create(user=user, material=material)
                if hasattr(material, 'section') and material.section:
                    course = getattr(material.section, 'course', None)  # Assuming one course per section; adjust if M2M

            elif content_type == 'assessment':
                assessment = Assessment.objects.filter(id=content_id).select_related('section').first()
                if not assessment:
                    return JsonResponse({'error': 'Assessment not found'}, status=404)
                AssessmentRead.objects.get_or_create(user=user, assessment=assessment)
                if hasattr(assessment, 'section') and assessment.section:
                    course = getattr(assessment.section, 'course', None)  # Same as above

            else:
                return JsonResponse({'error': 'Invalid content_type'}, status=400)

            if course:
                progress, created = CourseProgress.objects.get_or_create(user=user, course=course)
                if not created:  # Only recalc if existing
                    progress.progress_percentage = calculate_course_progress(user, course)
                    progress.save(update_fields=['progress_percentage'])
                logger.info(f"Updated progress for user {user.id} in course {course.id}: {progress.progress_percentage}%")

        return JsonResponse({'status': 'success'})

    except Exception as e:
        logger.exception("Unexpected error in mark_progress")
        return JsonResponse({'error': 'Internal server error'}, status=500)

@login_required
def start_assessment_courses(request, assessment_id):
    if request.method != 'POST':
        #logger.error(f"Invalid request method: {request.method} for start_assessment")
        return render(request, 'learner/partials/error.html', {
            'error_message': 'Permintaan tidak valid.'
        }, status=400) if request.headers.get('HX-Request') == 'true' else HttpResponse(status=400)

    assessment = get_object_or_404(Assessment.objects.select_related('section__courses'), id=assessment_id)
    course = assessment.section.courses
    if not Enrollment.objects.filter(user=request.user, course=course).exists():
        #logger.warning(f"User {request.user.username} not enrolled in course {course.slug}")
        return render(request, 'learner/partials/error.html', {
            'error_message': 'Anda tidak terdaftar di kursus ini.'
        }, status=403) if request.headers.get('HX-Request') == 'true' else HttpResponse(status=403)

    session, created = AssessmentSession.objects.get_or_create(
        user=request.user, assessment=assessment,
        defaults={
            'start_time': timezone.now(),
            'end_time': timezone.now() + timedelta(minutes=assessment.duration_in_minutes) if assessment.duration_in_minutes > 0 else None
        }
    )
    if not created and session.end_time and session.end_time > timezone.now():
       # logger.debug(f"Using existing session for user {request.user.username}, assessment {assessment_id}")
       pass
    else:
        session.start_time = timezone.now()
        session.end_time = timezone.now() + timedelta(minutes=assessment.duration_in_minutes) if assessment.duration_in_minutes > 0 else None
        session.save()
       # logger.debug(f"{'New' if created else 'Reset'} session for user {request.user.username}, assessment {assessment_id}")

    user_progress, _ = CourseProgress.objects.get_or_create(user=request.user, course=course)

    context = {
        'course': course,
        'course_name': course.course_name,
        'username': request.user.username,
        'slug': course.slug,
        'sections': Section.objects.filter(courses=course).prefetch_related('materials', 'assessments').order_by('order'),
        'current_content': ('assessment', assessment, assessment.section),
        'material': None,
        'assessment': assessment,
        'comments': None,
        'assessment_locked': False,
        'payment_required_url': None,
        'is_started': True,
        'is_expired': False,
        'remaining_time': max(0, int((session.end_time - timezone.now()).total_seconds())) if session.end_time else 0,
        'answered_questions': {
            answer.question.id: answer for answer in QuestionAnswer.objects.filter(
                user=request.user, question__assessment=assessment
            ).select_related('question', 'choice')
        },
        'course_progress': user_progress.progress_percentage,
        'previous_url': None,
        'next_url': None,
    }

    context.update(_build_assessment_context(assessment, request.user))
    context['show_timer'] = context['remaining_time'] > 0
    context['is_expired'] = context['remaining_time'] <= 0
    context['can_review'] = bool(context['submissions'])

    combined_content = _build_combined_content(context['sections'])
    current_index = next((i for i, c in enumerate(combined_content) if c[0] == 'assessment' and c[1].id == assessment_id), 0)
    context['previous_url'], context['next_url'] = _get_navigation_urls(request.user.username, course.id, course.slug, combined_content, current_index)

    if course.payment_model.code == 'buy_take_exam':
        has_paid = Payment.objects.filter(
            user=request.user, course=course, status='completed', payment_model='buy_take_exam'
        ).exists()
        if not has_paid:
            context['assessment_locked'] = True
            context['payment_required_url'] = reverse('payments:process_payment', kwargs={
                'course_id': course.id,
                'payment_type': 'exam'
            })
        else:
            AssessmentRead.objects.get_or_create(user=request.user, assessment=assessment)
            user_progress.progress_percentage = calculate_course_progress(request.user, course)
            user_progress.save()
    else:
        AssessmentRead.objects.get_or_create(user=request.user, assessment=assessment)
        user_progress.progress_percentage = calculate_course_progress(request.user, course)
        user_progress.save()

    context['course_progress'] = user_progress.progress_percentage

    is_htmx = request.headers.get('HX-Request') == 'true'
    if not is_htmx:
        redirect_url = reverse('learner:load_content', kwargs={
            'username': request.user.username, 'id': course.id, 'slug': course.slug,
            'content_type': 'assessment', 'content_id': assessment.id
        })
        #logger.info(f"Redirecting non-HTMX request to: {redirect_url}")
        return HttpResponseRedirect(redirect_url)

    #logger.info(f"start_assessment: Rendering HTMX for user {request.user.username}, assessment {assessment_id}, time_left={context['remaining_time']}")
    response = render(request, 'learner/partials/content.html', context)
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


@login_required
def submit_assessment_new(request, assessment_id):
    """
    Submit an assessment, save user answers, end the session, 
    calculate score, and save it in AssessmentResult.
    """
    # ✅ Pastikan request POST
    if request.method != 'POST':
        logger.warning(f"Invalid request method: {request.method} for submit_assessment_new")
        if request.headers.get('HX-Request') == 'true':
            return render(request, 'learner/partials/error.html', {
                'error_message': 'Permintaan tidak valid.'
            }, status=400)
        return HttpResponse(status=400)

    # ✅ Ambil assessment dan course terkait
    assessment = get_object_or_404(
        Assessment.objects.select_related('section__courses'),
        id=assessment_id
    )
    course = assessment.section.courses

    # ✅ Ambil session user saat ini
    session = AssessmentSession.objects.filter(user=request.user, assessment=assessment).first()
    if not session:
        logger.error(f"No session found for user {request.user.username}, assessment {assessment_id}")
        if request.headers.get('HX-Request') == 'true':
            return render(request, 'learner/partials/error.html', {
                'error_message': 'Sesi penilaian tidak ditemukan.'
            }, status=400)
        return HttpResponse(status=400)

    # ⬇️ SIMPAN JAWABAN PILIHAN GANDA
    # Ambil semua POST yang mulai dengan 'answers_'
    answers = {
        key.split('_')[1]: value
        for key, value in request.POST.items()
        if key.startswith('answers_')
    }

    # Loop jawaban, simpan/update QuestionAnswer
    for question_id, choice_id in answers.items():
        try:
            question = Question.objects.get(id=question_id, assessment=assessment)
            choice = Choice.objects.get(id=choice_id, question=question)

            QuestionAnswer.objects.update_or_create(
                user=request.user,
                question=question,
                defaults={'choice': choice}
            )
        except (Question.DoesNotExist, Choice.DoesNotExist) as e:
            logger.warning(f"Invalid answer data for question {question_id}: {e}")
            continue

    # ⬇️ AKHIR SESI
    session.end_time = timezone.now()
    session.save()

    logger.debug(f"Assessment submitted for user {request.user.username}, assessment {assessment_id}")

    # ⬇️ HITUNG NILAI OTOMATIS
    answers_qs = QuestionAnswer.objects.filter(
        user=request.user,
        question__assessment=assessment
    ).select_related('question', 'choice')

    total_questions = assessment.questions.count()
    correct_answers = sum(1 for answer in answers_qs if answer.choice.is_correct)
    percentage = (correct_answers / total_questions * 100) if total_questions > 0 else 0

    # ⬇️ SIMPAN HASIL KE AssessmentResult
    AssessmentResult.objects.update_or_create(
        user=request.user,
        assessment=assessment,
        session=session,
        defaults={
            'total_questions': total_questions,
            'correct_answers': correct_answers,
            'score': percentage,
        }
    )

    # ⬇️ BANGUN CONTEXT UNTUK TEMPLATE
    context = {
        'course': course,
        'course_name': course.course_name,
        'username': request.user.username,
        'slug': course.slug,
        'sections': Section.objects.filter(courses=course).prefetch_related('materials', 'assessments').order_by('order'),
        'current_content': ('assessment', assessment, assessment.section),
        'material': None,
        'assessment': assessment,
        'comments': None,
        'assessment_locked': False,
        'payment_required_url': None,
        'is_started': True,
        'is_expired': True,
        'remaining_time': 0,
        'answered_questions': {
            answer.question.id: answer for answer in answers_qs
        },
        'course_progress': CourseProgress.objects.get_or_create(user=request.user, course=course)[0].progress_percentage,
        'previous_url': None,
        'next_url': None,
        'assessment_result': AssessmentResult.objects.get(
            user=request.user,
            assessment=assessment,
            session=session
        ),
    }

    # Tambahan helper context jika ada
    context.update(_build_assessment_context(assessment, request.user))
    context['can_review'] = bool(context['submissions'])

    # ⬇️ Bangun navigasi previous/next
    combined_content = _build_combined_content(context['sections'])
    current_index = next(
        (i for i, c in enumerate(combined_content) if c[0] == 'assessment' and c[1].id == assessment_id),
        0
    )
    context['previous_url'], context['next_url'] = _get_navigation_urls(
        request.user.username, course.id, course.slug, combined_content, current_index
    )

    # ⬇️ HANDLE HTMX REQUEST
    is_htmx = request.headers.get('HX-Request') == 'true'
    if not is_htmx:
        redirect_url = reverse('learner:load_content', kwargs={
            'username': request.user.username,
            'slug': course.slug,
            'content_type': 'assessment',
            'content_id': assessment.id
        })
        logger.info(f"Redirecting non-HTMX request to: {redirect_url}")
        return HttpResponseRedirect(redirect_url)

    # ⬇️ Render HTMX response
    logger.info(f"submit_assessment_new: Rendering HTMX for user {request.user.username}, assessment {assessment_id}")
    response = render(request, 'learner/partials/content.html', context)
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


@login_required
def submit_answer(request):
    """
    Submit an answer for a quiz question.
    
    Args:
        request: HTTP request object.
    
    Returns:
        HttpResponse: Rendered assessment partial.
    """
    if request.method != 'POST':
        logger.warning(f"Invalid request method: {request.method} for submit_answer")
        return render(request, 'learner/partials/error.html', {
            'error_message': 'Permintaan tidak valid.'
        }, status=400) if request.headers.get('HX-Request') == 'true' else HttpResponse(status=400)

    question_id = request.POST.get('question_id')
    choice_id = request.POST.get('choice_id')
    if not question_id or not choice_id:
        logger.warning(f"Missing question_id or choice_id for user {request.user.username}")
        return render(request, 'learner/partials/error.html', {
            'error_message': 'Pilihan tidak valid.'
        }, status=400) if request.headers.get('HX-Request') == 'true' else HttpResponse(status=400)

    question = get_object_or_404(Question, id=question_id)
    choice = get_object_or_404(Choice, id=choice_id, question=question)
    assessment = question.assessment
    course = assessment.section.courses  # Changed 'course' to 'courses'

    if not Enrollment.objects.filter(user=request.user, course=course).exists():
        logger.warning(f"User {request.user.username} not enrolled in course {course.slug}")
        return render(request, 'learner/partials/error.html', {
            'error_message': 'Anda tidak terdaftar di kursus ini.'
        }, status=403) if request.headers.get('HX-Request') == 'true' else HttpResponse(status=403)

    session = AssessmentSession.objects.filter(user=request.user, assessment=assessment).first()
    if not session or (session.end_time and session.end_time < timezone.now()):
        logger.warning(f"No session or session expired for user {request.user.username}, assessment {assessment.id}")
        return render(request, 'learner/partials/error.html', {
            'error_message': 'Sesi penilaian tidak valid atau telah kedaluwarsa.'
        }, status=403) if request.headers.get('HX-Request') == 'true' else HttpResponse(status=403)

    QuestionAnswer.objects.update_or_create(
        user=request.user, question=question,
        defaults={'choice': choice}
    )
    logger.debug(f"Answer submitted for user {request.user.username}, question {question_id}, choice {choice_id}")

    context = {
        'course': course,
        'course_name': course.course_name,
        'username': request.user.username,
        'slug': course.slug,
        'sections': Section.objects.filter(courses=course).prefetch_related('materials', 'assessments').order_by('order'),
        'current_content': ('assessment', assessment, assessment.section),
        'material': None,
        'assessment': assessment,
        'comments': None,
        'assessment_locked': False,
        'payment_required_url': None,
        'is_started': True,
        'is_expired': session.end_time and session.end_time < timezone.now(),
        'remaining_time': max(0, int((session.end_time - timezone.now()).total_seconds())) if session.end_time else 0,
        'answered_questions': {
            answer.question.id: answer for answer in QuestionAnswer.objects.filter(
                user=request.user, question__assessment=assessment
            ).select_related('question', 'choice')
        },
        'course_progress': CourseProgress.objects.get_or_create(user=request.user, course=course)[0].progress_percentage,
        'previous_url': None,
        'next_url': None,
    }

    context.update(_build_assessment_context(assessment, request.user))
    context['show_timer'] = context['remaining_time'] > 0
    context['can_review'] = bool(context['submissions'])

    combined_content = _build_combined_content(context['sections'])
    current_index = next((i for i, c in enumerate(combined_content) if c[0] == 'assessment' and c[1].id == assessment.id), 0)
    context['previous_url'], context['next_url'] = _get_navigation_urls(request.user.username,course.id, course.slug, combined_content, current_index)

    is_htmx = request.headers.get('HX-Request') == 'true'
    logger.info(f"submit_answer: Rendering HTMX for user {request.user.username}, assessment {assessment.id}, question {question_id}")
    response = render(request, 'learner/partials/content.html', context)
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response

def is_bot(request):
    """
    Check if the request originates from a bot based on User-Agent.
    
    Args:
        request: HTTP request object.
    
    Returns:
        bool: True if bot detected, False otherwise.
    """
    user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
    return 'bot' in user_agent or 'crawler' in user_agent

def is_suspicious(request):
    """
    Check if the request is suspicious based on User-Agent or missing Referer.
    
    Args:
        request: HTTP request object.
    
    Returns:
        bool: True if suspicious, False otherwise.
    """
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    referer = request.META.get('HTTP_REFERER', '')
    return 'bot' in user_agent.lower() or not referer

def is_spam(request, user, content):
    """
    Check if a comment is spam based on rate-limiting, bot detection, and blacklisted keywords.
    
    Args:
        request: HTTP request object.
        user: CustomUser object.
        content: Comment content.
    
    Returns:
        bool: True if spam detected, False otherwise.
    """
    if is_bot(request):
        logger.warning(f"Bot detected in comment attempt by {user.username}")
        return True

    time_limit = timedelta(seconds=30)
    last_comment = Comment.objects.filter(user=user).order_by('-created_at').first()
    if last_comment and timezone.now() - last_comment.created_at < time_limit:
        logger.warning(f"Rate limit exceeded for user {user.username}")
        return True

    comment_instance = Comment(user=user, content=content)
    if comment_instance.contains_blacklisted_keywords():
        logger.warning(f"Blacklisted keywords detected in comment by {user.username}: {content}")
        return True

    return False

@login_required
def add_comment(request):
    """
    Add a comment to a material, with spam and security checks.
    Returns HTMX partial or full redirect depending on request.
    """
    if request.method != "POST":
        logger.warning(f"Invalid request method: {request.method}")
        if request.headers.get("HX-Request") == "true":
            return HttpResponse("Permintaan tidak valid.", status=400)
        messages.warning(request, "Permintaan tidak valid.")
        return HttpResponse(status=400)

    comment_text = request.POST.get("comment_text")
    material_id = request.POST.get("material_id")
    parent_id = request.POST.get("parent_id")

    if not comment_text or not material_id:
        logger.warning(f"Missing fields: comment_text={bool(comment_text)}, material_id={material_id}")
        if request.headers.get("HX-Request") == "true":
            return HttpResponse("Komentar dan ID materi diperlukan.", status=400)
        messages.warning(request, "Komentar dan ID materi diperlukan.")
        return HttpResponse(status=400)

    material = get_object_or_404(Material, id=material_id)
    course = material.section.courses
    parent_comment = get_object_or_404(Comment, id=parent_id, material=material) if parent_id else None

    # Cek suspicious / spam / blacklisted keyword
    message = None
    comment = Comment(user=request.user, material=material, content=comment_text, parent=parent_comment)

    if is_suspicious(request):
        logger.warning(f"Suspicious activity detected: {request.user.username}")
        message = "Aktivitas mencurigakan terdeteksi."
    elif is_spam(request, request.user, comment_text):
        logger.warning(f"Spam comment detected: {request.user.username}")
        message = "Komentar Anda terdeteksi sebagai spam!"
    elif comment.contains_blacklisted_keywords():
        logger.warning(f"Blacklisted keyword detected in comment: {request.user.username}")
        message = "Komentar mengandung kata-kata yang tidak diizinkan."
    else:
        comment.save()
        # Kirim notifikasi ke instructor hanya jika instructor ada dan bukan diri sendiri
        instructor_user = course.instructor.user if course.instructor else None
        if instructor_user and instructor_user != request.user:
            Notification.objects.create(
                user=instructor_user,                 # instructor
                actor=request.user,                   # peserta yang komentar
                notif_type='new_comment',             # tipe notif, tambahkan di Notification.NOTIF_TYPES
                priority='medium',
                title=f"New comment on {material.title}",
                message=f"{request.user.username} commented on '{material.title}' in {course.course_name}.",
                link=f'/message_comment'  # deep link ke komentar
            )
        logger.debug(f"Comment added by {request.user.username} for material {material_id}, parent_id={parent_id}")

    # Context untuk template partial
    context = {
        "comments": Comment.objects.filter(material=material, parent=None)
                                   .select_related("user", "parent")
                                   .prefetch_related("children"),
        "material": material,
        "user_reactions": {
            r.comment_id: r.reaction_type
            for r in CommentReaction.objects.filter(user=request.user, comment__material=material)
        },
        "message": message,
    }

    if request.headers.get("HX-Request") == "true":
        return render(request, "learner/partials/comments.html", context)

    # Non-HTMX fallback
    if message:
        messages.warning(request, message)
    else:
        messages.success(request, "Komentar berhasil diposting!")

    return HttpResponseRedirect(reverse(
        "learner:load_content",
        kwargs={
            "username": request.user.username,
            "slug": course.slug,
            "content_type": "material",
            "content_id": material_id
        }
    ))




@login_required
def get_progress(request, username, slug):
    """
    Get the progress bar for a course.
    
    Args:
        request: HTTP request object.
        username: Username of the user.
        slug: Course slug.
    
    Returns:
        HttpResponse: Rendered progress partial.
    """
    if request.user.username != username:
        logger.warning(f"Unauthorized access attempt by {request.user.username} for {username}")
        return HttpResponse(status=403)

    course = get_object_or_404(Course, slug=slug)
    user_progress, _ = CourseProgress.objects.get_or_create(user=request.user, course=course)
    return render(request, 'learner/partials/progress.html', {'course_progress': user_progress.progress_percentage})


def calculate_course_progress(user, course):
    """
    Hitung progress kursus secara akurat: total konten yang sudah dibaca / total konten.
    """
    # Ambil semua materi & assessment di course ini
    materials = Material.objects.filter(section__courses=course)
    assessments = Assessment.objects.filter(section__courses=course)

    total_content = materials.count() + assessments.count()
    
    if total_content == 0:
        return 100

    # Hitung yang sudah dibaca
    read_materials = MaterialRead.objects.filter(
        user=user,
        material__section__courses=course
    ).count()

    read_assessments = AssessmentRead.objects.filter(
        user=user,
        assessment__section__courses=course
    ).count()

    completed = read_materials + read_assessments

    return round((completed / total_content) * 100)

@login_required
def submit_answer_askora_new(request, ask_ora_id):
    if request.method != 'POST':
        return HttpResponseBadRequest("Invalid request")

    ask_ora = get_object_or_404(AskOra, id=ask_ora_id)
    assessment = ask_ora.assessment
    course = assessment.section.courses
    user = request.user

    # Cek apakah user sudah submit
    already_submitted = Submission.objects.filter(askora=ask_ora, user=user).exists()

    if not already_submitted:
        Submission.objects.create(
            askora=ask_ora,
            user=user,
            answer_text=request.POST.get('answer_text'),
            answer_file=request.FILES.get('answer_file')
        )

    # Feedback HTMX
    message_html = (
        '<span class="text-success">Jawaban berhasil dikirim!</span>'
        if not already_submitted else
        '<span class="text-warning">Anda sudah mengirimkan jawaban!</span>'
    )

    # ===============================
    # Build context menggunakan helper existing
    # ===============================
    sections = Section.objects.filter(courses=course).prefetch_related(
        'children', 'materials', 'assessments'
    ).order_by('order')

    combined_content = _build_combined_content(sections)

    # Tentukan index konten saat ini
    current_index = next(
        (i for i, c in enumerate(combined_content) if c[0] == 'assessment' and c[1].id == assessment.id),
        0
    )

    # Ambil context assessment
    assessment_context = _build_assessment_context(assessment, user)

    # Ambil URL navigasi
    previous_url, next_url = _get_navigation_urls(user.username, course.id, course.slug, combined_content, current_index)

    # Gabungkan semua context
    context = {
        'course': course,
        'sections': sections,
        'assessment': assessment,
        'current_content': ('assessment', assessment, assessment.section),
        'username': request.user.username,
        'previous_url': previous_url,
        'next_url': next_url,
        'disable_next': False,  # pastikan tombol Next tetap aktif
        'hx_message': message_html,  # feedback HTMX
        **assessment_context
    }

    return render(request, 'learner/partials/content.html', context)


@login_required
def submit_peer_review_new(request, submission_id):
    """
    Menyimpan peer review untuk submisi tertentu dan merender ulang halaman assessment
    menggunakan pola yang sama seperti submit_answer_askora_new agar tombol Next tetap aktif.
    """
    if request.method != 'POST':
        return HttpResponseBadRequest("Invalid request")

    submission = get_object_or_404(Submission, id=submission_id)
    assessment = submission.askora.assessment
    course = assessment.section.courses
    user = request.user

    # Cek apakah user sudah review submission ini
    already_reviewed = PeerReview.objects.filter(submission=submission, reviewer=user).exists()

    hx_message = ""
    if already_reviewed:
        hx_message = '<span class="text-warning">Anda sudah mereview submisi ini!</span>'
    else:
        score_raw = request.POST.get('score')
        comment = request.POST.get('comment', '').strip()
        try:
            if not score_raw:
                raise ValueError("Score tidak boleh kosong")
            score = int(score_raw)
            if not 1 <= score <= 5:
                raise ValueError("Nilai harus antara 1 hingga 5")

            PeerReview.objects.create(
                submission=submission,
                reviewer=user,
                score=score,
                comment=comment or None
            )
            hx_message = '<span class="text-success">Review berhasil dikirim!</span>'

            # Kirim notifikasi ke owner submission
            owner_user = submission.user
            if owner_user != user:
                Notification.objects.create(
                    user=owner_user,
                    actor=user,
                    notif_type='submission_received',
                    priority='medium',
                    title=f"Your submission received a review",
                    message=f"{user.username} reviewed your submission for '{assessment.name}' in {course.course_name}.",
                    link=f'/{owner_user.username}/{course.id}/{course.slug}/assessment/{assessment.id}/',
                    content_type=ContentType.objects.get_for_model(PeerReview),
                    object_id=PeerReview.objects.last().id
                )

            # Hitung skor final submission
            assessment_score, _ = AssessmentScore.objects.get_or_create(submission=submission)
            assessment_score.calculate_final_score()

        except Exception as e:
            hx_message = f'<span class="text-danger">Error: {str(e)}</span>'

    # ===============================
    # Build context menggunakan helper existing
    # ===============================
    sections = Section.objects.filter(courses=course).prefetch_related(
        'children', 'materials', 'assessments'
    ).order_by('order')

    combined_content = _build_combined_content(sections)

    current_index = next(
        (i for i, c in enumerate(combined_content) if c[0] == 'assessment' and c[1].id == assessment.id),
        0
    )

    assessment_context = _build_assessment_context(assessment, user)
    previous_url, next_url = _get_navigation_urls(user.username, course.id, course.slug, combined_content, current_index)

    context = {
        'course': course,
        'sections': sections,
        'assessment': assessment,
        'current_content': ('assessment', assessment, assessment.section),
        'username': request.user.username,
        'previous_url': previous_url,
        'next_url': next_url,
        'disable_next': False,  # pastikan tombol Next tetap aktif
        'hx_message': hx_message,  # feedback HTMX
        **assessment_context
    }

    return render(request, 'learner/partials/content.html', context)



def render_content(request, assessment, course):
    """
    Helper function untuk merender ulang template content.html dengan konteks lengkap.
    
    Args:
        request: Objek HTTP request.
        assessment: Objek Assessment.
        course: Objek Course.
    
    Returns:
        HttpResponse: Render template content.html.
    """
    sections = Section.objects.filter(courses=course).prefetch_related(
        Prefetch('materials', queryset=Material.objects.all()),
        Prefetch('assessments', queryset=Assessment.objects.all())
    ).order_by('order')

    # Bangun combined_content untuk navigasi
    combined_content = []
    for section in sections:
        for material in section.materials.all():
            combined_content.append(('material', material))
        for assessment_item in section.assessments.all():
            combined_content.append(('assessment', assessment_item))
    current_index = next((i for i, c in enumerate(combined_content) if c[0] == 'assessment' and c[1].id == assessment.id), 0)

    # Filter submisi yang belum direview
    submissions = Submission.objects.filter(
        askora__assessment=assessment
    ).exclude(user=request.user).exclude(
        id__in=PeerReview.objects.filter(reviewer=request.user).values('submission__id')
    )
    
    # Periksa apakah ada submisi dari pengguna lain
    has_other_submissions = Submission.objects.filter(
        askora__assessment=assessment
    ).exclude(user=request.user).exists()

    # Bangun konteks
    context = {
        'course': course,
        'course_name': course.course_name,
        'username': request.user.username,
        'id': course.id,
        'slug': course.slug,
        'sections': sections,
        'current_content': ('assessment', assessment, assessment.section),
        'material': None,
        'assessment': assessment,
        'comments': None,
        'assessment_locked': False,
        'payment_required_url': None,
        'is_started': False,
        'is_expired': False,
        'remaining_time': 0,
        'answered_questions': {},
        'course_progress': CourseProgress.objects.get_or_create(user=request.user, course=course)[0].progress_percentage,
        'previous_url': None,
        'next_url': None,
        'ask_oras': assessment.ask_oras.all(),
        'user_submissions': Submission.objects.filter(askora__assessment=assessment, user=request.user),
        'askora_submit_status': {
            ao.id: Submission.objects.filter(askora=ao, user=request.user).exists()
            for ao in assessment.ask_oras.all()
        },
        'askora_can_submit': {
            ao.id: (
                not Submission.objects.filter(askora=ao, user=request.user).exists() and
                ao.is_responsive and
                (ao.response_deadline is None or ao.response_deadline > timezone.now())
            ) for ao in assessment.ask_oras.all()
        },
        'can_review': submissions.exists(),
        'submissions': submissions,
        'has_other_submissions': has_other_submissions,  # Tambahan: True jika ada submisi dari pengguna lain
        'is_quiz': assessment.questions.exists(),
        'peer_review_stats': None,
        'show_timer': False,
    }

    # Hitung peer_review_stats jika pengguna punya submisi
    user_submissions = context['user_submissions']
    if user_submissions.exists():
        total_participants = Submission.objects.filter(
            askora__assessment=assessment
        ).values('user').distinct().count()
        user_reviews = PeerReview.objects.filter(
            submission__in=user_submissions
        ).aggregate(
            total_reviews=Count('id'),
            distinct_reviewers=Count('reviewer', distinct=True)
        )
        context['peer_review_stats'] = {
            'total_reviews': user_reviews['total_reviews'] or 0,
            'distinct_reviewers': user_reviews['distinct_reviewers'] or 0,
            'total_participants': total_participants - 1,
            'completed': user_reviews['distinct_reviewers'] >= (total_participants - 1)
        }
        if user_reviews['total_reviews'] > 0:
            avg_score = PeerReview.objects.filter(
                submission__in=user_submissions
            ).aggregate(avg_score=Avg('score'))['avg_score']
            context['peer_review_stats']['avg_score'] = round(avg_score, 2) if avg_score else None

    # Hitung URL navigasi
    if current_index > 0:
        prev = combined_content[current_index - 1]
        context['previous_url'] = reverse('learner:load_content', kwargs={
            'username': request.user.username,
            'id': course.id,
            'slug': course.slug,
            'content_type': prev[0],
            'content_id': prev[1].id
        })
    if current_index < len(combined_content) - 1:
        next_item = combined_content[current_index + 1]
        context['next_url'] = reverse('learner:load_content', kwargs={
            'username': request.user.username,
            'id': course.id,
            'slug': course.slug,
            'content_type': next_item[0],
            'content_id': next_item[1].id
        })

    logger.info(f"submit_peer_review_new: Rendering learner/partials/content.html untuk user {request.user.username}, assessment {assessment.id}")
    response = render(request, 'learner/partials/content.html', context)
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response

@login_required
def learner_detail(request, username):
    """
    Detail learner: menampilkan daftar course, progress, dan ringkasan score.
    Mendukung semua tipe assessment: MCQ (via AssessmentResult), In-Video Quiz, LTI, Askora/Essay.
    """
    user = request.user

    # 🛑 Akses hanya untuk user sendiri
    if username != user.username:
        return HttpResponseForbidden("Access denied.")
    if not getattr(user, 'is_learner', False):
        return HttpResponseForbidden("Access denied: learner only.")

    learner = get_object_or_404(CustomUser, username=username)

    # Ambil semua enrollment dan course-nya sekaligus
    enrollments = Enrollment.objects.filter(user=learner).select_related('course').prefetch_related(
        'course__sections__materials',
        'course__sections__assessments'
    )

    instructor = Instructor.objects.filter(user=learner).first()

    all_courses_data = []
    completed_courses_data = []

    # Helper function untuk hitung score tiap assessment
    def calculate_assessment_score(user, assessment):
        """
        Hitung score per assessment, mendukung:
        - LTIResult
        - In-Video Quiz (QuizResult)
        - MCQ (AssessmentResult)
        - Askora / ORA / Essay (Submission + AssessmentScore)
        """
        score_value = Decimal('0')
        is_submitted = True

        # CASE 1: LTIResult
        lti_result = LTIResult.objects.filter(user=user, assessment=assessment).first()
        if lti_result and lti_result.score is not None:
            lti_score = Decimal(lti_result.score)
            # Jika score > 1, diasumsikan 0-100, ubah ke 0-1
            if lti_score > 1.0:
                lti_score = lti_score / 100
            score_value = lti_score * Decimal(assessment.weight)

        # CASE 2: In-Video Quiz
        elif QuizResult.objects.filter(user=user, assessment=assessment).exists():
            quiz_result = QuizResult.objects.filter(user=user, assessment=assessment).order_by('-created_at').first()
            if quiz_result and quiz_result.total_questions > 0:
                raw_percentage = Decimal(quiz_result.score) / Decimal(quiz_result.total_questions)
                score_value = raw_percentage * Decimal(assessment.weight)
            else:
                is_submitted = False

        # CASE 3: MCQ via AssessmentResult
        elif AssessmentResult.objects.filter(user=user, assessment=assessment).exists():
            mcq_result = AssessmentResult.objects.filter(user=user, assessment=assessment).order_by('-submitted_at').first()
            if mcq_result:
                if mcq_result.total_questions > 0:
                    # Bisa gunakan correct_answers / total_questions
                    raw_percentage = Decimal(mcq_result.correct_answers) / Decimal(mcq_result.total_questions)
                    score_value = raw_percentage * Decimal(assessment.weight)
                else:
                    # fallback: jika score field sudah ada persentase
                    score_value = (Decimal(mcq_result.score) / 100) * Decimal(assessment.weight)
            else:
                is_submitted = False

        # CASE 4: Askora / ORA / Essay
        else:
            submission = Submission.objects.filter(askora__assessment=assessment, user=user).order_by('-submitted_at').first()
            if submission:
                assessment_score = AssessmentScore.objects.filter(submission=submission).first()
                if assessment_score and assessment_score.final_score is not None:
                    score_value = (Decimal(assessment_score.final_score) / Decimal(100)) * Decimal(assessment.weight)
                else:
                    is_submitted = False
            else:
                is_submitted = False

        # Clamp score agar tidak melebihi weight
        score_value = min(score_value, Decimal(assessment.weight))
        return score_value, is_submitted

    # Loop tiap enrollment/course
    for enrollment in enrollments:
        course = enrollment.course

        # Ambil semua materials & assessments untuk course ini
        materials = Material.objects.filter(section__courses=course).distinct()
        assessments = Assessment.objects.filter(section__courses=course).distinct()

        total_materials = materials.count()
        total_assessments = assessments.count()

        # Progress material
        materials_read = MaterialRead.objects.filter(user=learner, material__in=materials).count()
        materials_progress = (materials_read / total_materials * 100) if total_materials > 0 else 0

        # Progress assessment & skor
        assessment_scores = []
        total_score = Decimal('0')
        total_max_score = Decimal('0')
        all_assessments_submitted = True
        assessments_attempted = []

        for assessment in assessments:
            score, is_submitted = calculate_assessment_score(learner, assessment)
            assessment_scores.append({
                'assessment': assessment,
                'score': score,
                'weight': assessment.weight,
                'is_submitted': is_submitted
            })
            total_score += score
            total_max_score += assessment.weight
            if is_submitted:
                assessments_attempted.append(assessment.id)
            else:
                all_assessments_submitted = False

        # Persentase assessment
        assessments_progress = (len(assessments_attempted) / total_assessments * 100) if total_assessments > 0 else 0

        # Rata-rata progress keseluruhan
        progress = (materials_progress + assessments_progress) / 2 if (total_materials + total_assessments) > 0 else 0

        # Simpan ke CourseProgress
        course_progress, _ = CourseProgress.objects.get_or_create(user=learner, course=course)
        course_progress.progress_percentage = progress
        course_progress.save()

        # Ambang kelulusan
        grade_range_pass = GradeRange.objects.filter(course=course, name='Pass').first()
        passing_threshold = grade_range_pass.min_grade if grade_range_pass else Decimal('52.00')

        # Hitung overall percentage
        overall_percentage = (total_score / total_max_score * 100) if total_max_score > 0 else Decimal('0')

        # Tentukan status Pass/Fail
        passing_criteria_met = overall_percentage >= passing_threshold and progress == 100
        status = "Pass" if all_assessments_submitted and passing_criteria_met else "Fail"

        # Tentukan grade letter
        grade_letter = GradeRange.objects.filter(
            course=course,
            min_grade__lte=overall_percentage,
            max_grade__gte=overall_percentage
        ).first()
        grade_letter = grade_letter.name if grade_letter else "N/A"

        # Simpan data course
        course_data = {
            'enrollment': enrollment,
            'course': course,
            'progress': round(progress, 2),
            'overall_percentage': round(overall_percentage, 2),
            'threshold': passing_threshold,
            'total_score': round(total_score, 2),
            'is_completed': status == "Pass",
            'assessments_attempted': assessments_attempted,
            'assessment_scores': assessment_scores,
            'status': status,
            'grade': grade_letter
        }

        all_courses_data.append(course_data)
        if status == "Pass":
            completed_courses_data.append(course_data)

    # Context untuk template
    context = {
        'learner': learner,
        'instructor': instructor,
        'all_courses': all_courses_data,
        'completed_courses': completed_courses_data
    }

    return render(request, 'learner/learner.html', context)

def calculate_assessment_score(user, assessment):
    score_value = Decimal('0')
    is_submitted = True

    # CASE 1: LTIResult
    lti_result = LTIResult.objects.filter(user=user, assessment=assessment).first()
    if lti_result and lti_result.score is not None:
        lti_score = Decimal(lti_result.score)
        if lti_score > 1.0:  # jika nilai 0-100
            lti_score /= 100
        score_value = lti_score * Decimal(assessment.weight)
        

    else:
        # CASE 2: In-Video Quiz
        invideo_quizzes = Quiz.objects.filter(assessment=assessment)
        if invideo_quizzes.exists():
            quiz_result = QuizResult.objects.filter(user=user, assessment=assessment).first()
            if quiz_result and quiz_result.total_questions > 0:
                raw_percentage = Decimal(quiz_result.score) / Decimal(quiz_result.total_questions)
                score_value = raw_percentage * Decimal(assessment.weight)
                
            else:
                score_value = Decimal('0')  # Pastikan quiz kosong tetap 0
                is_submitted = False
                

        else:
            # CASE 3: MCQ (AssessmentResult)
            mcq_result = AssessmentResult.objects.filter(user=user, assessment=assessment).first()
            if mcq_result and mcq_result.total_questions > 0:
                raw_percentage = Decimal(mcq_result.correct_answers) / Decimal(mcq_result.total_questions)
                score_value = raw_percentage * Decimal(assessment.weight)
                
            else:
                # Jika tidak ada submission MCQ
                score_value = Decimal('0')
                is_submitted = False
                

            # CASE 4: Askora (Submission)
            askora_subs = Submission.objects.filter(askora__assessment=assessment, user=user)
            if askora_subs.exists():
                latest_submission = askora_subs.order_by('-submitted_at').first()
                assessment_score = AssessmentScore.objects.filter(submission=latest_submission).first()
                if assessment_score:
                    score_value = Decimal(assessment_score.final_score)
                   
                else:
                    score_value = Decimal('0')
                    is_submitted = False
                   
            else:
                if not mcq_result:
                    score_value = Decimal('0')
                    is_submitted = False
                   

    # Clamp score agar tidak melebihi weight
    score_value = min(score_value, Decimal(assessment.weight))
    
    return score_value, is_submitted

@login_required
def grade_distribution_view(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    sections = course.sections.all()
    assessments = Assessment.objects.filter(section__in=sections).order_by('id')

    enrolled_users = [e.user for e in course.enrollments.select_related('user')]
    table_data = []

    grade_ranges = course.grade_ranges.all()

    # Tentukan passing threshold
    passing_threshold = Decimal('60')  # Default jika tidak ada range grade
    if grade_ranges.exists():
        lowest_range = grade_ranges.first()
        passing_threshold = lowest_range.max_grade + 1

    # Loop untuk setiap user
    for user in enrolled_users:
        scores = {}
        total_score = Decimal('0')
        total_max = Decimal('0')
        all_assessments_submitted = True

        for assessment in assessments:
            # Menggunakan helper function untuk menghitung score per assessment
            score_value, is_submitted = calculate_assessment_score(user, assessment)

           

            scores[assessment.id] = round(score_value, 2)
            total_score += score_value
            total_max += Decimal(assessment.weight)

            # Cek apakah semua assessment sudah disubmit
            if not is_submitted:
                all_assessments_submitted = False

        # Menghitung rata-rata
        average = (total_score / total_max * Decimal('100')) if total_max > 0 else Decimal('0')

        # Menentukan grade berdasarkan rata-rata
        grade_name = '-'
        for gr in grade_ranges:
            if gr.min_grade <= average <= gr.max_grade:
                grade_name = gr.name
                break

        # Simpan ke table_data
        table_data.append({
            'user': user,
            'scores': scores,
            'total_score': round(total_score, 2),
            'total_max': round(total_max, 2),
            'average': round(average, 2),
            'grade': grade_name,
            'status': "Pass" if all_assessments_submitted else "Fail"
        })

    # Sort data berdasarkan rata-rata tertinggi
    table_data.sort(key=lambda x: x['average'], reverse=True)

    context = {
        'course': course,
        'assessments': assessments,
        'table_data': table_data
    }

    return render(request, 'learner/grade_distribution.html', context)