from django import template
from django.db.models import Count
from django.urls import reverse
from courses.models import PeerReview, LTIResult,Submission,Course, Section, Material, Assessment,MaterialRead, AssessmentRead, QuestionAnswer, Submission, AssessmentScore, GradeRange, CourseProgress
import random
import re
from decimal import Decimal
from django.urls import reverse
from decimal import Decimal, ROUND_HALF_UP
import logging
from django.db import models  # Tambah import ini untuk Prefetch
from django.db.models import Prefetch  # Import Prefetch secara eksplisit
from django.utils.safestring import mark_safe

register = template.Library()
@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)

@register.filter
def split_by_equal(value):
    """Split string by '=' and return list."""
    return value.split('=')

@register.filter
def split(value, key):
    return value.split(key)

@register.filter
def split_lines(value):
    return value.strip().splitlines()

@register.filter
def linepartition(value, separator="="):
    """Split string into (before, sep, after) like Python's str.partition()"""
    return value.partition(separator)

@register.filter
def make_iframes_responsive(value):
    """
    Membungkus semua <iframe> (YouTube, Vimeo, dll) dengan div responsive Tailwind
    """
    if not value:
        return value

    # Pattern yang lebih kuat & aman
    pattern = r'(<iframe[^>]*>)(.*?)(</iframe>)'
    
    def replace_match(match):
        iframe_tag = match.group(0)
        # Tambah atribut yang sering hilang (biar aman)
        iframe_tag = iframe_tag.replace('<iframe', '<iframe class="w-full h-full" allowfullscreen ')
        # Bungkus dengan div aspect ratio Tailwind
        return f'<div class="relative w-full overflow-hidden rounded-lg shadow-lg" style="padding-top: 56.25%;">{iframe_tag}</div><div class="absolute inset-0">{iframe_tag}</div></div>'  # salah, coba yang benar:

    # Cara yang benar & paling simpel (rekomendasi)
    replacement = (
        '<div class="relative w-full overflow-hidden rounded-xl shadow-lg" style="padding-top: 56.25%;">'
        '<iframe class="absolute inset-0 w-full h-full" \\1 allowfullscreen loading="lazy"></iframe>'
        '</div>'
    )
    
    result = re.sub(pattern, replacement, value, flags=re.IGNORECASE | re.DOTALL)
    return mark_safe(result)

@register.filter
def shuffled(value):
    result = list(value)
    random.shuffle(result)
    return result

@register.filter
def dict_get(dictionary, key):
    """
    Safely get a value from a dictionary using a key.
    Returns None if the key doesn't exist.
    """
    return dictionary.get(key)

@register.filter
def get_question_answer(dictionary, question_id):
    """
    Get the answer object for a given question ID from the answered_questions dictionary.
    Returns None if no answer exists.
    """
    return dictionary.get(question_id)


@register.filter
def dict_get(dictionary, key):
    return dictionary.get(key)


@register.filter
def dict_get(d, key):
    return d.get(key)


@register.filter
def subtract(value, arg):
    return value - arg

@register.simple_tag
def get_review_progress(submission):
    total_participants = Submission.objects.filter(
        askora__assessment=submission.askora.assessment
    ).values('user').distinct().count()
    
    reviews_received = PeerReview.objects.filter(
        submission=submission
    ).aggregate(
        count=Count('id'),
        reviewers=Count('reviewer', distinct=True)
    )
    
    return {
        'received': reviews_received['count'] or 0,
        'reviewers': reviews_received['reviewers'] or 0,
        'total': total_participants - 1,  # exclude submitter
        'completed': reviews_received['reviewers'] >= (total_participants - 1)
    }


@register.filter
def mul(value, arg):
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return ''
    
logger = logging.getLogger(__name__)


@register.simple_tag(takes_context=True)
def get_course_completion_status(context):
    request = context['request']
    user = request.user
    course = context.get('course')

    if not course:
        logger.warning("No course provided in get_course_completion_status")
        return {
            'is_completed': False,
            'certificate_url': None,
            'assessments_completed_percentage': 0,
            'course_progress': 0,
            'overall_percentage': 0,
            'passing_threshold': 60
        }

    # Ambil passing threshold dari GradeRange (konsisten dengan view: Fail max +1)
    grade_ranges = GradeRange.objects.filter(course=course)
    if grade_ranges.exists():
        grade_fail = grade_ranges.order_by('max_grade').first()
        passing_threshold = Decimal(grade_fail.max_grade + 1) if grade_fail else Decimal('60')
    else:
        passing_threshold = Decimal('60')  # fallback default

    # Ambil course_progress dari DB
    course_progress_obj = CourseProgress.objects.filter(user=user, course=course).first()
    course_progress = Decimal(course_progress_obj.progress_percentage if course_progress_obj else 0)
    course_progress = course_progress.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Prefetch assessments untuk performa (fix: gunakan 'ltiresult_set' untuk reverse relation)
    assessments = Assessment.objects.filter(section__courses=course).prefetch_related(
        Prefetch('questions'),
        Prefetch(
            'ltiresult_set',  # Fix: nama reverse relation dari LTIResult ke Assessment
            queryset=LTIResult.objects.filter(user=user, score__isnull=False),
            to_attr='lti_results'
        )
    )

    total_assessments = assessments.count()
    assessments_completed = 0
    total_score = Decimal(0)
    total_max_score = Decimal(0)
    all_assessments_submitted = True

    for assessment in assessments:
        score_value = Decimal(0)
        weight = Decimal(assessment.weight or 1)
        is_submitted = True

        # Cek LTI (dari prefetch, to_attr='lti_results' sebagai list)
        lti_results = getattr(assessment, 'lti_results', [])
        if lti_results:
            lti_result = lti_results[0]  # Ambil yang pertama (atau order_by('-id').first() jika perlu latest)
            lti_score = Decimal(lti_result.score)
            if lti_score > 1:  # Normalisasi jika 0-100
                logger.warning(f"LTI score {lti_score} > 1.0 for user {user.id}, assessment {assessment.id}, normalizing to {lti_score / 100}")
                lti_score = lti_score / Decimal(100)
            score_value = min(lti_score * weight, weight)
            assessments_completed += 1
            logger.debug(f"LTI: normalized_score={lti_score}, score_value={score_value}")
        elif assessment.questions.exists():  # Quiz
            has_answers = QuestionAnswer.objects.filter(
                user=user, question__assessment=assessment
            ).exists()
            if not has_answers:
                is_submitted = False
                all_assessments_submitted = False
                continue

            total_questions = assessment.questions.count()
            correct_answers = QuestionAnswer.objects.filter(
                user=user,
                question__assessment=assessment,
                choice__is_correct=True
            ).count()
            assessments_completed += 1
            score_value = (Decimal(correct_answers) / Decimal(total_questions)) * weight if total_questions > 0 else Decimal(0)
            logger.debug(f"Quiz: correct={correct_answers}/{total_questions}, score_value={score_value}")
        else:  # ORA
            submission = Submission.objects.filter(
                user=user, askora__assessment=assessment
            ).order_by('-submitted_at').first()
            if not submission:
                is_submitted = False
                all_assessments_submitted = False
                continue

            score_obj = AssessmentScore.objects.filter(submission=submission).first()
            if not score_obj:
                is_submitted = False
                all_assessments_submitted = False
                continue

            assessments_completed += 1
            score_value = Decimal(score_obj.final_score)
            logger.debug(f"ORA: score={score_value}")

        total_score += score_value
        total_max_score += weight

    # Batasi total_score <= total_max_score
    total_score = min(total_score, total_max_score)

    # Hitung persentase
    overall_percentage = (total_score / total_max_score * Decimal(100)) if total_max_score > 0 else Decimal(0)
    overall_percentage = overall_percentage.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    assessments_completed_percentage = (
        (Decimal(assessments_completed) / Decimal(total_assessments) * 100) if total_assessments > 0 else Decimal(0)
    )
    assessments_completed_percentage = assessments_completed_percentage.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Evaluasi kelulusan (strict: progress == 100)
    passing_criteria_met = overall_percentage >= passing_threshold and course_progress == Decimal(100)
    is_completed = all_assessments_submitted and passing_criteria_met

    certificate_url = (
        reverse('courses:generate_certificate', kwargs={'course_id': course.id})
        if is_completed else None
    )

    logger.info(f"Completion for user {user.id}, course {course.id}: "
                f"is_completed={is_completed}, assessments={assessments_completed}/{total_assessments}, "
                f"overall={overall_percentage}%, threshold={passing_threshold}, progress={course_progress}%")

    return {
        'is_completed': is_completed,
        'certificate_url': certificate_url,
        'assessments_completed_percentage': float(assessments_completed_percentage),  # Convert ke float untuk template
        'course_progress': float(course_progress),
        'overall_percentage': float(overall_percentage),
        'passing_threshold': float(passing_threshold)
    }
    
@register.simple_tag(takes_context=True)
def is_content_read(context, content_type, content_id):
    """
    Check if a material or assessment has been read/opened or completed by the user.
    
    Args:
        context: Template context (includes request).
        content_type: 'material' or 'assessment'.
        content_id: ID of the material or assessment.
    
    Returns:
        bool: True if content is read/opened or completed, False otherwise.
    """
    user = context['request'].user
    if not user.is_authenticated:
        return False
    if content_type == 'material':
        return MaterialRead.objects.filter(user=user, material_id=content_id).exists()
    elif content_type == 'assessment':
        # Cek LTIResult untuk assessment LTI
        if LTIResult.objects.filter(user=user, assessment_id=content_id, score__isnull=False).exists():
            #logger.debug(f"LTIResult found for user {user.id}, assessment {content_id}")
            return True
        # Cek QuestionAnswer untuk kuis
        if QuestionAnswer.objects.filter(user=user, question__assessment_id=content_id).exists():
            #logger.debug(f"QuestionAnswer found for user {user.id}, assessment {content_id}")
            return True
        # Cek Submission untuk ORA
        if Submission.objects.filter(user=user, askora__assessment_id=content_id).exists():
            #logger.debug(f"Submission found for user {user.id}, assessment {content_id}")
            return True
        # Fallback ke AssessmentRead untuk menandai bahwa assessment telah dibuka
        assessment_read = AssessmentRead.objects.filter(user=user, assessment_id=content_id).exists()
        #logger.debug(f"AssessmentRead for user {user.id}, assessment {content_id}: {assessment_read}")
        return assessment_read
    return False