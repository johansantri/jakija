from django.shortcuts import render, redirect
from django.shortcuts import render, redirect,get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.core.paginator import Paginator
from django.db.models import Prefetch
import csv
from django.core.mail import send_mail
from decimal import Decimal
from django.contrib import messages
from courses.models import Partner,Quiz,QuizResult,LTIResult,InstructorCertificate,Course,CoursePrice,PricingType, Enrollment,Section,GradeRange,CourseStatusHistory,QuestionAnswer, CourseProgress, PeerReview,MaterialRead, AssessmentRead, AssessmentScore,Material,Assessment, Submission, CustomUser, Instructor
from authentication.models import CustomUser, Universiti
# Create your views here.
from django.template.loader import render_to_string
from weasyprint import HTML
from django.core.files.base import ContentFile
from django.utils.timezone import now
from django.db.models import Count
from decimal import Decimal
import qrcode
import base64
from io import BytesIO
from django.urls import reverse
import os
import uuid  # ✅ Tambahkan ini
import logging
from .utils import generate_course_checklist
from io import BytesIO
from django.conf import settings
import qrcode
import base64
from django.utils import timezone

def verify_instructor_certificate(request, cert_id):
    cert = get_object_or_404(InstructorCertificate, id=cert_id)
    return render(request, 'instructor/verify_certificate.html', {
        'cert': cert,
    })


@login_required
def generate_instructor_certificate_pdf(request):
    try:
        instructor = Instructor.objects.get(user=request.user)
    except Instructor.DoesNotExist:
        return redirect('courses:course_view')

    course_id = request.POST.get("course_id")
    courses = Course.objects.filter(instructor=instructor, status_course__status='archived')
    if course_id:
        courses = courses.filter(id=course_id)

    enriched_certificates = []

    for course in courses:
        enrollments = Enrollment.objects.filter(course=course)
        total_enrolled = enrollments.count()
        if total_enrolled == 0:
            continue

        total_passed = 0
        total_score_accum = Decimal(0)
        total_progress_accum = Decimal(0)

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

                    correct_choices = set(
                        question.choices.filter(is_correct=True).values_list("id", flat=True)
                    )
                    user_choices = set(
                        user_answers.values_list("choice_id", flat=True)
                    )

                    if user_choices == correct_choices:
                        user_score += Decimal(assessment.weight) / Decimal(total_questions)

                if not has_answered_assessment:
                    user_submitted_all_assessments = False

            course_progress = CourseProgress.objects.filter(user=user, course=course).first()
            progress = course_progress.progress_percentage if course_progress else 0
            percentage = (user_score / total_max_score * 100) if total_max_score > 0 else 0

            is_passed = (
                progress == 100 and
                user_submitted_all_assessments and
                percentage >= passing_threshold
            )
            if is_passed:
                total_passed += 1

            total_score_accum += user_score
            total_progress_accum += Decimal(progress)

        passing_ratio = total_passed / total_enrolled
        if passing_ratio < 0.40:
            continue

        cert, _ = InstructorCertificate.objects.get_or_create(
            instructor=request.user,
            course=course,
            partner=course.org_partner,
        )

        cert.total_enrolled = total_enrolled
        cert.total_passed = total_passed
        cert.average_score = (total_score_accum / total_enrolled).quantize(Decimal('0.00'))
        cert.average_progress = (total_progress_accum / total_enrolled).quantize(Decimal('0.00'))

        # ---- Generate/check QR code file ----

        qr_folder = os.path.join(settings.MEDIA_ROOT, 'qrcodes')
        os.makedirs(qr_folder, exist_ok=True)

        qr_filename = f"certificate_{cert.id}.png"
        qr_path = os.path.join(qr_folder, qr_filename)

        if not os.path.exists(qr_path):
            verify_url = request.build_absolute_uri(
                reverse('instructor:verify_instructor_certificate', args=[cert.id])
            )
            qr = qrcode.QRCode(version=1, box_size=10, border=4)
            qr.add_data(verify_url)
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="black", back_color="white")
            qr_img.save(qr_path)

        qr_url = request.build_absolute_uri(settings.MEDIA_URL + f'qrcodes/{qr_filename}')
        cert.qr_url = qr_url  # Temp property untuk template

        # Untuk embed QR sebagai base64 (jika perlu)
        with open(qr_path, "rb") as f:
            qr_bytes = f.read()
        qr_base64 = base64.b64encode(qr_bytes).decode('utf-8')
        cert.qr_code_data_uri = f"data:image/png;base64,{qr_base64}"

        enriched_certificates.append(cert)

    if not enriched_certificates:
        return HttpResponse("Tidak ada kursus yang memenuhi syarat untuk sertifikat.", status=400)

    html_string = render_to_string('instructor/instructor_certificates.html', {
        'instructor': instructor,
        'certificates': enriched_certificates,
        'generated_at': timezone.now(),
        'base_url': request.build_absolute_uri('/')
    })

    html = HTML(string=html_string, base_url=request.build_absolute_uri('/'))
    pdf = html.write_pdf()

    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="instructor_certificates.pdf"'
    return response

# View untuk Instructor mengajukan kurasi
@login_required
def instructor_submit_curation(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    
    # Pastikan pengguna adalah Instructor dan ditugaskan ke kursus ini
    if not request.user.is_instructor or course.instructor.user != request.user:
        raise PermissionDenied("You do not have permission to submit this course for curation.")

    # Ambil materi dan assessment terkait kursus
    materials = Material.objects.filter(section__courses=course)
    assessments = Assessment.objects.filter(section__courses=course)

    # Tentukan apakah Instructor boleh mengajukan
    can_submit = False
    message = None

    if course.status_course.status == 'draft':
        # Status draft: Instructor boleh mengajukan (baru pertama kali atau setelah penolakan)
        can_submit = True
    elif course.status_course.status in ['curation', 'published', 'archived']:
        # Status curation, published, atau archived: Instructor tidak boleh mengajukan
        if course.status_course.status == 'curation':
            message = "This course has already been submitted for curation and is under review."
        elif course.status_course.status == 'published':
            message = "This course has already been published and cannot be resubmitted."
        elif course.status_course.status == 'archived':
            message = "This course has been archived and cannot be resubmitted."
    else:
        message = "Invalid course status."

    # Ambil riwayat penolakan terakhir (status 'draft')
    latest_rejection = course.status_history.filter(status='draft').last()

    # Jika Instructor boleh mengajukan dan request adalah POST
    if can_submit and request.method == "POST":
        # Validasi: Pastikan ada materi dan assessment
        if not materials.exists() or not assessments.exists():
            messages.error(request, "Course must have materials and assessments before submitting for curation.")
            return redirect('courses:studio', id=course.id)

        message = request.POST.get('message')
        if not message:
            messages.error(request, "Please provide a message for your submission.")
            return redirect('courses:studio', id=course.id)

        # Ubah status ke 'curation'
        course.change_status('curation', request.user, message=message)
        messages.success(request, "Course has been submitted for curation.")
        return redirect('courses:studio', id=course.id)

    # Render template dengan informasi apakah form boleh ditampilkan
    return render(request, 'instructor/submit_curation.html', {
        'course': course,
        'can_submit': can_submit,
        'message': message,
        'history': course.status_history.all(),
        'latest_rejection': latest_rejection,  # Tambahkan riwayat penolakan terakhir ke konteks
    })


# View untuk Partner meninjau kurasi

@login_required
def partner_review_curation(request, course_id):
    course = get_object_or_404(Course, id=course_id)

    # Pastikan pengguna adalah Partner dan memiliki hak atas kursus ini
    if not request.user.is_partner or course.org_partner.user != request.user:
        raise PermissionDenied("You do not have permission to review this course.")

    # Tentukan apakah Partner boleh mengajukan ke curation
    can_submit_to_curation = course.status_course.status == 'curation'

    if request.method == "POST":
        action = request.POST.get('action')
        message = request.POST.get('message')

        if not message:
            messages.error(request, "Please provide a message for your review.")
            return redirect('instructor:partner_review_curation', course_id=course.id)

        if action == 'accept':
            # Hanya izinkan mengajukan ke curation jika status saat ini adalah 'curation'
            if not can_submit_to_curation:
                messages.error(request, "Course cannot be submitted for curation from its current status.")
                return redirect('instructor:partner_review_curation', course_id=course.id)
            course.change_status('curation', request.user, message=message)
            messages.success(request, "Course has been accepted and submitted for Superuser review.")

        elif action == 'reject':
            # Partner boleh menolak ke 'draft', kecuali jika status adalah 'archived'
            if course.status_course.status == 'archived':
                messages.error(request, "Cannot reject an archived course. Please contact the Superuser to unarchive it first.")
                return redirect('instructor:partner_review_curation', course_id=course.id)
            course.change_status('draft', request.user, message=message)
            messages.success(request, "Course has been rejected and returned to Instructor for revisions.")
            # Kirim email notifikasi ke Instructor
            instructor_email = course.instructor.user.email if course.instructor else None
            if instructor_email:
                send_mail(
                    subject=f"Course Rejected: {course.course_name}",
                    message=f"Your course '{course.course_name}' has been rejected by the Partner.\nReason: {message}\nPlease revise and resubmit.",
                    from_email='noreply@yourdomain.com',
                    recipient_list=[instructor_email],
                    fail_silently=True,
                )
            # Kirim email notifikasi ke Superuser
            superusers = CustomUser.objects.filter(is_superuser=True)
            superuser_emails = [superuser.email for superuser in superusers if superuser.email]
            if superuser_emails:
                send_mail(
                    subject=f"Course Rejected to Draft by Partner: {course.course_name}",
                    message=f"The course '{course.course_name}' has been rejected by Partner and returned to Draft status.\nReason: {message}",
                    from_email='noreply@yourdomain.com',
                    recipient_list=superuser_emails,
                    fail_silently=True,
                )

        else:
            messages.error(request, "Invalid action.")
            return redirect('instructor:partner_review_curation', course_id=course.id)

        return redirect('courses:studio', id=course.id)

    return render(request, 'partner/review_curation.html', {
        'course': course,
        'history': course.status_history.all(),
        'can_submit_to_curation': can_submit_to_curation,
    })

# View untuk Superuser meninjau dan mempublikasikan
@login_required
def superuser_publish_course(request, course_id):
    course = get_object_or_404(Course, id=course_id)

    # Pastikan user superuser
    if not (request.user.is_superuser or getattr(request.user, 'is_curation', False)):
        raise PermissionDenied("You do not have permission to publish this course.")


    # Ambil harga kursus terbaru dengan price_type yang valid
    course_price = CoursePrice.objects.filter(course=course, price_type__isnull=False).order_by('-id').first()

    price_info = {
        'price_type_description': (
            course_price.price_type.description if course_price and course_price.price_type and course_price.price_type.description
            else course_price.price_type.name if course_price and course_price.price_type
            else 'Not set'
        ),
        'partner_price': course_price.partner_price if course_price else 0,
        'discount_percent': course_price.discount_percent if course_price else 0,
    }

    # Ambil semua pricing type sebagai pilihan payment_model
    payment_model_choices = PricingType.objects.all()

    if request.method == "POST":
        action = request.POST.get('action')

        # Update payment_model
        if action == 'update_payment_model':
            new_payment_model_id = request.POST.get('payment_model')
            try:
                new_payment_model = PricingType.objects.get(id=new_payment_model_id)
                course.payment_model = new_payment_model
                course.save()
                messages.success(request, f"Payment model updated to '{new_payment_model.name}'.")
            except PricingType.DoesNotExist:
                messages.error(request, "Invalid payment model selected.")
            return redirect('instructor:superuser_publish_course', course_id=course.id)

        # Semua aksi lain butuh pesan
        message = request.POST.get('message')
        if action in ['superuser_reject', 'superuser_archive', 'superuser_reject_to_draft'] and not message:
            messages.error(request, "Please provide a message for your action.")
            return redirect('instructor:superuser_publish_course', course_id=course.id)

        if action == 'superuser_publish':
            if course.status_course.status != 'curation':
                messages.error(request, "Course can only be published from 'Curation' status.")
                return redirect('instructor:superuser_publish_course', course_id=course.id)
            if not course_price:
                messages.error(request, "Cannot publish course without a set price.")
                return redirect('instructor:superuser_publish_course', course_id=course.id)
            course.change_status('published', request.user, message=message or "Published by Superuser.")
            messages.success(request, "Course has been published to the catalog.")

        elif action == 'superuser_reject':
            if course.status_course.status != 'curation':
                messages.error(request, "Course can only be rejected to Partner from 'Curation' status.")
                return redirect('instructor:superuser_publish_course', course_id=course.id)
            course.change_status('curation', request.user, message=message)
            messages.success(request, "Course has been rejected and returned to Partner for revisions.")

        elif action == 'superuser_archive':
            if course.status_course.status == 'archived':
                messages.error(request, "Course is already archived.")
                return redirect('instructor:superuser_publish_course', course_id=course.id)
            course.change_status('archived', request.user, message=message)
            messages.success(request, "Course has been archived.")

            instructor_email = course.instructor.user.email if course.instructor else None
            partner_email = course.org_partner.user.email if course.org_partner else None
            recipient_list = [email for email in [instructor_email, partner_email] if email]
            if recipient_list:
                email_message = (
                    f"The course '{course.course_name}' has been archived by Superuser.\n"
                    f"Price Type: {price_info['price_type_description']}\n"
                    f"Partner Price: {price_info['partner_price']}\n"
                    f"Discount: {price_info['discount_percent']}%\n"
                    f"Reason: {message}"
                )
                send_mail(
                    subject=f"Course Archived: {course.course_name}",
                    message=email_message,
                    from_email='noreply@yourdomain.com',
                    recipient_list=recipient_list,
                    fail_silently=True,
                )

        elif action == 'superuser_reject_to_draft':
            if course.status_course.status == 'draft':
                messages.error(request, "Course is already in 'Draft' status.")
                return redirect('instructor:superuser_publish_course', course_id=course.id)
            course.change_status('draft', request.user, message=message)
            messages.success(request, "Course has been rejected and returned to Instructor as Draft.")

            instructor_email = course.instructor.user.email if course.instructor else None
            partner_email = course.org_partner.user.email if course.org_partner else None
            recipient_list = [email for email in [instructor_email, partner_email] if email]
            if recipient_list:
                email_message = (
                    f"The course '{course.course_name}' has been rejected by Superuser and returned to Draft status.\n"
                    f"Price Type: {price_info['price_type_description']}\n"
                    f"Partner Price: {price_info['partner_price']}\n"
                    f"Discount: {price_info['discount_percent']}%\n"
                    f"Reason: {message}"
                )
                send_mail(
                    subject=f"Course Rejected to Draft: {course.course_name}",
                    message=email_message,
                    from_email='noreply@yourdomain.com',
                    recipient_list=recipient_list,
                    fail_silently=True,
                )

        else:
            messages.error(request, "Invalid action.")
            return redirect('instructor:superuser_publish_course', course_id=course.id)

        return redirect('courses:studio', id=course.id)

    return render(request, 'partner/publish_course.html', {
        'course': course,
        'history': course.status_history.all(),
        'price_info': price_info,
        'payment_model_choices': payment_model_choices,
        'current_payment_model': course.payment_model,
    })

@login_required
def studios(request, id):
    # ===============================
    # Ambil course
    # ===============================
    course = get_object_or_404(
        Course.objects.select_related(
            'status_course', 'org_partner', 'instructor', 'author', 'author__university'
        ),
        id=id
    )

    # Riwayat status
    status_history = course.status_history.all()

    # Konten course
    sections = Section.objects.filter(courses=course).prefetch_related('materials', 'assessments')
    materials = Material.objects.filter(section__courses=course)
    assessments = Assessment.objects.filter(section__courses=course)

    # Role user
    user = request.user
    is_instructor = user.is_instructor and course.instructor and course.instructor.user == user
    is_partner = user.is_partner and course.org_partner.user == user
    is_superuser = user.is_superuser

    # ===============================
    # AUTO CHECKLIST (REAL-TIME)
    # ===============================
    checklist_data = generate_course_checklist(course)
    checklist = checklist_data["checklist"]
    readiness = checklist_data["readiness_percentage"]

    is_course_ready = len(checklist) == 0

    # ===============================
    # POST ACTION
    # ===============================
    if request.method == "POST":
        action = request.POST.get("action")
        message = request.POST.get("message")

        # ========== Instructor submit ==========
        if action == "submit_curation" and is_instructor:
            if course.status_course.status != "draft":
                messages.error(request, "Course hanya bisa diajukan dari status Draft.")
            elif not is_course_ready:
                messages.error(
                    request,
                    "Course belum siap dikurasi. Lengkapi checklist terlebih dahulu."
                )
            elif not message:
                messages.error(request, "Pesan wajib diisi.")
            else:
                course.change_status("curation", user, message=message)
                messages.success(request, "Course berhasil diajukan ke kurasi.")
            return redirect("courses:studio", id=course.id)

        # ========== Partner review ==========
        elif action in ["partner_accept", "partner_reject"] and is_partner:
            if course.status_course.status != "curation":
                messages.error(request, "Course hanya bisa direview saat status Curation.")
            elif not message:
                messages.error(request, "Pesan wajib diisi.")
            else:
                if action == "partner_accept":
                    course.change_status("curation", user, message=message)
                    messages.success(request, "Course diteruskan ke Superuser.")
                else:
                    course.change_status("draft", user, message=message)
                    messages.success(request, "Course dikembalikan ke Instructor.")
            return redirect("courses:studio", id=course.id)

        # ========== Superuser ==========
        elif action in ["superuser_publish", "superuser_reject"] and is_superuser:
            if course.status_course.status != "curation":
                messages.error(request, "Course hanya bisa dipublish dari Curation.")
            elif action == "superuser_publish" and not is_course_ready:
                messages.error(
                    request,
                    "Course belum memenuhi checklist, tidak bisa dipublish."
                )
            elif action == "superuser_reject" and not message:
                messages.error(request, "Pesan wajib diisi.")
            else:
                if action == "superuser_publish":
                    course.change_status(
                        "published", user, message=message or "Published by Superuser."
                    )
                    messages.success(request, "Course berhasil dipublish.")
                else:
                    course.change_status("curation", user, message=message)
                    messages.success(request, "Course dikembalikan ke Partner.")
            return redirect("courses:studio", id=course.id)

    # ===============================
    # CONTEXT
    # ===============================
    context = {
        "course": course,
        "status_history": status_history,
        "sections": sections,
        "materials": materials,
        "assessments": assessments,
        "is_instructor": is_instructor,
        "is_partner": is_partner,
        "is_superuser": is_superuser,

        # Author info
        "author_full_name": course.author.username,
        "author_email": course.author.email,
        "author_university": course.author.university.name if course.author.university else "N/A",
        "author_gender": course.author.gender or "N/A",

        # Checklist
        "checklist": checklist,
        "readiness": readiness,
        "is_course_ready": is_course_ready,
    }

    return render(request, "instructor/studio.html", context)

def export_learning_report_csv(report_data):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="instructor_learning_report.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Learner Name', 'Email', 'University', 'Gender',
        'Course', 'Progress (%)', 'Materials Read', 'Materials Read (%)',
        'Assessments Completed', 'Assessments Completed (%)', 'Total Score', 'Threshold', 'Status',
        'Last Login', 'Material Name', 'Access Time', 'Duration (Minutes)', 
        'Assessment Name', 'Weight', 'Score'
    ])

    for data in report_data:
        # Materi
        for material in data['material_access_details']:
            writer.writerow([
                data['learner_full_name'],
                data['learner_email'],
                data['learner_university'],
                data['learner_gender'],
                data['course'].course_name,
                data['progress_percentage'],
                f"{data['materials_read']}/{data['total_materials']}",
                data['materials_read_percentage'],
                f"{data['assessments_completed']}/{data['total_assessments']}",
                data['assessments_completed_percentage'],
                data['total_score'],
                data['threshold'],
                data['status'],
                data['last_login'],
                material['material_name'],
                material['access_time'],
                material['duration'] if material['duration'] is not None else 'N/A',
                '', '', ''
            ])

        # Assessment
        for assessment in data['assessment_details']:
            writer.writerow([
                data['learner_full_name'],
                data['learner_email'],
                data['learner_university'],
                data['learner_gender'],
                data['course'].course_name,
                data['progress_percentage'],
                f"{data['materials_read']}/{data['total_materials']}",
                data['materials_read_percentage'],
                f"{data['assessments_completed']}/{data['total_assessments']}",
                data['assessments_completed_percentage'],
                data['total_score'],
                data['threshold'],
                data['status'],
                data['last_login'],
                '', '', '',
                assessment['name'],
                assessment['weight'],
                assessment['score'],
            ])

    return response





@login_required
def instructor_learner_detail_report(request):
    user = request.user
    learner_id = request.GET.get('learner_id')

    if not learner_id:
        raise PermissionDenied("Learner ID is required.")

    learner = get_object_or_404(
        CustomUser.objects.select_related('university'),
        id=learner_id
    )

    # ======================
    # SUPERUSER
    # ======================
    if user.is_superuser:
        courses = Course.objects.filter(
            enrollments__user=learner
        ).select_related('org_partner', 'instructor').distinct()

    # ======================
    # PARTNER
    # ======================
    elif user.is_partner:
        try:
            partner = user.partner_user
        except Partner.DoesNotExist:
            raise PermissionDenied("Partner profile not found.")

        courses = Course.objects.filter(
            org_partner=partner,
            enrollments__user=learner
        ).select_related('org_partner', 'instructor').distinct()

        if not courses.exists():
            raise PermissionDenied("Learner not in your partner scope.")

    # ======================
    # INSTRUCTOR
    # ======================
    elif user.is_instructor:
        instructor = Instructor.objects.filter(
            user=user,
            status='Approved'
        ).select_related('provider').first()

        if not instructor:
            raise PermissionDenied("Instructor profile not found or not approved.")

        courses = Course.objects.filter(
            instructor=instructor,
            org_partner=instructor.provider,
            enrollments__user=learner
        ).select_related('org_partner', 'instructor').distinct()

        if not courses.exists():
            raise PermissionDenied("Learner not in your course scope.")

    else:
        raise PermissionDenied("You do not have permission.")

    report_data = []

    # Ambil grade range untuk Pass
    grade_ranges = GradeRange.objects.filter(course__in=courses, name='Pass')
    grade_range_dict = {gr.course_id: gr.min_grade for gr in grade_ranges}

    for course in courses:
        # Ambil sections
        sections = Section.objects.filter(courses=course).prefetch_related(
            Prefetch('materials', queryset=Material.objects.all()),
            Prefetch('assessments', queryset=Assessment.objects.all())
        )

        # Ambil aktivitas learner
        material_reads = MaterialRead.objects.filter(user=learner, material__section__courses=course).select_related('material').order_by('read_at')
        assessment_reads = AssessmentRead.objects.filter(user=learner, assessment__section__courses=course).select_related('assessment').order_by('completed_at')
        question_answers = QuestionAnswer.objects.filter(user=learner, question__assessment__section__courses=course).select_related('question').order_by('answered_at')

        # Gabungkan aktivitas untuk durasi akses
        learner_activities = []
        for mr in material_reads:
            learner_activities.append(('material', mr.material.title, mr.read_at))
        for ar in assessment_reads:
            learner_activities.append(('assessment', ar.assessment.name, ar.completed_at))
        for qa in question_answers:
            learner_activities.append(('question', qa.question.text, qa.answered_at))
        learner_activities.sort(key=lambda x: x[2])

        # Progress
        user_progress, _ = CourseProgress.objects.get_or_create(user=learner, course=course)
        progress_percentage = user_progress.progress_percentage

        # Material stats
        materials = Material.objects.filter(section__courses=course)
        total_materials = materials.count()
        materials_read_percentage = (len(material_reads) / total_materials * 100) if total_materials else 0

        material_access_details = []
        for i, activity in enumerate(learner_activities):
            if activity[0] == 'material':
                access_time = activity[2]
                duration = None
                if i + 1 < len(learner_activities):
                    next_time = learner_activities[i + 1][2]
                    duration = (next_time - access_time).total_seconds() / 60
                material_access_details.append({
                    'material_name': activity[1],
                    'access_time': access_time,
                    'duration': duration
                })

        # Assessment stats
        assessments = Assessment.objects.filter(section__courses=course)
        total_assessments = assessments.count()
        assessments_completed = len(assessment_reads)
        assessments_completed_percentage = (assessments_completed / total_assessments * 100) if total_assessments else 0

        assessment_scores = []
        askora_details = []
        total_max_score = Decimal('0')
        total_score = Decimal('0')
        all_assessments_submitted = True  # rename biar jelas

        for assessment in assessments:
            score_value = Decimal('0')
            is_submitted = True  # default: anggap submitted sampai terbukti sebaliknya

            # 1. Prioritas tertinggi: LTI Result
            lti_result = LTIResult.objects.filter(user=learner, assessment=assessment).first()
            if lti_result and lti_result.score is not None:
                lti_score = Decimal(lti_result.score)
                if lti_score > 1.0:  # kadang datang dalam bentuk 0-100
                    lti_score /= 100
                score_value = lti_score * Decimal(assessment.weight)

            else:
                # 2. In-video Quiz
                invideo_quizzes = Quiz.objects.filter(assessment=assessment)
                if invideo_quizzes.exists():
                    quiz_result = QuizResult.objects.filter(user=learner, assessment=assessment).first()
                    if quiz_result and quiz_result.total_questions > 0:
                        score_value = (Decimal(quiz_result.score) / Decimal(quiz_result.total_questions)) * Decimal(assessment.weight)
                    else:
                        is_submitted = False
                        score_value = Decimal('0')

                else:
                    # 3. Regular Quiz (old question model)
                    total_questions = assessment.questions.count()
                    if total_questions > 0:
                        total_correct = sum(
                            QuestionAnswer.objects.filter(question=q, user=learner, choice__is_correct=True).count()
                            for q in assessment.questions.all()
                        )
                        answers_exist = QuestionAnswer.objects.filter(
                            question__in=assessment.questions.all(), user=learner
                        ).exists()

                        if not answers_exist:
                            is_submitted = False

                        score_value = (Decimal(total_correct) / Decimal(total_questions)) * Decimal(assessment.weight) if total_questions else Decimal('0')

                    else:
                        # 4. AskOra Submission
                        submissions = Submission.objects.filter(
                            askora__assessment=assessment,
                            user=learner
                        ).select_related('askora').prefetch_related(
                            Prefetch('peer_reviews', queryset=PeerReview.objects.select_related('reviewer'))
                        )

                        if not submissions.exists():
                            is_submitted = False
                            score_value = Decimal('0')
                        else:
                            latest = submissions.order_by('-submitted_at').first()
                            assessment_score = AssessmentScore.objects.filter(submission=latest).first()

                            if assessment_score and assessment_score.final_score is not None:
                                score_value = Decimal(assessment_score.final_score)
                            else:
                                is_submitted = False  # belum dinilai = belum complete
                                score_value = Decimal('0')

                            # Kumpulkan detail AskOra
                            peer_reviews_data = [
                                {
                                    'reviewer': pr.reviewer.get_full_name() or pr.reviewer.username,
                                    'score': pr.score,
                                    'weight': pr.weight,
                                    'comment': pr.comment or "No comment",
                                    'reviewed_at': pr.created_at
                                } for pr in latest.peer_reviews.all()
                            ]

                            askora_details.append({
                                'assessment_name': assessment.name,
                                'submission': latest,
                                'submitted_at': latest.submitted_at,
                                'final_score': assessment_score.final_score if assessment_score else None,
                                'peer_reviews': peer_reviews_data
                            })

            # Clamp score agar tidak melebihi bobot
            score_value = min(score_value, Decimal(assessment.weight))

            # Tambah ke breakdown
            assessment_scores.append({
                'name': assessment.name,
                'weight': float(assessment.weight),
                'score': score_value
            })

            total_score += score_value
            total_max_score += Decimal(assessment.weight)

            if not is_submitted:
                all_assessments_submitted = False

        # Total row
        assessment_scores.append({
            'name': 'Total',
            'weight': float(total_max_score),
            'score': total_score
        })

        # Hitung overall percentage dan status
        overall_percentage = (total_score / total_max_score * 100) if total_max_score > 0 else 0
        threshold = grade_range_dict.get(course.id, Decimal('52.00'))
        status = "Pass" if all_assessments_submitted and overall_percentage >= threshold else "Fail"

        #assessment_scores.append({'name': 'Total', 'weight': total_max_score, 'score': total_score})

        report_data.append({
            'course': course,
            'progress_percentage': progress_percentage,
            'materials_read': len(material_reads),
            'total_materials': total_materials,
            'materials_read_percentage': materials_read_percentage,
            'material_access_details': material_access_details,
            'assessments_completed': assessments_completed,
            'total_assessments': total_assessments,
            'assessments_completed_percentage': assessments_completed_percentage,
            'total_score': total_score,
            'threshold': threshold,
            'assessment_details': assessment_scores,
            'askora_submissions_details': askora_details,
            'status': status
        })

    # CSV export
    if 'export' in request.GET:
        import csv
        from django.http import HttpResponse

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="learner_detail_report_{learner.username}.csv"'
        writer = csv.writer(response)

        writer.writerow([
            'Learner', 'Email', 'University', 'Gender', 'Course',
            'Progress (%)', 'Materials Read', 'Materials Read (%)',
            'Assessments Completed', 'Assessments Completed (%)', 'Total Score', 'Threshold', 'Status',
            'Material', 'Access Time', 'Duration', 'Assessment', 'Weight', 'Score',
            'AskOra Assessment', 'Submission', 'Submitted At', 'Final Score', 'Peer Reviewer', 'Peer Score', 'Peer Comment'
        ])

        for data in report_data:
            # Materials
            for m in data['material_access_details']:
                writer.writerow([
                    learner.username, learner.email, learner.university.name if learner.university else 'N/A', learner.gender or 'N/A',
                    data['course'].course_name,
                    data['progress_percentage'], f"{data['materials_read']}/{data['total_materials']}", data['materials_read_percentage'],
                    f"{data['assessments_completed']}/{data['total_assessments']}", data['assessments_completed_percentage'],
                    data['total_score'], data['threshold'], data['status'],
                    m['material_name'], m['access_time'], m['duration'],
                    '', '', '', '', '', '', '', ''
                ])
            # Assessments
            for a in data['assessment_details']:
                writer.writerow([
                    learner.username, learner.email, learner.university.name if learner.university else 'N/A', learner.gender or 'N/A',
                    data['course'].course_name,
                    data['progress_percentage'], f"{data['materials_read']}/{data['total_materials']}", data['materials_read_percentage'],
                    f"{data['assessments_completed']}/{data['total_assessments']}", data['assessments_completed_percentage'],
                    data['total_score'], data['threshold'], data['status'],
                    '', '', '', a['name'], a['weight'], a['score'], '', '', '', '', '', '', ''
                ])
            # AskOra
            for ask in data['askora_submissions_details']:
                for pr in ask['peer_reviews']:
                    writer.writerow([
                        learner.username, learner.email, learner.university.name if learner.university else 'N/A', learner.gender or 'N/A',
                        data['course'].course_name,
                        data['progress_percentage'], f"{data['materials_read']}/{data['total_materials']}", data['materials_read_percentage'],
                        f"{data['assessments_completed']}/{data['total_assessments']}", data['assessments_completed_percentage'],
                        data['total_score'], data['threshold'], data['status'],
                        '', '', '', ask['assessment_name'], '', '',
                        ask['submission'], ask['submitted_at'], ask['final_score'],
                        pr['reviewer'], pr['score'], pr['comment']
                    ])

        return response

    context = {
        'learner': learner,
        'report_data': report_data,
    }
    return render(request, 'instructor/learner_detail_report.html', context)
