from django.shortcuts import render, get_object_or_404, redirect
from courses.models import Partner
from authentication.models import Universiti
from courses.forms import PartnerFormUpdate
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator,EmptyPage, PageNotAnInteger
from django.http import HttpResponseForbidden
from courses.models import Course, Material,CourseStatus,GradeRange,MaterialRead,Question,AssessmentRead,Submission,QuestionAnswer,AssessmentScore,Section,Assessment, Enrollment,CourseRating,CourseComment,CourseViewLog,UserActivityLog,CourseSessionLog,Certificate
from payments.models import Payment
from authentication.models import CustomUser
from django.db.models import Avg, Count, Subquery, OuterRef, FloatField
from collections import defaultdict
from django.db.models import Avg, Count, Q,F,FloatField, ExpressionWrapper,DecimalField
from django.contrib import messages
from datetime import timedelta
from django.utils.timezone import now
from django.http import Http404
from django.db.models.functions import ExtractHour, ExtractWeekDay
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.cache import cache_page
import json
from django.db.models.functions import TruncDate, ExtractWeekDay
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Count, Sum
from .utils import get_geo_from_ip
from audit.models import AuditLog
from django.db.models.functions import TruncMonth
from collections import defaultdict
from decimal import Decimal
from django.db.models.functions import TruncWeek
from django.views.decorators.http import require_GET
from django_ratelimit.decorators import ratelimit
from django.views.decorators.cache import cache_page
from django.http import HttpResponse
import datetime, csv, json
from django.db.models import Count, Avg, Max, Min
from django.contrib.admin.views.decorators import staff_member_required
import pprint
from decimal import Decimal, ROUND_HALF_UP
from django.db.models.functions import Coalesce
from django.views.decorators.http import require_POST
import logging
from django.utils import timezone
from .forms import PartnerRequestForm
from django.conf import settings
from django.template.loader import render_to_string
from django.core.mail import EmailMessage
logger = logging.getLogger(__name__)


@user_passes_test(lambda u: u.is_staff)
def verify_partner_list(request):
    partners = Partner.objects.filter(status='pending')
    return render(request, 'partner/verify_list.html', {'partners': partners})

@user_passes_test(lambda u: u.is_staff)
def verify_partner_detail(request, pk):
    partner = get_object_or_404(Partner, pk=pk)
    
    if request.method == "POST":
        action = request.POST.get('action')
        note = request.POST.get('note', '')
        if action == 'approve':
            partner.approve(request.user)
        elif action == 'reject':
            partner.reject(note, request.user)
        elif action == 'revision':
            partner.request_revision(note, request.user)
        return redirect('partner:verify_partner_list')

    return render(request, 'partner/verify_detail.html', {'partner': partner})


# Utility function untuk email HTML
def send_partner_email_html(user, subject, template_name, context):
    """Kirim email HTML ke partner"""
    if user.email:
        html_content = render_to_string(template_name, context)
        email = EmailMessage(
            subject=subject,
            body=html_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        email.content_subtype = "html"
        email.send(fail_silently=False)
        logger.info(f"HTML email sent to {user.email}: {subject}")
    else:
        logger.warning(f"User {user.username} has no email, cannot send '{subject}'")


def request_partner(request):
    logger.info(f"Request method: {request.method}, User: {request.user}, Authenticated: {request.user.is_authenticated}")

    # 1️⃣ Cek login
    if not request.user.is_authenticated:
        logger.info("User not authenticated, redirecting to login")
        return redirect(f'/login/?next=/request-partner/')

    # 2️⃣ Cek apakah user sudah punya data Partner
    try:
        partner = Partner.objects.get(user=request.user)
        logger.info(f"Partner found: {partner.id}, Status: {partner.status}, Verified: {partner.is_verified}")

        # Partner sudah disetujui
        if partner.is_verified or partner.status == 'approved':
            logger.info("Partner already approved — redirecting to dashboard")
            return redirect('authentication:dashboard')

        # Status pending
        elif partner.status == 'pending':
            logger.info("Partner request pending — showing waiting page")
            return render(request, 'partner/status_pending.html', {'partner': partner})

        # Status revisi
        elif partner.status == 'revision':
            logger.info("Partner in revision mode")
            if request.method == 'POST':
                form = PartnerRequestForm(request.POST, request.FILES, instance=partner)
                if form.is_valid():
                    updated_partner = form.save(commit=False)
                    updated_partner.status = 'pending'
                    updated_partner.revision_note = ''
                    updated_partner.updated_by = request.user
                    updated_partner.updated_ad = timezone.now()
                    updated_partner.save()
                    logger.info(f"Partner revision resubmitted: {updated_partner.id}")

                    # Kirim email notifikasi revisi
                    send_partner_email_html(
                        request.user,
                        'Partner Request Resubmitted',
                        'email/partner_request_resubmitted.html',
                        {'user': request.user, 'partner': updated_partner}
                    )

                    return render(request, 'partner/request_resubmitted.html', {'partner': updated_partner})
                else:
                    logger.warning(f"Revision form invalid: {form.errors}")
            else:
                form = PartnerRequestForm(instance=partner)
            return render(request, 'partner/revision_form.html', {'form': form, 'partner': partner})

        # Status rejected
        elif partner.status == 'rejected':
            logger.info("Partner request rejected — showing page")
            return render(request, 'partner/status_rejected.html', {'partner': partner})

    except Partner.DoesNotExist:
        logger.info("No partner found, showing new form")
        partner = None

    # 3️⃣ Jika belum pernah request, tampilkan form baru
    if request.method == 'POST':
        form = PartnerRequestForm(request.POST, request.FILES)
        if form.is_valid():
            new_partner = form.save(commit=False)
            new_partner.user = request.user
            new_partner.author = request.user
            new_partner.status = 'pending'
            new_partner.save()
            logger.info(f"New partner request submitted: {new_partner.id}")

            # Kirim email notifikasi submit
            send_partner_email_html(
                request.user,
                'Partner Request Submitted',
                'email/partner_request_submitted.html',
                {'user': request.user, 'partner': new_partner}
            )

            return render(request, 'partner/request_success.html', {'partner': new_partner})
        else:
            logger.warning(f"Form invalid: {form.errors}")
    else:
        form = PartnerRequestForm()

    logger.info("Rendering new partner request form")
    return render(request, 'partner/request_partner.html', {'form': form})


@cache_page(60 * 5)
def partner_analytics_admin(request):
    if not request.user.is_superuser and not request.user.is_staff:
        return redirect('/')

    download = request.GET.get('download')
    partners = Partner.objects.select_related('name', 'author')

    # === CSV Export ===
    if download == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="partner_analytics.csv"'
        writer = csv.writer(response)
        writer.writerow(['Universiti', 'Author', 'Phone', 'Tax', 'ICEI Share', 'Balance', 'Created', 'Social Media'])

        for p in partners:
            social_list = [f for f in ['tiktok','youtube','facebook','instagram','linkedin','twitter'] if getattr(p, f)]
            writer.writerow([
                getattr(p.name, 'name', 'N/A'),
                p.author.get_full_name() or p.author.email,
                p.phone,
                f"{p.tax}%",
                f"{p.iceiprice}%",
                float(p.balance),
                p.created_ad.strftime("%Y-%m-%d"),
                ", ".join(social_list)
            ])
        return response

    # === Helper to floatify Decimals ===
    def floatify(obj):
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, list):
            return [floatify(i) for i in obj]
        elif isinstance(obj, dict):
            return {k: floatify(v) for k, v in obj.items()}
        return obj

     # === 1. Growth Over Time ===
    monthly = partners.annotate(month=TruncMonth('created_ad')).values('month').annotate(total=Count('id')).order_by('month')
    growth_data = {
        'labels': [m['month'].strftime('%b %Y') for m in monthly],
        'datasets': [{'label': 'New Partners', 'data': [m['total'] for m in monthly], 'borderColor': '#3B82F6', 'fill': False}]
    }

    # === 2. Distribution by Universitas ===
    univ = partners.values('name__name').annotate(total=Count('id')).order_by('-total')[:10]
    university_data = {
        'labels': [u['name__name'] for u in univ],
        'datasets': [{'label': 'Partners', 'data': [u['total'] for u in univ], 'backgroundColor': '#10B981'}]
    }

    # === 3. Balance Stats (from Payments) ===
    balance_stats = Payment.objects.filter(status='completed').values('course__org_partner') \
        .annotate(total=Sum('snapshot_partner_earning')) \
        .aggregate(
            avg=Avg('total'),
            max=Max('total'),
            min=Min('total')
        )

    balance_stats = floatify(balance_stats)

    # === 4. Tax Distribution ===
    tax_qs = partners.values('tax').annotate(total=Count('id')).order_by('tax')
    tax_data = {
        'labels': [str(t['tax']) for t in tax_qs],
        'datasets': [{'label': 'Tax (%)', 'data': [t['total'] for t in tax_qs], 'backgroundColor': '#F87171'}]
    }

    # === 5. ICEI Share Distribution ===
    icei_qs = partners.values('iceiprice').annotate(total=Count('id')).order_by('iceiprice')
    icei_data = {
        'labels': [str(i['iceiprice']) for i in icei_qs],
        'datasets': [{'label': 'ICEI Share (%)', 'data': [i['total'] for i in icei_qs], 'backgroundColor': '#60A5FA'}]
    }

    # === 6. Social Media Presence ===
    social_fields = ['tiktok', 'youtube', 'facebook', 'instagram', 'linkedin', 'twitter']
    social_data = {
        'labels': [f.capitalize() for f in social_fields],
        'datasets': [{
            'label': 'Partners with Account',
            'data': [partners.exclude(**{f: ''}).exclude(**{f: None}).count() for f in social_fields],
            'backgroundColor': '#F59E0B'
        }]
    }

    # === 7. Top Authors ===
    top_authors = partners.values('author__email').annotate(total=Count('id')).order_by('-total')[:5]
    author_data = {
        'labels': [a['author__email'] for a in top_authors],
        'datasets': [{'label': 'Partners Created', 'data': [a['total'] for a in top_authors], 'backgroundColor': '#8B5CF6'}]
    }

    # === 8. Revenue per Partner ===
    revenue_per_partner = Payment.objects.filter(status='completed') \
        .values('course__org_partner__name__name') \
        .annotate(total=Sum('amount')).order_by('-total')[:10]
    revenue_data = {
        'labels': [r['course__org_partner__name__name'] for r in revenue_per_partner],
        'datasets': [{
            'label': 'Total Revenue',
            'data': [float(r['total']) if r['total'] else 0 for r in revenue_per_partner],
            'backgroundColor': '#4ADE80'
        }]
    }

    # === 9. Monthly Revenue Trend ===
    monthly_revenue = Payment.objects.filter(status='completed') \
        .annotate(month=TruncMonth('created_at')) \
        .values('month') \
        .annotate(total=Sum('amount')).order_by('month')
    monthly_revenue_data = {
        'labels': [m['month'].strftime('%b %Y') for m in monthly_revenue],
        'datasets': [{
            'label': 'Revenue',
            'data': [float(m['total']) if m['total'] else 0 for m in monthly_revenue],
            'borderColor': '#6366F1',
            'fill': False
        }]
    }

    # === 10. Completion Rate per Partner ===
    completion_qs = Enrollment.objects.filter(certificate_issued=True) \
        .values('course__org_partner__name__name') \
        .annotate(total=Count('id')).order_by('-total')[:10]
    completion_data = {
        'labels': [c['course__org_partner__name__name'] for c in completion_qs],
        'datasets': [{'label': 'Certificates Issued', 'data': [c['total'] for c in completion_qs], 'backgroundColor': '#FB923C'}]
    }

    # === 11. Courses per Partner ===
    courses_per_partner = Course.objects.values('org_partner__name__name') \
        .annotate(total=Count('id')).order_by('-total')[:10]
    course_count_data = {
        'labels': [c['org_partner__name__name'] for c in courses_per_partner],
        'datasets': [{'label': 'Courses', 'data': [c['total'] for c in courses_per_partner], 'backgroundColor': '#0EA5E9'}]
    }

    # === Chart Metadata ===
    chart_list = [
        {"id": "growthChart", "title": "Partner Growth (12 Months)"},
        {"id": "univChart", "title": "Top 10 Universitas"},
        {"id": "revenueChart", "title": "Top Revenue by Partner"},
        {"id": "monthlyRevenueChart", "title": "Revenue Trend (Monthly)"},
        {"id": "completionChart", "title": "Completion Rate (Top 10)"},
        {"id": "taxChart", "title": "Tax (%) Distribution"},
        {"id": "iceiChart", "title": "ICEI Share (%)"},
        {"id": "socialChart", "title": "Social Media Presence"},
        {"id": "authorChart", "title": "Top 5 Authors"},
        {"id": "courseCountChart", "title": "Total Courses by Partner"},
    ]

    context = {
        'growth_data': json.dumps(growth_data),
        'univ_data': json.dumps(university_data),
        'social_data': json.dumps(social_data),
        'author_data': json.dumps(author_data),
        'tax_data': json.dumps(tax_data),
        'icei_data': json.dumps(icei_data),
        'balance_avg': balance_stats.get('avg'),
        'balance_min': balance_stats.get('min'),
        'balance_max': balance_stats.get('max'),
        'revenue_data': json.dumps(revenue_data),
        'monthly_revenue_data': json.dumps(monthly_revenue_data),
        'completion_data': json.dumps(completion_data),
        'course_count_data': json.dumps(course_count_data),
        'chart_list': chart_list,
    }

    return render(request, 'partner/partner_analytics.html', context)

@ratelimit(key='ip', rate='60/m', block=True)
@require_GET
def partner_list_view(request):
    try:
        published_status = CourseStatus.objects.get(status='published')

        partners = (
            Partner.objects
            .annotate(
                published_course_count=Count(
                    'courses',
                    filter=Q(courses__status_course=published_status),
                    distinct=True
                )
            )
            .order_by('id')
        )

    except CourseStatus.DoesNotExist:
        partners = Partner.objects.none()

    paginator = Paginator(partners, 12)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'partner/partner_list.html', {
        'partners': page_obj,
    })


@login_required
def top_courses_by_revenue_view(request):
    user = request.user

    # cek role
    if user.is_superuser or getattr(user, 'is_staff', False) \
       or getattr(user, 'is_finance', False) or getattr(user, 'is_curatin', False):
        courses = Course.objects.all()
    elif getattr(user, 'is_partner', False):
        try:
            courses = Course.objects.filter(org_partner__user=user)
        except Exception:
            messages.error(request, "Akun Anda belum terhubung ke data Partner.")
            return redirect('authentication:dashboard')
    else:
        messages.error(request, "Anda tidak memiliki akses ke halaman ini.")
        return redirect('authentication:dashboard')

    courses = courses.annotate(
        revenue=Coalesce(
            Sum('payments__amount', filter=Q(payments__status='completed')),
            0,
            output_field=DecimalField()
        )
    ).order_by('-revenue')[:10]

    labels = [course.course_name for course in courses]
    revenues = [float(course.revenue) for course in courses]  # Convert Decimal ke float

    return render(request, 'partner/top_courses_revenue.html', {
        'labels': labels,
        'revenues': revenues,
    })

@login_required
def top_transaction_partners_view(request):
    user = request.user

    # cek role
    if user.is_superuser or getattr(user, 'is_staff', False) \
       or getattr(user, 'is_finance', False) or getattr(user, 'is_curatin', False):
        partners = Partner.objects.all()
    elif getattr(user, 'is_partner', False):
        try:
            partners = Partner.objects.filter(user=user)
        except Partner.DoesNotExist:
            messages.error(request, "Akun Anda belum terhubung ke data Partner.")
            return redirect('authentication:dashboard')
    else:
        messages.error(request, "Anda tidak memiliki akses ke halaman ini.")
        return redirect('authentication:dashboard')

    partners = partners.annotate(
        total_transactions=Count('courses__payments', distinct=True),
        paid_transactions=Count('courses__payments', filter=Q(courses__payments__status='completed'), distinct=True),
        pending_transactions=Count('courses__payments', filter=Q(courses__payments__status='pending'), distinct=True),
        expired_transactions=Count('courses__payments', filter=Q(courses__payments__status='expired'), distinct=True),
        total_amount=Sum('courses__payments__amount'),
        paid_amount=Sum('courses__payments__amount', filter=Q(courses__payments__status='completed')),
        pending_amount=Sum('courses__payments__amount', filter=Q(courses__payments__status='pending')),
        expired_amount=Sum('courses__payments__amount', filter=Q(courses__payments__status='expired'))
    ).order_by('-total_transactions')[:10]

    labels = [partner.name if isinstance(partner.name, str) else partner.name.name for partner in partners]
    transaction_counts = [partner.total_transactions for partner in partners]
    paid_counts = [partner.paid_transactions for partner in partners]
    pending_counts = [partner.pending_transactions for partner in partners]
    expired_counts = [partner.expired_transactions for partner in partners]

    transaction_totals = [float(partner.total_amount or 0) for partner in partners]
    paid_totals = [float(partner.paid_amount or 0) for partner in partners]
    pending_totals = [float(partner.pending_amount or 0) for partner in partners]
    expired_totals = [float(partner.expired_amount or 0) for partner in partners]

    partner_data = list(zip(
        labels, transaction_counts,
        paid_counts, pending_counts, expired_counts,
        transaction_totals, paid_totals, pending_totals, expired_totals
    ))

    context = {
        'partner_data': partner_data,
        'labels_json': json.dumps(labels),
        'paid_counts_json': json.dumps(paid_counts),
        'pending_counts_json': json.dumps(pending_counts),
        'expired_counts_json': json.dumps(expired_counts),
        'paid_totals_json': json.dumps(paid_totals),
        'pending_totals_json': json.dumps(pending_totals),
        'expired_totals_json': json.dumps(expired_totals),
    }

    return render(request, 'partner/top_partners_transactions.html', context)




@login_required
def transaction_trends_view(request):
    user = request.user

    # cek role
    if user.is_superuser or getattr(user, 'is_staff', False) \
       or getattr(user, 'is_finance', False) or getattr(user, 'is_curatin', False):
        payments = Payment.objects.filter(status='completed')
    elif getattr(user, 'is_partner', False):
        try:
            partner = user.partner_user  # ambil relasi Partner
            payments = Payment.objects.filter(
                status='completed',
                course__org_partner=partner
            )
        except Partner.DoesNotExist:
            messages.error(request, "Akun Anda belum terhubung ke data Partner.")
            return redirect('authentication:dashboard')
    else:
        messages.error(request, "Anda tidak memiliki akses ke halaman ini.")
        return redirect('authentication:dashboard')

    # Data bulanan
    monthly_data = payments.annotate(
        month=TruncMonth('created_at')
    ).values('month').annotate(
        total_amount=Sum('amount'),
        transaction_count=Count('id')
    ).order_by('month')

    labels = [entry['month'].strftime('%b %Y') for entry in monthly_data]
    transaction_totals = [entry['total_amount'] or 0 for entry in monthly_data]
    transaction_counts = [entry['transaction_count'] for entry in monthly_data]

    return render(request, 'partner/transaction_trends.html', {
        'labels': labels,
        'transaction_totals': transaction_totals,
        'transaction_counts': transaction_counts,
    })



def has_access(user):
    """Cek apakah user memiliki akses ke dashboard/analytics."""
    if user.is_superuser or getattr(user, 'is_staff', False) or getattr(user, 'is_finance', False) or getattr(user, 'is_curatin', False):
        return True
    if getattr(user, 'is_partner', False):
        return True
    return False

@login_required
@user_passes_test(has_access, login_url='authentication:dashboard')
def active_partners_view(request):
    partners = Partner.objects.all()
    user = request.user

    # Pastikan profil user lengkap
    required_fields = {
        'first_name': 'First Name',
        'last_name': 'Last Name',
        'email': 'Email',
        'phone': 'Phone Number',
        'gender': 'Gender',
        'birth': 'Date of Birth',
    }
    missing_fields = [label for field, label in required_fields.items() if not getattr(user, field)]
    if missing_fields:
        messages.warning(request, f"Please complete the following information: {', '.join(missing_fields)}")
        return redirect('authentication:edit-profile', pk=user.pk)

    # Filter untuk partner
    if getattr(user, 'is_partner', False) and not user.is_superuser:
        try:
            partners = partners.filter(user=user)
        except Partner.DoesNotExist:
            messages.error(request, "Your account is not linked to Partner data.")
            return redirect('authentication:dashboard')

    partners = partners.annotate(
        total_courses=Count('courses', distinct=True),
        total_certificates=Count('courses__certificates', distinct=True)
    ).order_by('-total_courses', '-total_certificates')[:10]

    labels = [partner.name.name for partner in partners]
    course_counts = [partner.total_courses for partner in partners]
    certificate_counts = [partner.total_certificates for partner in partners]

    return render(request, 'partner/active_partners.html', {
        'labels': labels,
        'course_counts': course_counts,
        'certificate_counts': certificate_counts,
    })



def has_access(user):
    """Cek apakah user memiliki akses ke analytics/dashboard."""
    if user.is_superuser or getattr(user, 'is_staff', False) or getattr(user, 'is_finance', False) or getattr(user, 'is_curatin', False):
        return True
    if getattr(user, 'is_partner', False):
        return True
    return False

@login_required
@user_passes_test(has_access, login_url='authentication:dashboard')
def certificate_analytics_view(request):
    # Ambil semua course
    courses = Course.objects.all()

    # Filter khusus partner
    if getattr(request.user, 'is_partner', False) and not request.user.is_superuser:
        try:
            partner = request.user.partner_user
            courses = courses.filter(org_partner=partner)
        except Partner.DoesNotExist:
            messages.error(request, "Akun Anda belum terhubung ke data Partner.")
            return redirect('authentication:dashboard')

    # Sertifikat per bulan
    monthly_certificates = (
        Certificate.objects.filter(course__in=courses)
        .annotate(month=TruncMonth('issue_date'))
        .values('month')
        .annotate(count=Count('id'))
        .order_by('month')
    )
    labels = [entry['month'].strftime('%b %Y') for entry in monthly_certificates]
    counts = [entry['count'] for entry in monthly_certificates]

    # Rata-rata skor per course
    avg_scores = (
        Certificate.objects.filter(course__in=courses)
        .values('course__course_name')
        .annotate(avg_score=Avg('total_score'))
        .order_by('-avg_score')[:10]
    )
    score_labels = [entry['course__course_name'] for entry in avg_scores]
    scores = [float(entry['avg_score']) for entry in avg_scores]

    return render(request, 'partner/certificate_analytics.html', {
        'labels': labels,
        'counts': counts,
        'score_labels': score_labels,
        'scores': scores,
    })


def has_access(user):
    """Cek apakah user memiliki akses ke analytics/dashboard."""
    if user.is_superuser or getattr(user, 'is_staff', False) or getattr(user, 'is_finance', False) or getattr(user, 'is_curatin', False):
        return True
    if getattr(user, 'is_partner', False):
        return True
    return False

@login_required
@user_passes_test(has_access, login_url='authentication:dashboard')
def course_dropoff_rate_view(request):
    courses = Course.objects.all()

    # Filter khusus partner
    if getattr(request.user, 'is_partner', False) and not request.user.is_superuser:
        try:
            partner = request.user.partner_user
            courses = courses.filter(org_partner=partner)
        except Partner.DoesNotExist:
            messages.error(request, "Akun Anda belum terhubung ke data Partner.")
            return redirect('authentication:dashboard')

    data = (
        Enrollment.objects.filter(course__in=courses)
        .values('course__course_name')
        .annotate(
            total_enrolled=Count('id'),
            total_completed=Count('id', filter=Q(certificate_issued=True))
        )
        .order_by('-total_enrolled')[:10]
    )

    labels = [entry['course__course_name'] for entry in data]
    completed = [entry['total_completed'] for entry in data]
    dropoffs = [entry['total_enrolled'] - entry['total_completed'] for entry in data]

    return render(request, 'partner/course_dropoff_rate.html', {
        'labels': labels,
        'completed': completed,
        'dropoffs': dropoffs,
    })


@login_required
@user_passes_test(lambda u: u.is_superuser or u.is_partner)
def course_enrollment_growth_view(request):
    courses = Course.objects.all()

    # Filter untuk partner
    if request.user.is_partner and not request.user.is_superuser:
        try:
            partner = request.user.partner_user
            courses = courses.filter(org_partner=partner)
        except Partner.DoesNotExist:
            messages.error(request, "Akun Anda belum terhubung ke data Partner.")
            return redirect('authentication:dashboard')

    enrollments = (
        Enrollment.objects.filter(course__in=courses)
        .annotate(month=TruncMonth('enrolled_at'))
        .values('course__course_name', 'month')
        .annotate(count=Count('id'))
        .order_by('month')
    )

    course_data = defaultdict(lambda: defaultdict(int))
    months_set = set()

    for entry in enrollments:
        course_name = entry['course__course_name']
        month = entry['month'].strftime('%Y-%m')
        course_data[course_name][month] = entry['count']
        months_set.add(month)

    all_months = sorted(list(months_set))

    datasets = []
    for i, (course, month_data) in enumerate(course_data.items()):
        datasets.append({
            'label': course,
            'data': [month_data.get(month, 0) for month in all_months],
            'color_hue': (i * 45) % 360,
        })

    return render(request, 'partner/course_enrollment_growth.html', {
        'labels': all_months,
        'datasets': datasets,
    })


def has_access(user):
    """Cek apakah user memiliki akses ke analytics/dashboard."""
    if user.is_superuser or getattr(user, 'is_staff', False) or getattr(user, 'is_finance', False) or getattr(user, 'is_curatin', False):
        return True
    if getattr(user, 'is_partner', False):
        return True
    return False

@login_required
@user_passes_test(has_access, login_url='authentication:dashboard')
def top_courses_by_rating_view(request):
    courses = Course.objects.all()

    # Jika partner, filter berdasarkan org_partner
    if getattr(request.user, 'is_partner', False) and not request.user.is_superuser:
        try:
            partner = request.user.partner_user  # relasi OneToOne ke Partner
            courses = courses.filter(org_partner=partner)
        except Partner.DoesNotExist:
            messages.error(request, "Akun Anda belum terhubung ke data Partner.")
            return redirect('authentication:dashboard')

    # Ambil top 10 courses berdasarkan rata-rata rating
    top_courses = (
        courses.annotate(avg_rating=Avg('ratings__rating'))
        .filter(avg_rating__isnull=False)
        .order_by('-avg_rating')[:10]
    )

    labels = [course.course_name for course in top_courses]
    ratings = [round(course.avg_rating, 2) for course in top_courses]

    return render(request, 'partner/top_courses_by_rating.html', {
        'labels': labels,
        'ratings': ratings,
    })

def has_access(user):
    if user.is_superuser or getattr(user, 'is_staff', False) or getattr(user, 'is_finance', False) or getattr(user, 'is_curatin', False):
        return True
    if getattr(user, 'is_partner', False):
        return True
    return False

@login_required
@user_passes_test(has_access, login_url='authentication:dashboard')
def retention_rate_view(request):
    today = now()
    start_date = today - timedelta(weeks=12)

    users = CustomUser.objects.filter(date_joined__gte=start_date)

    # Filter partner
    if getattr(request.user, 'is_partner', False) and not request.user.is_superuser:
        try:
            partner = request.user.partner_user
            users = users.filter(partner_user=partner)
        except Partner.DoesNotExist:
            messages.error(request, "Akun Anda belum terhubung ke data Partner.")
            return redirect('authentication:dashboard')

    # Cohorts mingguan
    cohorts = (
        users
        .annotate(week_joined=TruncWeek('date_joined'))
        .values('week_joined')
        .annotate(
            new_users=Count('id'),
            retained_users=Count('id', filter=Q(last_login__gte=F('date_joined') + timedelta(days=7)))
        )
        .order_by('week_joined')
    )

    week_labels = [c['week_joined'].strftime('%Y-%m-%d') if c['week_joined'] else 'Unknown' for c in cohorts]
    new_users = [c['new_users'] for c in cohorts]
    retained_users = [c['retained_users'] for c in cohorts]

    # Daily active users
    user_ids = users.values_list('id', flat=True)
    activity = (
        UserActivityLog.objects.filter(
            activity_type='login_view',
            timestamp__gte=start_date,
            user_id__in=user_ids
        )
        .annotate(day=TruncDate('timestamp'))
        .values('day')
        .annotate(active_users=Count('user', distinct=True))
        .order_by('day')
    )

    day_labels = [a['day'].strftime('%Y-%m-%d') if a['day'] else 'Unknown' for a in activity]
    daily_active_users = [a['active_users'] for a in activity]

    context = {
        'week_labels': week_labels,
        'new_users': new_users,
        'retained_users': retained_users,
        'day_labels': day_labels,
        'daily_active_users': daily_active_users,
    }

    return render(request, 'partner/retention_rate.html', context)






def is_passed(user, course):
    from courses.models import Assessment, QuestionAnswer, GradeRange, CourseProgress

    # Ambil semua assessment terkait course
    assessments = Assessment.objects.filter(section__courses=course).distinct()
    total_score = Decimal(0)
    total_max_score = Decimal(0)
    all_submitted = True

    for assessment in assessments:
        total_questions = assessment.questions.count()
        if total_questions == 0:
            continue

        correct_answers = 0
        answered = False
        for question in assessment.questions.all():
            answers = QuestionAnswer.objects.filter(question=question, user=user)
            if answers.exists():
                answered = True
                correct_answers += answers.filter(choice__is_correct=True).count()

        if not answered:
            all_submitted = False

        score = (Decimal(correct_answers) / Decimal(total_questions)) * Decimal(assessment.weight)
        total_score += score
        total_max_score += Decimal(assessment.weight)

    percentage = (total_score / total_max_score) * 100 if total_max_score > 0 else 0

    # Ambil progress dari CourseProgress
    course_progress = CourseProgress.objects.filter(user=user, course=course).first()
    progress_percentage = course_progress.progress_percentage if course_progress else 0

    # Ambil passing grade dari GradeRange
    grade_range = GradeRange.objects.filter(course=course).first()
    passing_threshold = grade_range.min_grade if grade_range else 0

    return progress_percentage == 100 and all_submitted and percentage >= passing_threshold


def has_access(user):
    # Superuser atau staff/finance/curatin bisa akses semua
    if user.is_superuser or getattr(user, 'is_staff', False) or getattr(user, 'is_finance', False) or getattr(user, 'is_curatin', False):
        return True
    # Partner bisa akses data course miliknya
    if getattr(user, 'is_partner', False):
        return True
    return False

@login_required
@user_passes_test(has_access, login_url='authentication:dashboard')
def course_completion_rate_view(request):
    # Base queryset
    courses = Course.objects.all()

    # Filter jika user adalah partner (bukan superuser)
    if getattr(request.user, 'is_partner', False) and not request.user.is_superuser:
        try:
            partner = request.user.partner_user
            courses = courses.filter(org_partner=partner)
        except Partner.DoesNotExist:
            messages.error(request, "Akun Anda belum terhubung ke data Partner.")
            return redirect('authentication:dashboard')

    # Annotate setiap course dengan:
    # - total_enrolled: jumlah enrollment
    # - total_completed: jumlah user yang passed (berdasarkan logika is_passed)
    courses_with_stats = courses.annotate(
        total_enrolled=Count('enrollments'),
    ).annotate(
        # Hitung berapa user yang passed berdasarkan logika is_passed kamu
        # (asumsi: ada field atau cara cepat di DB untuk tahu status passed)
        total_completed=Count(
            'enrollments',
            filter=Q(enrollments__user__courseprogress__course=F('id'),
                     enrollments__user__courseprogress__progress_percentage=100,
                     # Tambahkan kondisi assessment passed jika diperlukan
                     # Contoh: AND overall score >= passing threshold
                     )
        )
    ).filter(total_enrolled__gt=0) \
     .order_by('-total_enrolled')[:10]

    # Siapkan data untuk chart
    labels = [course.course_name for course in courses_with_stats]
    completed = [course.total_completed for course in courses_with_stats]
    not_completed = [course.total_enrolled - course.total_completed for course in courses_with_stats]

    return render(request, 'partner/course_completion_rate.html', {
        'labels': labels,
        'completed': completed,
        'not_completed': not_completed,
    })



def has_access(user):
    # Superuser atau staff/finance/curatin bisa akses semua
    if user.is_superuser or getattr(user, 'is_staff', False) or getattr(user, 'is_finance', False) or getattr(user, 'is_curatin', False):
        return True
    # Partner bisa akses data user miliknya
    if getattr(user, 'is_partner', False):
        return True
    return False

@login_required
@user_passes_test(has_access, login_url='authentication:dashboard')
def user_growth_view(request):
    users = CustomUser.objects.filter(date_joined__isnull=False)

    # Jika partner, filter user yang terkait partner
    if getattr(request.user, 'is_partner', False) and not request.user.is_superuser:
        try:
            partner = request.user.partner_user
            users = users.filter(partner_user=partner)
        except Partner.DoesNotExist:
            messages.error(request, "Akun Anda belum terhubung ke data Partner.")
            return redirect('authentication:dashboard')

    data = (
        users
        .annotate(month=TruncMonth('date_joined'))
        .values('month')
        .annotate(count=Count('id'))
        .order_by('month')
    )

    months = [entry['month'].strftime('%b %Y') for entry in data]
    counts = [entry['count'] for entry in data]

    return render(request, 'partner/user_growth.html', {
        'months': months,
        'counts': counts,
    })


def has_access(user):
    # Superuser atau staff/finance/curatin bisa akses semua
    if user.is_superuser or getattr(user, 'is_staff', False) or getattr(user, 'is_finance', False) or getattr(user, 'is_curatin', False):
        return True
    # Partner bisa akses course miliknya
    if getattr(user, 'is_partner', False):
        return True
    return False

@login_required
@user_passes_test(has_access, login_url='authentication:dashboard')
def popular_courses_view(request):
    courses = Course.objects.all()

    # Jika user adalah partner, filter course khusus partner
    if getattr(request.user, 'is_partner', False) and not request.user.is_superuser:
        try:
            partner = request.user.partner_user
            courses = courses.filter(org_partner=partner)
        except Partner.DoesNotExist:
            messages.error(request, "Akun Anda belum terhubung ke data Partner.")
            return redirect('authentication:dashboard')

    data = courses.annotate(enrollment_count=Count('enrollments')).order_by('-enrollment_count')[:10]

    labels = [course.course_name for course in data]
    counts = [course.enrollment_count for course in data]

    return render(request, 'partner/popular_courses.html', {
        'labels': labels,
        'counts': counts,
    })



def has_analytics_access(user):
    """Cek apakah user bisa mengakses analytics/learning views."""
    return user.is_authenticated and (
        user.is_superuser
        or getattr(user, 'is_partner', False)
        or getattr(user, 'is_curation', False)
        or getattr(user, 'is_finance', False)
    )

@login_required
@user_passes_test(has_analytics_access)
def device_usage_view(request):
    logs = AuditLog.objects.filter(action='login')
    user = request.user

    # Filter logs jika user partner
    can_access_all = user.is_superuser or getattr(user, 'is_finance', False) or getattr(user, 'is_curation', False)
    if not can_access_all and getattr(user, 'is_partner', False):
        partner = getattr(user, 'partner_user', None)
        if partner:
            logs = logs.filter(user__enrollments__course__org_partner=partner).distinct()
        else:
            logs = logs.none()  # partner invalid → kosong

    # Aggregate device usage
    data = (
        logs.values('device_type')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    labels = [item['device_type'] or 'Unknown' for item in data]
    counts = [item['count'] for item in data]

    return render(request, 'partner/device_usage.html', {
        'labels': labels,
        'counts': counts,
    })


def has_analytics_access(user):
    """Cek apakah user bisa mengakses analytics/learning views."""
    return user.is_authenticated and (
        user.is_superuser
        or getattr(user, 'is_partner', False)
        or getattr(user, 'is_curation', False)
        or getattr(user, 'is_finance', False)
    )

@login_required
@user_passes_test(has_analytics_access)
def participant_geography_view(request):
    view_mode = request.GET.get('view', 'country')  # default: country

    logs = CourseSessionLog.objects.exclude(location_country__isnull=True)
    user = request.user

    # Filter logs jika user partner
    can_access_all = user.is_superuser or getattr(user, 'is_finance', False) or getattr(user, 'is_curation', False)
    if not can_access_all and getattr(user, 'is_partner', False):
        partner = getattr(user, 'partner_user', None)
        if partner:
            partner_courses = Course.objects.filter(org_partner=partner)
            logs = logs.filter(course__in=partner_courses)
        else:
            logs = logs.none()  # partner invalid → kosong

    # Aggregate data
    if view_mode == 'city':
        data = (
            logs.exclude(location_city__isnull=True)
            .values('location_country', 'location_city')
            .annotate(total=Count('id'))
            .order_by('-total')[:10]
        )
        labels = [f"{item['location_city']}, {item['location_country']}" for item in data]
    else:
        data = (
            logs.values('location_country')
            .annotate(total=Count('id'))
            .order_by('-total')[:10]
        )
        labels = [item['location_country'] for item in data]

    totals = [item['total'] for item in data]

    return render(request, 'partner/participant_geography.html', {
        'countries': labels,
        'totals': totals,
        'view_mode': view_mode,
    })



def has_analytics_access(user):
    """Cek apakah user bisa mengakses analytics/learning views."""
    return user.is_authenticated and (
        user.is_superuser
        or getattr(user, 'is_partner', False)
        or getattr(user, 'is_curation', False)
        or getattr(user, 'is_finance', False)
    )

@login_required
@user_passes_test(has_analytics_access)
def learning_duration_view(request):
    user = request.user
    can_access_all = user.is_superuser or getattr(user, 'is_finance', False) or getattr(user, 'is_curation', False)

    # Ambil daftar course berdasarkan role
    if can_access_all:
        courses = Course.objects.all()
    else:
        partner = getattr(user, 'partner_user', None)
        if not partner:
            raise Http404("Partner profile not found.")
        courses = Course.objects.filter(org_partner=partner)

    session_logs = CourseSessionLog.objects.filter(course__in=courses)

    today = now().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)

    # Total waktu belajar dalam detik
    weekly_seconds = session_logs.filter(started_at__date__gte=week_ago).aggregate(total=Sum('duration_seconds'))['total'] or 0
    monthly_seconds = session_logs.filter(started_at__date__gte=month_ago).aggregate(total=Sum('duration_seconds'))['total'] or 0

    # Waktu belajar per course (top 10)
    duration_by_course = (
        session_logs
        .values('course__course_name')
        .annotate(total_seconds=Sum('duration_seconds'))
        .order_by('-total_seconds')[:10]
    )

    # Konversi detik ke menit
    for item in duration_by_course:
        item['total_minutes'] = round(item['total_seconds'] / 60)

    context = {
        'weekly_minutes': round(weekly_seconds / 60),
        'monthly_minutes': round(monthly_seconds / 60),
        'duration_by_course': duration_by_course,
    }

    return render(request, 'partner/learning_duration.html', context)


@csrf_exempt
@login_required
def ping_session(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            course_id = data.get("course_id")
            course = Course.objects.get(id=course_id)
        except (json.JSONDecodeError, Course.DoesNotExist):
            return JsonResponse({"error": "Invalid course_id"}, status=400)

        ip_address = get_client_ip(request)

        session, created = CourseSessionLog.objects.get_or_create(
            user=request.user,
            course=course,
            ended_at__isnull=True,
            defaults={
                "started_at": now(),
                "user_agent": request.META.get("HTTP_USER_AGENT", "")[:255],
                "ip_address": ip_address,
            }
        )

        session.ended_at = now()

        if not session.location_country:
            session.location_country, session.location_city = get_geo_from_ip(ip_address)

        session.save()

        return JsonResponse({"status": "ok", "duration_seconds": session.duration_seconds})

    return JsonResponse({"error": "Invalid method"}, status=405)


def get_client_ip(request):
    x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded:
        return x_forwarded.split(",")[0]
    return request.META.get("REMOTE_ADDR")


def has_analytics_access(user):
    """Cek apakah user bisa mengakses analytics/login trends."""
    return user.is_authenticated and (
        user.is_superuser 
        or getattr(user, 'is_partner', False) 
        or getattr(user, 'is_curation', False) 
        or getattr(user, 'is_finance', False)
    )

@login_required
@user_passes_test(has_analytics_access)
def login_trends_view(request):
    user = request.user
    can_access_all = user.is_superuser or getattr(user, 'is_finance', False) or getattr(user, 'is_curation', False)

    # Filter log berdasarkan role
    logs = UserActivityLog.objects.filter(activity_type='login_view')
    if not can_access_all:
        # Partner → hanya log miliknya sendiri
        logs = logs.filter(user=user)

    # Log per tanggal
    logins_per_day = (
        logs
        .annotate(date=TruncDate('timestamp'))
        .values('date')
        .annotate(count=Count('id'))
        .order_by('date')
    )

    # Log per weekday
    logins_by_day = (
        logs
        .annotate(weekday=ExtractWeekDay('timestamp'))
        .values('weekday')
        .annotate(count=Count('id'))
        .order_by('weekday')
    )

    # Map nama hari (1=Sunday)
    days_map = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    login_day_data = [
        {"day": days_map[(item['weekday'] - 1) % 7], "count": item['count']}
        for item in logins_by_day
    ]

    context = {
        "logins_per_day": json.dumps([
            {"date": item['date'].strftime('%Y-%m-%d'), "count": item['count']}
            for item in logins_per_day
        ]),
        "logins_by_day": json.dumps(login_day_data),
    }

    return render(request, 'partner/login_trends.html', context)



# Hanya superuser dan partner yang boleh akses
def is_superuser_or_partner(user):
    return user.is_authenticated and (user.is_superuser or getattr(user, 'is_partner', False))

@login_required
@user_passes_test(lambda u: u.is_superuser or getattr(u, 'is_finance', False) 
                                or getattr(u, 'is_curation', False) 
                                or getattr(u, 'is_partner', False))
def heatmap_view(request):
    user = request.user

    # Tentukan data log sesuai role
    can_access_all = user.is_superuser or getattr(user, 'is_finance', False) or getattr(user, 'is_curation', False)
    if can_access_all:
        logs = UserActivityLog.objects.all()
    else:  # partner → hanya log miliknya sendiri
        logs = UserActivityLog.objects.filter(user=user)

    # Annotate hour dan weekday
    qs = (
        logs
        .annotate(
            hour=ExtractHour('timestamp'),
            weekday=ExtractWeekDay('timestamp')
        )
        .values('hour', 'weekday')
        .annotate(count=Count('id'))
        .order_by('hour', 'weekday')
    )

    # Format heatmap data
    heatmap_data = []
    for item in qs:
        hour = item['hour']
        weekday = (item['weekday'] - 1) % 7  # ubah dari 1=Sunday menjadi 0=Sunday
        heatmap_data.append({
            "x": hour,
            "y": weekday,
            "v": item['count'],
        })

    return render(request, 'partner/heatmap.html', {
        'heatmap_data': json.dumps(heatmap_data),
    })

@login_required
def partner_analytics_view(request):
    user = request.user

    # Pastikan user melengkapi data profil
    required_fields = {
        'first_name': 'First Name',
        'last_name': 'Last Name',
        'email': 'Email',
        'phone': 'Phone Number',
        'gender': 'Gender',
        'birth': 'Date of Birth',
    }
    missing_fields = [label for field, label in required_fields.items() if not getattr(user, field)]
    if missing_fields:
        messages.warning(request, f"Please complete the following information: {', '.join(missing_fields)}")
        return redirect('authentication:edit-profile', pk=user.pk)

    # Cek role: superuser, finance, curation, atau partner
    can_access_all = user.is_superuser or getattr(user, 'is_finance', False) or getattr(user, 'is_curation', False)
    is_partner = getattr(user, 'is_partner', False)

    if not (can_access_all or is_partner):
        messages.error(request, "Access denied. You do not have permission to view the participants of this course.")
        return redirect('authentication:home')

    # Ambil courses sesuai role
    if can_access_all:
        courses = Course.objects.all().only('id', 'course_name')
    else:  # partner → hanya course miliknya
        partner = getattr(user, 'partner_user', None)
        if not partner:
            raise Http404("Partner profile not found.")
        courses = Course.objects.filter(org_partner=partner).only('id', 'course_name')

    # Ambil log view untuk courses
    logs = CourseViewLog.objects.filter(course__in=courses).select_related('course')

    # Hitung referensi waktu
    today = now().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)

    # Total views dalam 7 hari dan 30 hari terakhir
    weekly_views = logs.filter(date__gte=week_ago).aggregate(total=Count('count'))['total'] or 0
    monthly_views = logs.filter(date__gte=month_ago).aggregate(total=Count('count'))['total'] or 0

    # Top 10 views per course
    view_by_course = (
        logs.values('course__course_name')
        .annotate(total=Count('count'))
        .order_by('-total')[:10]
    )

    # Top 10 comments per course
    comment_by_course = (
        CourseComment.objects.filter(course__in=courses)
        .values('course__course_name')
        .annotate(total=Count('id'))
        .order_by('-total')[:10]
    )

    context = {
        'weekly_views': weekly_views,
        'monthly_views': monthly_views,
        'view_by_course': view_by_course,
        'comment_by_course': comment_by_course,
    }

    return render(request, 'partner/analytics.html', context)


@login_required
def partner_course_comments(request):
    # Jika superuser, ambil semua course dan komentar
    if request.user.is_superuser or request.user.is_curation:
        owned_courses = Course.objects.all()
    elif hasattr(request.user, 'partner_user'):
        # Jika partner, ambil hanya kursus miliknya
        partner = request.user.partner_user
        owned_courses = Course.objects.filter(org_partner=partner)
    else:
        # Selain itu, tolak akses
        return HttpResponseForbidden("You are not authorized to view this page.")

    # Ambil komentar utama dari course yang dimiliki
    comments = CourseComment.objects.filter(
        course__in=owned_courses,
        parent__isnull=True
    ).order_by('-created_at')

    # Paginasi
    paginator = Paginator(comments, 5)
    page = request.GET.get('page')
    try:
        comments_page = paginator.page(page)
    except PageNotAnInteger:
        comments_page = paginator.page(1)
    except EmptyPage:
        comments_page = paginator.page(paginator.num_pages)

    # Balasan komentar
    if request.method == 'POST':
        content = request.POST.get('content')
        parent_id = request.POST.get('parent_id')

        try:
            parent_comment = CourseComment.objects.get(id=parent_id, course__in=owned_courses)
        except CourseComment.DoesNotExist:
            return HttpResponseForbidden("Invalid parent comment.")

        if content:
            CourseComment.objects.create(
                user=request.user,
                content=content,
                course=parent_comment.course,
                parent=parent_comment
            )
            return redirect('partner:partner_course_comments')

    context = {
        'comments': comments_page
    }
    return render(request, 'partner/partner_course_comments.html', context)


@login_required
@require_POST
def delete_comment(request, comment_id):
    # Ambil komentar, pastikan comment_id valid dan terkait kursus milik user
    comment = get_object_or_404(CourseComment, id=comment_id)

    # Cek akses: superuser atau curation boleh hapus, atau partner yang memiliki kursus
    if not (request.user.is_superuser or request.user.is_curation):
        if not (hasattr(request.user, 'partner_user') and comment.course.org_partner == request.user.partner_user):
            return HttpResponseForbidden("You are not authorized to delete this comment.")

    # Hapus komentar
    comment.delete()
    messages.success(request, "Komentar berhasil dihapus.")
    # Redirect ke halaman komentar partner (bisa juga tambah pesan sukses kalau perlu)
    return redirect('partner:partner_course_comments')


@login_required
def post_comment_reply(request, course_id, comment_id=None):
    course = get_object_or_404(Course, id=course_id)

    # Pastikan yang mengakses adalah partner
    if not request.user.is_partner:
        return HttpResponseForbidden("You are not authorized to post replies.")

    if request.method == 'POST':
        content = request.POST.get('content')

        # Validasi konten komentar
        if content:
            # Menambahkan balasan komentar
            if comment_id:
                parent_comment = get_object_or_404(CourseComment, id=comment_id)
                reply = CourseComment.objects.create(
                    user=request.user,
                    content=content,
                    course=course,
                    parent=parent_comment
                )
                messages.success(request, "Your reply has been posted!")
            else:
                # Bisa digunakan jika Anda ingin menambah komentar baru juga
                CourseComment.objects.create(
                    user=request.user,
                    content=content,
                    course=course
                )
                messages.success(request, "Your comment has been posted!")
        else:
            messages.error(request, "Content cannot be empty.")

    return redirect('partner:course_lms_detail', id=course.id, slug=course.slug)

@login_required
def partner_course_ratings(request):
    user = request.user

    # === Hak akses ===
    if not (user.is_partner or user.is_curation or user.is_superuser):
        return HttpResponseForbidden("You are not authorized to view this page.")

    # === Filter dasar course ===
    if user.is_curation or user.is_superuser:
        courses = Course.objects.all()
    else:
        courses = Course.objects.filter(org_partner__user=user)

    # === Filter rating ===
    star = request.GET.get('star')  # klik bintang 1-5
    min_rating = request.GET.get('min_rating')
    max_rating = request.GET.get('max_rating')

    # Annotate rata-rata rating & jumlah rating
    courses = courses.annotate(
        avg_rating=Avg('ratings__rating'),
        rating_count=Count('ratings')
    )

    # Exact rating filter dulu (star) jika ada
    if star:
        courses = courses.filter(ratings__rating=int(star)).distinct()
    else:
        if min_rating:
            courses = courses.filter(avg_rating__gte=float(min_rating))
        if max_rating:
            courses = courses.filter(avg_rating__lte=float(max_rating))

    courses = courses.order_by('-avg_rating', 'id')

    # === Pagination ===
    paginator = Paginator(courses, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Ambil rating untuk course di halaman ini saja
    course_ids = [course.id for course in page_obj.object_list]
    ratings_qs = CourseRating.objects.filter(course_id__in=course_ids)\
                                     .select_related('user')\
                                     .order_by('-created_at')

    ratings_by_course = defaultdict(list)
    for rating in ratings_qs:
        ratings_by_course[rating.course_id].append(rating)

    context = {
        'course_rating_data': page_obj,
        'course_ratings_details': ratings_by_course,
        'selected_star': star,
        'min_rating': min_rating,
        'max_rating': max_rating,
    }

    return render(request, 'partner/partner_course_ratings.html', context)


def get_enrollments_filtered(user, direction, search_query):
    partner_university = user.university
    owned_courses = Course.objects.filter(org_partner__user=user)
    owned_course_ids = owned_courses.values_list('id', flat=True)

    if direction == "inbound":
        enrollments = Enrollment.objects.select_related("user", "course").filter(
            course__in=owned_course_ids
        ).exclude(user__university=partner_university)

    elif direction == "outbound":
        enrollments = Enrollment.objects.select_related("user", "course").filter(
            user__university=partner_university
        ).exclude(course__in=owned_course_ids)

    elif direction == "internal":
        enrollments = Enrollment.objects.select_related("user", "course").filter(
            user__university=partner_university,
            course__in=owned_course_ids
        )

    else:
        enrollments = Enrollment.objects.select_related("user", "course").filter(
            course__in=owned_course_ids
        )

    if search_query:
        enrollments = enrollments.filter(user__email__icontains=search_query)

    return enrollments, owned_courses

@login_required
def partner_enrollment_view(request):
    user = request.user
    if not user.is_partner:
        return HttpResponseForbidden("You are not authorized to view this page.")

    direction = request.GET.get("direction", "")
    search_query = request.GET.get("search", "")

    enrollments, owned_courses = get_enrollments_filtered(user, direction, search_query)

    user_courses_map = defaultdict(list)
    user_list = {}

    for enroll in enrollments:
        u = enroll.user
        course = enroll.course
        user_list[u.id] = u

        materials = Material.objects.filter(section__courses=course)
        total_materials = materials.count()
        materials_read = MaterialRead.objects.filter(user=u, material__in=materials).count()
        materials_read_pct = (Decimal(materials_read) / total_materials * 100) if total_materials > 0 else Decimal('0')

        assessments = Assessment.objects.filter(section__courses=course)
        total_assessments = assessments.count()
        assessments_completed = AssessmentRead.objects.filter(user=u, assessment__in=assessments).count()
        assessments_completed_pct = (Decimal(assessments_completed) / total_assessments * 100) if total_assessments > 0 else Decimal('0')

        progress = ((materials_read_pct + assessments_completed_pct) / 2).quantize(Decimal('1'), rounding=ROUND_HALF_UP)

        total_score = Decimal('0')
        total_max_score = Decimal('0')
        for assessment in assessments:
            score_value = Decimal('0')
            total_questions = assessment.questions.count()

            if total_questions > 0:
                total_correct = QuestionAnswer.objects.filter(
                    question__in=assessment.questions.all(),
                    user=u,
                    choice__is_correct=True
                ).count()
                score_value = (Decimal(total_correct) / Decimal(total_questions)) * Decimal(assessment.weight)
            else:
                submission = Submission.objects.filter(askora__assessment=assessment, user=u).order_by('-submitted_at').first()
                if submission:
                    score_obj = AssessmentScore.objects.filter(submission=submission).first()
                    if score_obj:
                        score_value = Decimal(score_obj.final_score)

            total_score += score_value
            total_max_score += Decimal(assessment.weight)

        overall_percentage = (total_score / total_max_score * 100) if total_max_score > 0 else Decimal('0')

        grade_range = GradeRange.objects.filter(course=course, name='Pass').first()
        passing_threshold = grade_range.min_grade if grade_range else Decimal('52.00')
        certificate_eligible = progress == 100 and overall_percentage >= passing_threshold

        user_courses_map[u.id].append({
            "name": course.course_name,
            "progress": float(progress),
            "passed": enroll.certificate_issued,
            "eligible": certificate_eligible,
            "score": float(overall_percentage),
            "threshold": float(passing_threshold),
        })

    users = list(user_list.values())
    users.sort(key=lambda u: u.id)
    paginator = Paginator(users, 10)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    context = {
        "users": page_obj,
        "direction": direction,
        "search_query": search_query,
        "owned_courses": owned_courses,
        "user_courses_map": user_courses_map,
        "total_users": len(users),
    }
    return render(request, "partner/partner_enrollments.html", context)

@login_required
def export_enrollments_csv(request):
    user = request.user
    if not user.is_partner:
        return HttpResponseForbidden("Not allowed")

    direction = request.GET.get("direction", "")
    search_query = request.GET.get("search", "")

    enrollments, _ = get_enrollments_filtered(user, direction, search_query)

    user_courses_map = defaultdict(list)
    user_list = {}

    for enroll in enrollments:
        u = enroll.user
        course = enroll.course
        user_list[u.id] = u

        materials = Material.objects.filter(section__courses=course)
        total_materials = materials.count()
        materials_read = MaterialRead.objects.filter(user=u, material__in=materials).count()
        materials_read_pct = (Decimal(materials_read) / total_materials * 100) if total_materials > 0 else Decimal('0')

        assessments = Assessment.objects.filter(section__courses=course)
        total_assessments = assessments.count()
        assessments_completed = AssessmentRead.objects.filter(user=u, assessment__in=assessments).count()
        assessments_completed_pct = (Decimal(assessments_completed) / total_assessments * 100) if total_assessments > 0 else Decimal('0')

        progress = ((materials_read_pct + assessments_completed_pct) / 2).quantize(Decimal('1'), rounding=ROUND_HALF_UP)

        total_score = Decimal('0')
        total_max_score = Decimal('0')
        for assessment in assessments:
            score_value = Decimal('0')
            total_questions = assessment.questions.count()

            if total_questions > 0:
                total_correct = QuestionAnswer.objects.filter(
                    question__in=assessment.questions.all(),
                    user=u,
                    choice__is_correct=True
                ).count()
                score_value = (Decimal(total_correct) / Decimal(total_questions)) * Decimal(assessment.weight)
            else:
                submission = Submission.objects.filter(askora__assessment=assessment, user=u).order_by('-submitted_at').first()
                if submission:
                    score_obj = AssessmentScore.objects.filter(submission=submission).first()
                    if score_obj:
                        score_value = Decimal(score_obj.final_score)

            total_score += score_value
            total_max_score += Decimal(assessment.weight)

        overall_percentage = (total_score / total_max_score * 100) if total_max_score > 0 else Decimal('0')

        grade_range = GradeRange.objects.filter(course=course, name='Pass').first()
        passing_threshold = grade_range.min_grade if grade_range else Decimal('52.00')
        certificate_eligible = progress == 100 and overall_percentage >= passing_threshold

        user_courses_map[u.id].append({
            "name": course.course_name,
            "progress": float(progress),
            "passed": enroll.certificate_issued,
            "eligible": certificate_eligible,
            "score": float(overall_percentage),
            "threshold": float(passing_threshold),
        })

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="enrollments.csv"'
    writer = csv.writer(response)
    writer.writerow(['Username', 'Email', 'University', 'Course', 'Progress', 'Score', 'Status'])

    for user_id, courses in user_courses_map.items():
        u = user_list[user_id]
        for course in courses:
            writer.writerow([
                u.username,
                u.email,
                u.university.name if u.university else '-',
                course["name"],
                f"{course['progress']}%",
                f"{course['score']}%",
                "Pass" if course["passed"] else "Not Yet"
            ])

    return response

# update your views here.
@login_required
def partner_update_view(request, partner_id, universiti_slug):
    # Mendapatkan partner yang sesuai dengan ID yang diberikan
    partner = get_object_or_404(Partner, id=partner_id)

    # Mendapatkan universitas berdasarkan slug
    universiti = get_object_or_404(Universiti, slug=universiti_slug)

    # Mengecek apakah pengguna yang sedang login adalah pemilik partner tersebut
    if partner.user != request.user:
        return redirect('authentication:home')  # Redirect ke halaman jika pengguna bukan pemilik data
    if partner.name != universiti:
        return redirect('authentication:home')

    
    # Jika form dikirim (POST)
    if request.method == 'POST':
        form = PartnerFormUpdate(request.POST, request.FILES, instance=partner)
        if form.is_valid():
            partner = form.save(commit=False)
            partner.universiti = universiti  # Update universiti ke partner yang diubah
            partner.save()
            return redirect('courses:partner_detail', partner_id=partner.id)  # Redirect ke halaman profil partner
    else:
        form = PartnerFormUpdate(instance=partner)

    return render(request, 'partner/partner_update.html', {'form': form, 'universiti': universiti})


def explore(request):
    # Ambil semua mitra dari database
    partners_list = Partner.objects.all()
    
    # Tentukan jumlah mitra per halaman
    paginator = Paginator(partners_list, 6)  # Tampilkan 6 mitra per halaman
    
    # Dapatkan halaman yang saat ini diminta
    page_number = request.GET.get('page')  # Mendapatkan nomor halaman dari query parameter
    page_obj = paginator.get_page(page_number)  # Dapatkan objek halaman sesuai nomor halaman
    
    # Render halaman dengan mitra yang ditemukan dan objek pagination
    return render(request, 'partner/explore.html', {'page_obj': page_obj})