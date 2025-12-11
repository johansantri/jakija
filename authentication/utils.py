from decimal import Decimal, ROUND_HALF_UP
from courses.models import (
    Assessment, QuestionAnswer, GradeRange,
    LTIResult, CourseProgress, Quiz, QuizResult,Submission, AssessmentScore
)
from django.core.cache import cache
import datetime

import requests

def calculate_course_status(user, course):
    total_score = Decimal('0')
    total_max_score = Decimal('0')
    all_assessments_submitted = True

    # --- Ambil passing threshold yang benar ---
    grade_ranges = GradeRange.objects.filter(course=course)
    if grade_ranges.exists():
        grade_fail = grade_ranges.order_by('max_grade').first()
        passing_threshold = grade_fail.max_grade + 1 if grade_fail else Decimal('60')
    else:
        passing_threshold = Decimal('60')  # fallback default

    # --- Loop assessments ---
    assessments = Assessment.objects.filter(section__courses=course)
    for assessment in assessments:
        score_value = Decimal('0')
        is_submitted = True
        weight = Decimal(assessment.weight)

        # === CASE 1: LTI RESULT ===
        lti_result = LTIResult.objects.filter(user=user, assessment=assessment).first()
        if lti_result and lti_result.score is not None:
            lti_score = Decimal(lti_result.score)
            if lti_score > 1:
                lti_score = lti_score / 100  # Normalisasi jika skor 0–100
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
                # === CASE 3: OLD QUESTION MODEL (Multiple Choice) ===
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
                        askora__assessment=assessment,
                        user=user
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

        # Batas nilai ke bobot
        score_value = min(score_value, weight)

        total_score += score_value
        total_max_score += weight


    # Normalisasi total skor
    total_score = min(total_score, total_max_score)
    overall_percentage = (total_score / total_max_score * 100) if total_max_score > 0 else Decimal('0')

    # Bulatkan
    total_score = total_score.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total_max_score = total_max_score.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    overall_percentage = overall_percentage.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # --- Ambil progress user ---
    course_progress = CourseProgress.objects.filter(user=user, course=course).first()
    progress_percentage = Decimal(course_progress.progress_percentage) if course_progress else Decimal('0')
    progress_percentage = progress_percentage.quantize(Decimal("0.01"))

    # --- Tentukan status kelulusan ---
    passing_criteria_met = (overall_percentage >= passing_threshold and progress_percentage == 100)
    status = "Pass" if all_assessments_submitted and passing_criteria_met else "Fail"

    return {
        'course_name': course.course_name,
        'total_score': total_score,
        'total_max_score': total_max_score,
        'status': status,
        'progress_percentage': progress_percentage,
        'overall_percentage': overall_percentage,
        'passing_threshold': passing_threshold.quantize(Decimal("0.01")),
    }




def is_user_online(user):
    if not hasattr(user, 'id'):
        return False  # jika bukan user object, anggap offline

    last_seen = cache.get(f'seen_{user.id}')
    if last_seen:
        now = datetime.datetime.now()
        if (now - last_seen).total_seconds() < 300:
            return True
    return False


def get_total_online_users(users):
    total_online = 0
    for user in users:
        if is_user_online(user):
            total_online += 1
    return total_online



def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def get_geo_from_ip(ip):
    try:
        response = requests.get(f"https://ipinfo.io/{ip}/json")
        if response.status_code == 200:
            data = response.json()
            return {
                "city": data.get("city"),
                "country": data.get("country"),
                "isp": data.get("org"),
                "lat": None,  # Kalau ada data latitude, bisa kamu parse juga
                "lon": None,
            }
    except Exception:
        pass
    return None
