# utils.py
from decimal import Decimal
from django.core.exceptions import ValidationError  # Add this import
from .models import Quiz,QuizResult,LTIResult,Assessment, GradeRange, QuestionAnswer, Submission, AssessmentScore,BlacklistedKeyword
from django.core.cache import cache
from django.utils.timezone import now
from datetime import timedelta
import uuid
from datetime import datetime, timezone
import urllib.parse
import hashlib
import hmac
import base64

def generate_nonce(request):
    nonce = uuid.uuid4().hex
    request.session['lti_nonce'] = nonce
    request.session['lti_nonce_timestamp'] = datetime.now(timezone.utc).timestamp()  # ✅ UTC benar
    return nonce

def user_has_passed_course(user, course):
    """
    Mengecek apakah user telah menyelesaikan course dan melewati passing threshold.
    Mendukung: LTIResult, Quiz (video), QuestionAnswer lama, Submission/ORA
    """
    assessments = Assessment.objects.filter(section__courses=course).distinct()
    grade_range = GradeRange.objects.filter(course=course, name='Pass').first()
    passing_threshold = grade_range.min_grade if grade_range else Decimal('52.00')

    total_max_score = Decimal('0')
    total_score = Decimal('0')
    all_submitted = True

    for assessment in assessments:
        score = Decimal('0')
        weight = Decimal(assessment.weight or 1)

        # 1️⃣ Cek LTIResult
        lti_results = LTIResult.objects.filter(user=user, assessment=assessment, score__isnull=False)
        if lti_results.exists():
            lti_score = Decimal(lti_results.order_by('-id').first().score)
            if lti_score > 1:  # normalisasi jika 0-100
                lti_score = lti_score / 100
            score = min(lti_score * weight, weight)
            total_max_score += weight
            total_score += score
            continue

        # 2️⃣ Cek Video Quiz
        quizzes = Quiz.objects.filter(assessment=assessment).distinct()
        if quizzes.exists():
            quiz_results = QuizResult.objects.filter(user=user, assessment=assessment)
            if not quiz_results.exists():
                all_submitted = False
                total_max_score += weight
                continue

            # Hitung persentase benar dari semua quiz
            quiz_score_total = Decimal('0')
            for quiz in quizzes:
                result = quiz_results.filter(video=quiz.video).first()
                if result:
                    quiz_score_total += Decimal(result.score) / Decimal(result.total_questions) * weight
            score = min(quiz_score_total, weight)
            total_max_score += weight
            total_score += score
            continue

        # 3️⃣ Cek QuestionAnswer lama (MC, TF, FB, dsb.)
        total_questions = assessment.questions.count()
        if total_questions > 0:
            user_answers = QuestionAnswer.objects.filter(user=user, question__assessment=assessment)
            if not user_answers.exists():
                all_submitted = False
                total_max_score += weight
                continue

            correct_answers = 0
            for question in assessment.questions.all():
                user_q_answers = user_answers.filter(question=question)
                correct_answers += sum(1 for qa in user_q_answers if qa.choice.is_correct)

            score = (Decimal(correct_answers) / Decimal(total_questions)) * weight
            score = min(score, weight)
            total_max_score += weight
            total_score += score
            continue

        # 4️⃣ Cek ORA / Submission + AssessmentScore
        submission = Submission.objects.filter(user=user, askora__assessment=assessment).order_by('-submitted_at').first()
        if not submission:
            all_submitted = False
            total_max_score += weight
            continue

        assessment_score = AssessmentScore.objects.filter(submission=submission).first()
        if not assessment_score or assessment_score.final_score is None:
            all_submitted = False
            total_max_score += weight
            continue

        score = min(Decimal(assessment_score.final_score), weight)
        total_max_score += weight
        total_score += score

    if total_max_score == 0:
        return False

    final_percentage = (total_score / total_max_score) * 100
    return all_submitted and final_percentage >= passing_threshold



def check_for_blacklisted_keywords(comment):
    blacklisted_keywords = BlacklistedKeyword.objects.all()
    
    for keyword in blacklisted_keywords:
        if keyword.keyword.lower() in comment.lower():
            return keyword.keyword  # Return kata yang dilanggar

    return None


def is_suspicious(request, threshold=5, time_window=60):
    """
    Detect suspicious activity based on request rate limiting.
    - `threshold`: The maximum number of requests allowed within `time_window` seconds.
    - `time_window`: The time window in seconds to check for frequent requests.
    """
    # Use the user IP or session key to track requests (session is a fallback for anonymous users)
    user_identifier = request.user.id if request.user.is_authenticated else request.session.session_key
    if not user_identifier:
        return False  # If no identifier is found, assume it's not suspicious
    
    # Cache key to track requests
    cache_key = f'user_activity_{user_identifier}'
    
    # Get the timestamp of the first request in this time window (cached)
    first_request_time = cache.get(cache_key)
    
    if not first_request_time:
        # If no first request time is found, store the current time
        cache.set(cache_key, now(), timeout=time_window)
        return False  # Not suspicious yet (first request)
    
    # If a request has occurred within the time window (e.g., 60 seconds)
    if (now() - first_request_time) < timedelta(seconds=time_window):
        # If they exceeded the threshold, mark it as suspicious
        request_count = cache.get(f'{cache_key}_count', 0) + 1
        cache.set(f'{cache_key}_count', request_count, timeout=time_window)
        
        if request_count > threshold:
            return True  # Suspicious if requests exceed the threshold
    else:
        # Reset the counter and the first request time if the time window has passed
        cache.set(cache_key, now(), timeout=time_window)
        cache.set(f'{cache_key}_count', 1, timeout=time_window)
    
    return False

#ambil ip client untuk di simpan di log
def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0]
    return request.META.get('REMOTE_ADDR')




def oauth_encode(value: str) -> str:
    """Percent-encode sesuai OAuth 1.0a (RFC 5849)."""
    return urllib.parse.quote(str(value), safe='~-._')


def generate_oauth_signature(params, consumer_secret, launch_url, http_method="POST"):
    """
    Generate OAuth 1.0 HMAC-SHA1 signature for LTI 1.1.
    """

    # Pisahkan URL dari query string
    parsed = urllib.parse.urlparse(launch_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    # Tambahkan query string ke params (kalau ada)
    query_params = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    for k, v in query_params:
        params[k] = v

    # Step 1: Encode semua params, exclude oauth_signature
    encoded_params = [(oauth_encode(k), oauth_encode(v))
                      for k, v in params.items() if k != "oauth_signature"]

    # Step 2: Sort alfabetis by key, lalu value
    encoded_params.sort()

    # Step 3: Param string
    param_str = "&".join([f"{k}={v}" for k, v in encoded_params])

    # Step 4: Base string (HTTP_METHOD&base_url&params)
    base_elems = [
        http_method.upper(),
        oauth_encode(base_url),
        oauth_encode(param_str),
    ]
    base_string = "&".join(base_elems)

    # Step 5: Signing key
    signing_key = f"{oauth_encode(consumer_secret)}&"

    # Step 6: HMAC-SHA1 + Base64
    hashed = hmac.new(signing_key.encode("utf-8"),
                      base_string.encode("utf-8"),
                      hashlib.sha1)
    signature = base64.b64encode(hashed.digest()).decode()

    return signature
