# myapp/signals.py
import logging
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.template.loader import render_to_string
from django.core.mail import EmailMessage
from django.conf import settings
from courses.models import Partner
from django.db.models.signals import post_migrate
from django.apps import apps
from django.contrib import messages
logger = logging.getLogger(__name__)

def send_partner_email_html(request, user, subject, template_name, context):
    """
    Kirim email HTML ke partner.
    - Jika konfigurasi email belum diatur di settings.py → beri peringatan dan batal kirim.
    - Jika user belum memiliki email → beri peringatan dan batal kirim.
    """

    # 🧩 1. Cek apakah konfigurasi email di settings sudah lengkap
    required_settings = ['EMAIL_HOST', 'EMAIL_PORT', 'DEFAULT_FROM_EMAIL']
    missing = [s for s in required_settings if not getattr(settings, s, None)]

    if missing:
        msg = f"Email configuration is incomplete: {', '.join(missing)}"
        logger.warning(msg)
        if request:
            messages.warning(request, msg)
        return  # hentikan fungsi, jangan kirim email

    # 🧩 2. Cek apakah user punya email
    if not getattr(user, 'email', None):
        msg = f"User '{getattr(user, 'username', 'Tanpa Nama')}' Email not available, so the message was not sent."
        logger.warning(msg)
        if request:
            messages.warning(request, msg)
        return

    # 🧩 3. Kirim email jika semua aman
    try:
        html_content = render_to_string(template_name, context)
        email = EmailMessage(
            subject=subject,
            body=html_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        email.content_subtype = "html"
        email.send(fail_silently=False)
        logger.info(f"Email successfully sent to {user.email} with subject '{subject}'.")
        if request:
            messages.success(request, f"Email successfully sent to {user.email}.")
    except Exception as e:
        logger.exception(f"Failed to send email to {user.email}: {str(e)}")
        if request:
            messages.error(request, "An error occurred while sending the email.")
# Simpan status lama sebelum disave
@receiver(pre_save, sender=Partner)
def cache_old_status(sender, instance, **kwargs):
    if instance.pk:
        try:
            old_instance = sender.objects.get(pk=instance.pk)
            instance._old_status = old_instance.status
        except sender.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None

def check_email_settings():
    """Cek apakah konfigurasi email sudah lengkap di settings.py"""
    required_settings = ['EMAIL_HOST', 'EMAIL_PORT', 'DEFAULT_FROM_EMAIL']
    missing = [s for s in required_settings if not getattr(settings, s, None)]
    if missing:
        msg = f"Email configuration is incomplete: {', '.join(missing)}"
        logger.warning(msg)
        return False, msg
    return True, None


@receiver(post_save, sender=Partner)
def notify_partner_status_change(sender, instance, created, **kwargs):
    """
    Kirim notifikasi email otomatis saat partner dibuat atau status berubah.
    - Jika konfigurasi email belum diatur → log & skip.
    - Jika user tidak punya email → log & skip.
    - Tangani error pengiriman email tanpa menghentikan signal.
    """

    ok, msg = check_email_settings()
    if not ok:
        logger.warning(f"Email tidak dikirim karena konfigurasi belum lengkap: {msg}")
        return

    if not getattr(instance.user, 'email', None):
        logger.warning(f"User '{instance.user.username}' belum memiliki email, abaikan pengiriman notifikasi.")
        return

    try:
        if created:
            # Partner baru dibuat
            send_partner_email_html(
                request=None,  # Signal tidak punya request
                user=instance.user,
                subject='Partner Request Submitted',
                template_name='email/partner_request_submitted.html',
                context={'user': instance.user, 'partner': instance},
            )
            logger.info(f"Email notifikasi: Partner request created for {instance.user.username}")
        else:
            # Status berubah
            old_status = getattr(instance, '_old_status', None)
            if old_status != instance.status:
                send_partner_email_html(
                    request=None,
                    user=instance.user,
                    subject='Partner Request Status Updated',
                    template_name='email/partner_request_status_updated.html',
                    context={'user': instance.user, 'partner': instance},
                )
                logger.info(f"Email notifikasi: Partner status changed for {instance.user.username}: {instance.status}")
    except Exception as e:
        logger.exception(f"Gagal mengirim email ke {instance.user.username}: {str(e)}")


#data permanen disini ya
@receiver(post_migrate)
def create_default_pricing_types(sender, **kwargs):
    # Pastikan hanya dijalankan untuk app ini
    if sender.name != 'courses':
        return

    PricingType = apps.get_model('courses', 'PricingType')
    
    data = [
        {
            "name": "Buy First",
            "code": "buy_first",
            "description": "Buy first, before access course material"
        },
        {
            "name": "Free",
            "code": "free",
            "description": "Course free access"
        },
        {
            "name": "Free to enroll, pay only when taking the exam",
            "code": "buy_take_exam",
            "description": "Free to enroll, pay only when taking the exam"
        },
        {
            "name": "Pay for certificate",
            "code": "pay_only_certificate",
            "description": "Enroll & take exam first, pay at certificate claim"
        }
    ]

    for item in data:
        PricingType.objects.get_or_create(code=item["code"], defaults=item)