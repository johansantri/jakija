from django import template
import base64
import random
from datetime import datetime
from courses.models import Course,CourseProgress,Assessment,Enrollment,GradeRange,QuestionAnswer  # ✅ Tambahkan ini
from io import BytesIO
from PIL import Image  # Pastikan ini ada
import re
from decimal import Decimal
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def mul(value, arg):
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return ''

@register.filter
def is_course_cert_eligible(course):
    enrollments = Enrollment.objects.filter(course=course)
    total_enrolled = enrollments.count()

    if total_enrolled == 0:
        return False

    total_passed = 0
    assessments = Assessment.objects.filter(section__courses=course).distinct()
    total_max_score = sum(a.weight for a in assessments)

    grade_range = GradeRange.objects.filter(course=course).first()
    passing_threshold = grade_range.min_grade if grade_range else 0

    for enrollment in enrollments:
        user = enrollment.user
        user_score = Decimal(0)
        user_submitted_all_assessments = True

        for assessment in assessments:
            questions = assessment.questions.all()
            total_questions = questions.count()
            has_answered_assessment = True

            for question in questions:
                user_answers = QuestionAnswer.objects.filter(question=question, user=user)
                if not user_answers.exists():
                    has_answered_assessment = False
                    continue

                correct_choices = set(question.choices.filter(is_correct=True).values_list("id", flat=True))
                user_choices = set(user_answers.values_list("choice_id", flat=True))

                if user_choices == correct_choices:
                    user_score += Decimal(assessment.weight) / Decimal(total_questions)

            if not has_answered_assessment:
                user_submitted_all_assessments = False

        progress_obj = CourseProgress.objects.filter(user=user, course=course).first()
        progress = progress_obj.progress_percentage if progress_obj else 0
        percentage = (user_score / total_max_score * 100) if total_max_score > 0 else 0

        is_passed = (
            progress == 100 and
            user_submitted_all_assessments and
            percentage >= passing_threshold
        )

        if is_passed:
            total_passed += 1

    passing_ratio = total_passed / total_enrolled
    return passing_ratio >= 0.4



@register.filter
def make_iframes_responsive(value):
    """
    Bungkus iframe YouTube/Vimeo saja agar responsive.
    Canva iframe biarkan asli supaya tidak blank.
    """
    if not value:
        return value

    pattern = r'(<iframe[^>]*>.*?</iframe>)'

    def wrap_iframe(match):
        iframe_tag = match.group(1)

        # Cek src iframe
        if 'youtube.com' in iframe_tag or 'youtu.be' in iframe_tag or 'vimeo.com' in iframe_tag:
            # Tambahkan class & atribut
            if 'class=' not in iframe_tag:
                iframe_tag = iframe_tag.replace('<iframe', '<iframe class="absolute inset-0 w-full h-full"')
            if 'allowfullscreen' not in iframe_tag:
                iframe_tag = iframe_tag.replace('<iframe', '<iframe allowfullscreen')
            if 'loading=' not in iframe_tag:
                iframe_tag = iframe_tag.replace('<iframe', '<iframe loading="lazy"')
            # Bungkus div responsive
            return f'<div class="relative w-full overflow-hidden rounded-xl shadow-lg" style="padding-top: 56.25%;">{iframe_tag}</div>'
        else:
            # Canva / embed lain → tampilkan apa adanya
            return iframe_tag

    result = re.sub(pattern, wrap_iframe, value, flags=re.IGNORECASE | re.DOTALL)
    return mark_safe(result)



@register.filter
def get_item(dictionary, key):
    """Filter untuk mengambil nilai dari dictionary berdasarkan key"""
    return dictionary.get(key)

@register.filter
def randomize(queryset):
    """Mengacak urutan elemen dalam list atau queryset"""
    items = list(queryset)  # pastikan queryset diubah menjadi list
    random.shuffle(items)
    return items

@register.filter
def split(value, delimiter=","):
    """Memisahkan string berdasarkan delimiter."""
    return value.split(delimiter)

@register.filter
def mask_phone(value):
    """
    Menyembunyikan semua angka kecuali 4 angka terakhir.
    """
    if not value or len(value) < 4:
        return '****'
    return '*' * (len(value) - 4) + value[-4:]

@register.filter
def mask_year(date_value):
    """
    Menampilkan bulan dan tanggal, menyembunyikan tahun (diganti ****).
    Bisa terima date object atau string.
    """
    if not date_value:
        return ''
    
    # Coba parsing kalau berupa string
    if isinstance(date_value, str):
        try:
            date_value = datetime.strptime(date_value, '%Y-%m-%d')
        except ValueError:
            return 'Invalid date'

    return date_value.strftime('%b %d, ****')


#untuk filter course bahasa
@register.filter
def get_language_name(language_code):
    """Mengembalikan nama bahasa berdasarkan kode bahasa."""
    choice_language = dict(Course.choice_language)
    return choice_language.get(language_code, language_code)  # Mengembalikan kode bahasa jika tidak ditemukan
#dan juga ini
@register.filter
def dict_get(dictionary, key):
    return dictionary.get(key, '')

@register.filter(name='add_class')
def add_class(value, class_name):
    return value.as_widget(attrs={'class': class_name})

@register.filter
def to(value):
    """Returns a range from 1 to the given value."""
    return range(1, value + 1)

@register.filter
def base64encode(value):
    """
    Mengonversi gambar menjadi string base64.
    Pastikan `value` adalah objek gambar PIL (Pillow).
    """
    if isinstance(value, Image.Image):
        buffer = BytesIO()
        value.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode('utf-8')
    return value