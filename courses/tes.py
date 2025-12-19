import random
from datetime import date
from faker import Faker
from io import BytesIO
from PIL import Image

from django.core.files.base import ContentFile
from courses.models import (
    Course, Partner, Instructor, Category,
    CourseStatus, PricingType,
    Section, Material, GradeRange, Assessment, Question, Choice
)
from authentication.models import CustomUser

fake = Faker()

# ==========================
# PRELOAD DATA
# ==========================
partners = list(Partner.objects.all())
instructors = list(Instructor.objects.all())
categories = list(Category.objects.all())
users = list(CustomUser.objects.all())
pricing_types = list(PricingType.objects.all())
languages = [lang[0] for lang in Course.choice_language]
levels = ['basic', 'middle', 'advanced']

publish_status = CourseStatus.objects.filter(status__iexact='published').first()
if not publish_status:
    raise Exception("❌ Status 'published' tidak ditemukan di CourseStatus")

today = date.today()
end_fixed = date(2026, 12, 26)

# ==========================
# DUMMY IMAGE GENERATOR
# ==========================
def generate_dummy_image():
    img = Image.new(
        'RGB',
        (400, 250),
        color=(
            random.randint(0, 255),
            random.randint(0, 255),
            random.randint(0, 255)
        )
    )
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    return ContentFile(buffer.getvalue(), f"{fake.word()}.png")

# ==========================
# GENERIC COURSE TITLE
# ==========================
def generate_course_title():
    subjects = ["Public Speaking", "Python Programming", "Time Management", "Digital Marketing", "Photography"]
    levels = ["Pengenalan", "Dasar-dasar", "Teknik Lanjutan", "Masterclass", "Workshop"]
    return f"{random.choice(levels)} {random.choice(subjects)}"

# ==========================
# CREATE COURSES
# python manage.py shell < courses/tes.py

# ==========================
TOTAL_COURSES = 5

for i in range(TOTAL_COURSES):
    course_name = generate_course_title()
    course = Course.objects.create(
        course_name=course_name,
        course_number=str(fake.random_number(digits=5)),
        course_run=str(fake.random_number(digits=3)),
        slug=fake.slug(),
        org_partner=random.choice(partners) if partners else None,
        instructor=random.choice(instructors) if instructors else None,
        category=random.choice(categories) if categories else None,
        level=random.choice(levels),
        status_course=publish_status,
        description=" ".join([fake.paragraph(nb_sentences=7) for _ in range(8)]),
        sort_description = " ".join([fake.paragraph(nb_sentences=7) for _ in range(2)]),

        hour=str(random.randint(1, 10)),
        author=random.choice(users) if users else None,
        language=random.choice(languages),
        start_date=today,
        end_date=end_fixed,
        start_enrol=today,
        end_enrol=end_fixed,
        payment_model=random.choice(pricing_types) if pricing_types else None,
        image=generate_dummy_image()
        
    )

    # ==========================
    # GRADE RANGE
    # ==========================
    GradeRange.objects.bulk_create([
        GradeRange(course=course, name="Tidak Lulus", min_grade=0, max_grade=59.99),
        GradeRange(course=course, name="Lulus", min_grade=60, max_grade=100),
    ])
    grade_ranges = list(course.grade_ranges.all())

    # ==========================
    # SECTIONS → SUBSECTIONS → UNITS
    # ==========================
    assessments_to_create = []

    # Topik section sesuai topik course
    section_topics = [f"Pendahuluan {course_name}", f"Materi Inti {course_name}", f"Praktik {course_name}"]
    for s_idx, section_topic in enumerate(section_topics, 1):
        section = Section.objects.create(
            title=section_topic,
            courses=course,
            order=s_idx
        )

        # Subsections: contoh generik
        subsection_topics = [f"Teori {section_topic}", f"Latihan {section_topic}"]
        for ss_idx, sub_topic in enumerate(subsection_topics, 1):
            subsection = Section.objects.create(
                title=sub_topic,
                parent=section,
                courses=course,
                order=ss_idx
            )

            # Units: contoh generik
            unit_topics = [f"Unit {i} {sub_topic}" for i in range(1, 3)]
            for u_idx, unit_topic in enumerate(unit_topics, 1):
                unit = Section.objects.create(
                    title=unit_topic,
                    parent=subsection,
                    courses=course,
                    order=u_idx
                )

                # Materials
                for m_idx in range(1, 4):
                    Material.objects.create(
                        section=unit,
                        title=f"{unit_topic} – Materi {m_idx}",
                        description=f"Deskripsi materi {m_idx} dari {unit_topic}. " +
                                    " ".join([fake.paragraph(nb_sentences=5) for _ in range(3)])
                    )

                # Assessments
                num_assessments = 1
                for a in range(num_assessments):
                    assessments_to_create.append({
                        "unit": unit,
                        "name": f"Quiz {unit_topic} – {a+1}"
                    })

    # ==========================
    # BAGI BOBOT 100%
    # ==========================
    total_assessments = len(assessments_to_create)
    if total_assessments > 0:
        weight_per_assessment = round(100 / total_assessments, 2)
        cumulative_weight = 0
        for idx, data in enumerate(assessments_to_create):
            if idx == total_assessments - 1:
                weight = round(100 - cumulative_weight, 2)
            else:
                weight = weight_per_assessment
                cumulative_weight += weight

            assessment = Assessment.objects.create(
                section=data["unit"],
                name=data["name"],
                duration_in_minutes=random.choice([10, 15, 30]),
                weight=weight,
                grade_range=random.choice(grade_ranges) if grade_ranges else None
            )

            # Questions & Choices
            for q in range(1, 6):
                question = Question.objects.create(
                    assessment=assessment,
                    text=f"Pertanyaan {q} untuk {data['name']}"
                )
                correct_index = random.randint(0, 3)
                for c in range(4):
                    Choice.objects.create(
                        question=question,
                        text=f"Pilihan {c+1} untuk pertanyaan {q}",
                        is_correct=(c == correct_index)
                    )

    print(f"✅ Course '{course_name}' selesai dibuat")

print("🎉 Semua course selesai dibuat!")
