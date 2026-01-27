# instructor/utils.py
import os
from django.template.loader import render_to_string
from weasyprint import HTML
from django.conf import settings
from decimal import Decimal
from courses.models import CourseChecklistItem
from django.utils import timezone
import re

def generate_certificate_file(context, output_filename):
    html_string = render_to_string("instructor/certificate_template.html", context)
    output_path = os.path.join(settings.MEDIA_ROOT, "certificates", output_filename)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    HTML(string=html_string).write_pdf(output_path)
    return output_path



#cout text words
def word_count(text):
    if not text:
        return 0
    return len(re.findall(r'\b\w+\b', text))
# =================================================
# ASSESSMENT VALIDATOR
# =================================================
def validate_assessment(assessment, unit_title):
    errors = []
    has_activity = False

    # =====================
    # MULTIPLE CHOICE KLASIK
    # =====================
    if assessment.questions.exists():
        has_activity = True

        if assessment.duration_in_minutes is None:
            errors.append("belum di-set durasi")

        for q in assessment.questions.all():
            if not q.text:
                errors.append("ada soal tanpa teks")

            choices = q.choices.all()
            if choices.count() < 2:
                errors.append("ada soal dengan pilihan kurang dari 2")
            elif not choices.filter(is_correct=True).exists():
                errors.append("ada soal tanpa jawaban benar")

    # =====================
    # ORA
    # =====================
    if assessment.ask_oras.exists():
        has_activity = True
        for ora in assessment.ask_oras.all():
            if not ora.question_text:
                errors.append("ORA tanpa pertanyaan")
            if ora.response_deadline <= timezone.now():
                errors.append("deadline ORA sudah lewat")

    # =====================
    # LTI
    # =====================
    if hasattr(assessment, "lti_tool"):
        has_activity = True
        lti = assessment.lti_tool
        if not all([
            lti.tool_name,
            lti.launch_url,
            lti.consumer_key,
            lti.shared_secret
        ]):
            errors.append("konfigurasi LTI belum lengkap")

    # =====================
    # VIDEO QUIZ
    # =====================
    if assessment.quizzes.exists():
        has_activity = True
        for quiz in assessment.quizzes.all():
            if quiz.time_in_video is None or quiz.time_in_video < 0:
                errors.append("video quiz tanpa timestamp")

            if quiz.question_type in ['MC', 'DD']:
                options = quiz.options.all()
                if options.count() < 2:
                    errors.append("video quiz MC tanpa opsi cukup")
                elif not options.filter(is_correct=True).exists():
                    errors.append("video quiz MC tanpa jawaban benar")
            else:
                if not quiz.correct_answer_text:
                    errors.append("video quiz tanpa jawaban benar")

    # =====================
    # EMPTY ASSESSMENT
    # =====================
    if not has_activity:
        errors.append(
            "assessment belum punya aktivitas (MC / ORA / LTI / Video Quiz)"
        )

    if errors:
        return (
            f"Assessment '{assessment.name}' di unit '{unit_title}': "
            + ", ".join(sorted(set(errors)))
        )

    return None



# =================================================
# COURSE CHECKLIST
# =================================================
def generate_course_checklist(course):
    checklist = []

    # ---------- BASIC INFO ----------
    if not course.course_name:
        checklist.append("Course name is not filled")

    # Validate description
    desc_words = word_count(course.description)
    if not course.description:
        checklist.append("Course description is not filled")
    elif desc_words < 500:
        checklist.append(f"Course description is too short ({desc_words} words). Minimum 500 words required")
    elif desc_words > 3000:
        checklist.append(f"Course description is too long ({desc_words} words). Maximum 3000 words allowed")

    # Short description
    if not course.sort_description:
        checklist.append("Short description is not filled")
    elif len(course.sort_description) < 50:
        checklist.append("Short description must be at least 50 characters")
    elif len(course.sort_description) > 150:
        checklist.append("Short description must not exceed 150 characters")

    if not course.language:
        checklist.append("Language is not selected")
    if not course.category:
        checklist.append("Category is not selected")
    if not course.instructor:
        checklist.append("Instructor is not assigned")
    if not course.level:
        checklist.append("Course level is not set")
    if not course.hour:
        checklist.append("Estimated course duration (hours) is not set")
    if not course.image:
        checklist.append("Course cover image is not uploaded")
    if not course.link_video:
        checklist.append("Course intro video is not provided")

    # ---------- SECTION TREE ----------
    sections = course.sections.all()
    if not sections.exists():
        checklist.append("At least 1 section must be created")
        return finalize_checklist(checklist)

    unit_sections = [s for s in sections if not s.children.exists()]
    if not unit_sections:
        checklist.append("No learning unit found (bottom-level section)")
        return finalize_checklist(checklist)

    # ---------- UNIT ----------
    for unit in unit_sections:
        materials = unit.materials.all()
        assessments = unit.assessments.all()

        if not materials.exists() and not assessments.exists():
            checklist.append(f"Unit '{unit.title}' has no materials or assessments")

        for mat in materials:
            if not mat.description:
                checklist.append(f"Material '{mat.title}' in unit '{unit.title}' has no description")

        total_weight = Decimal(0)
        for ass in assessments:
            total_weight += ass.weight or 0
            error = validate_assessment(ass, unit.title)
            if error:
                checklist.append(error)

        if total_weight > 100:
            checklist.append(f"Total assessment weight in unit '{unit.title}' exceeds 100")

    # ---------- GRADE ----------
    if sections.filter(assessments__isnull=False).exists() and not course.grade_ranges.exists():
        checklist.append("Courses with assessments must have grade ranges")

    # ---------- DATE & PAYMENT ----------
    if not course.start_date or not course.end_date:
        checklist.append("Course must have a start and end date")
    elif course.start_date > course.end_date:
        checklist.append("Start date cannot be after end date")

    if course.start_enrol and course.end_enrol and course.start_enrol > course.end_enrol:
        checklist.append("Enrollment start date cannot be after enrollment end date")

    if course.payment_model and course.payment_model != 'free' and not course.prices.exists():
        checklist.append("Paid courses must have pricing information")

    return finalize_checklist(checklist)


# =================================================
# FINALIZER
# =================================================
def finalize_checklist(checklist):
    readiness = max(100 - len(checklist) * 10, 0)
    return {
        "checklist": checklist,
        "readiness_percentage": readiness
    }


# =================================================
# SAVE TO DB
# =================================================
def update_course_checklist_db(course):
    result = generate_course_checklist(course)

    course.checklist_items.all().delete()

    CourseChecklistItem.objects.bulk_create([
        CourseChecklistItem(course=course, message=msg)
        for msg in result['checklist']
    ])

    course.readiness_percentage = result['readiness_percentage']
    course.save(update_fields=['readiness_percentage'])
    data = generate_course_checklist(course)
    checklist = data['checklist']
    readiness = data['readiness_percentage']

    # Hapus lama & simpan baru
    course.checklist_items.all().delete()
    CourseChecklistItem.objects.bulk_create([
        CourseChecklistItem(course=course, message=msg) for msg in checklist
    ])

    # Update readiness
    course.readiness_percentage = readiness
    course.save(update_fields=['readiness_percentage'])