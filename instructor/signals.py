from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from courses.models import Enrollment, Course, InstructorCertificate
from authentication.models import CustomUser
from django.core.files.base import ContentFile
from django.template.loader import render_to_string
from weasyprint import HTML
from django.db.models.signals import pre_save
from .utils import update_course_checklist_db
from django.dispatch import receiver

@receiver(post_save, sender=Course)
def auto_update_course_checklist(sender, instance, **kwargs):
    update_course_checklist_db(instance)

@receiver(pre_save, sender=Course)
def issue_instructor_certificate_when_archived(sender, instance, **kwargs):
    try:
        # Ambil instance lama dari database
        old_instance = Course.objects.get(pk=instance.pk)
        old_status = old_instance.status_course.status if old_instance.status_course else None
    except Course.DoesNotExist:
        old_status = None  # Course baru, belum ada di DB

    new_status = instance.status_course.status if instance.status_course else None

    print(f">> Status lama: {old_status}, Status baru: {new_status}")

    # Hanya lanjut kalau status berubah ke 'archived'
    if new_status != 'archived' or old_status == 'archived':
        return

    if instance.end_date and instance.end_date > timezone.now().date():
        print(">> Course masih berlangsung, keluar")
        return

    instructor = getattr(instance, 'instructor', None)
    if not instructor or not getattr(instructor, 'is_instructor', False):
        print(">> Bukan instructor, keluar")
        return

    if InstructorCertificate.objects.filter(course=instance, instructor=instructor).exists():
        print(">> Sertifikat sudah ada, keluar")
        return

    total_enrolled = Enrollment.objects.filter(course=instance).count()
    total_completed = Enrollment.objects.filter(course=instance, certificate_issued=True).count()

    if total_enrolled == 0:
        print(">> Tidak ada peserta, keluar")
        return

    completion_rate = total_completed / total_enrolled
    print(f">> Completion rate: {completion_rate}")

    if completion_rate >= 0.5:
        cert = InstructorCertificate.objects.create(
            instructor=instructor,
            course=instance,
            partner=getattr(instance, 'org_partner', None)
        )
        print(f">> Sertifikat instructor berhasil dibuat: ID {cert.id}")



@receiver(post_save, sender=InstructorCertificate)
def generate_certificate_pdf(sender, instance, created, **kwargs):
    print(">> Signal buat PDF sertifikat instructor")

    if created and not instance.certificate_file:
        print(f">> Membuat PDF untuk sertifikat ID {instance.id}")
        html_string = render_to_string(
            'instructor/instructor_template.html',
            {'cert': instance}
        )

        pdf_file = HTML(string=html_string).write_pdf()
        filename = f"instructor_certificate_{instance.id}.pdf"
        instance.certificate_file.save(filename, ContentFile(pdf_file))
        print(">> File PDF berhasil disimpan")
    else:
        print(">> Tidak perlu membuat PDF (sudah ada atau bukan baru)")
