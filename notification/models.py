from django.db import models
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey

# Create your models here.
class Notification(models.Model):
    NOTIF_TYPES = (
        # Transaksi & Enrollment
        ('enrollment_success', 'Enrollment Berhasil'),
        ('payment_success', 'Pembayaran Berhasil'),
        ('payment_failed', 'Pembayaran Gagal'),
        
        # Belajar & Progress
        ('new_lesson', 'Materi Baru'),
        ('new_quiz', 'Quiz/Tugas Baru'),
        ('deadline_reminder', 'Pengingat Deadline'),
        ('progress_milestone', 'Pencapaian Progress'),
        ('certificate_issued', 'Sertifikat Diterbitkan'),
        
        # Interaksi
        ('instructor_announcement', 'Pengumuman dari Pengajar'),
        ('new_review', 'Review Baru pada Course-mu'),
        ('submission_received', 'Submission Reviewed'),
        ('new_course_comment', 'New Course Comment'),
        # 🔵 Partner Workflow
        ('partner_request_submitted', 'Partner Request Submitted'),
        ('partner_request_resubmitted', 'Partner Request Resubmitted'),
        ('partner_approved', 'Partner Approved'),
        ('partner_rejected', 'Partner Rejected'),
        ('partner_revision', 'Partner Revision Required'),

        #course curation
        ('assigned_course_instructor', 'Assigned Course Instructor'),
        ('course_submitted', 'Course Submitted'),
        ('course_ready_publish', 'Course Ready for Publish'),
        ('course_rejected_partner', 'Course Rejected by Partner'),
        ('course_rejected_superuser', 'Course Rejected by Superuser'),
        ('course_published', 'Course Published'),
        
    )

    PRIORITY_CHOICES = (
        ('low', 'Rendah'),
        ('medium', 'Sedang'),
        ('high', 'Penting'),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    
    # Siapa yang memicu (penting untuk instructor/student interaksi)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='triggered_notifications'
    )

    notif_type = models.CharField(max_length=40, choices=NOTIF_TYPES)
    priority   = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    
    title      = models.CharField(max_length=255, blank=True)
    message    = models.TextField()
    is_read    = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Deep link (fallback jika tidak pakai generic)
    link       = models.CharField(max_length=500, blank=True, null=True)

    # Generic relation → paling fleksibel
    content_type   = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True)
    object_id      = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read']),
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['notif_type', 'priority']),
        ]

    def __str__(self):
        return f"[{self.notif_type}] {self.user.username} - {self.message[:60]}"

    def mark_as_read(self):
        if not self.is_read:
            self.is_read = True
            self.save(update_fields=['is_read'])