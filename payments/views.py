# payments/views.py

import requests
from django.conf import settings
from types import SimpleNamespace
from django.shortcuts import render
from django.db.models import Sum, Count
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
import logging
from courses.models import Course,CoursePrice,Partner,Enrollment,CalculateAdminPrice
from payments.models import CartItem,Transaction,Payment, Voucher,VoucherUsage  # pastikan model keranjang belanja kamu ini
from django.utils.timezone import now
from django.db import IntegrityError
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.utils.http import urlencode
from django.db.models import Q
from django.utils import timezone
import json, time
from datetime import timedelta
from weasyprint import HTML
from django.http import HttpResponse
from django.template.loader import render_to_string
from .utils import get_client_ip, get_geo_from_ip, validate_voucher, get_tripay_payment_channels,create_tripay_transaction,send_checkout_email,send_payment_confirmation_email
from decimal import Decimal
from django.db import transaction as db_transaction
import uuid
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse
from django.views.decorators.csrf import csrf_exempt
import hmac
import hashlib
import json
import time
import csv
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils.decorators import method_decorator

from django.views.generic import TemplateView
from datetime import datetime, timezone as dt_timezone
from payments.utils import create_tripay_transaction
from django.db.models import F, Sum, Count,Value,DecimalField
from django.db.models.functions import Coalesce
from django.db import models 
from datetime import timedelta, date
from django.core.cache import cache
from django.db.models.functions import TruncDate
import logging
CACHE_TIMEOUT_AGGREGATES = 300   # 5 menit
CACHE_TIMEOUT_CHART = 300        # 5 menit

@login_required
@user_passes_test(lambda u: u.is_superuser or getattr(u, 'is_finance', False))
def finance_dashboard(request):
    # --- Aggregates (satu query) ---
    aggregates = cache.get('finance_aggregates_v1')
    if aggregates is None:
        aggregates = Payment.objects.filter(status='completed').aggregate(
            total_completed_transactions=Count('id'),
            total_revenue=Sum('amount'),
            total_partner_revenue=Sum('snapshot_partner_earning'),
            total_ice_revenue=Sum('snapshot_ice_earning'),
        )
        cache.set('finance_aggregates_v1', aggregates, CACHE_TIMEOUT_AGGREGATES)

    # safe defaults
    total_completed_transactions = aggregates.get('total_completed_transactions') or 0
    total_revenue = aggregates.get('total_revenue') or 0
    total_partner_revenue = aggregates.get('total_partner_revenue') or 0
    total_ice_revenue = aggregates.get('total_ice_revenue') or 0

    # --- Revenue chart (last 30 days) in single query using TruncDate ---
    chart_cache_key = 'finance_revenue_last30_v1'
    chart_data = cache.get(chart_cache_key)
    if chart_data is None:
        end_date = timezone.localdate()  # use localdate to match payment_date__date
        start_date = end_date - timedelta(days=29)  # 30 days including today
        qs = (
            Payment.objects
            .filter(status='completed', payment_date__date__gte=start_date)
            .annotate(day=TruncDate('payment_date'))
            .values('day')
            .annotate(total=Sum('amount'))
            .order_by('day')
        )
        # build map day -> total
        day_map = {r['day']: float(r['total'] or 0) for r in qs}
        labels = []
        data = []
        for i in range(29, -1, -1):  # from 29 days ago ... today
            d = end_date - timedelta(days=i)
            labels.append(d.strftime('%d %b'))
            data.append(day_map.get(d, 0.0))
        chart_data = {'labels': labels, 'data': data}
        cache.set(chart_cache_key, chart_data, CACHE_TIMEOUT_CHART)

    # --- Recent transactions (limited + select_related + only columns we need) ---
    recent_transactions = (
        Payment.objects
        .select_related('user', 'course', 'linked_transaction')
        .only(
            'id', 'amount', 'status', 'payment_date',
            'transaction_id', 'payment_method',
            'linked_transaction__transaction_id', 'linked_transaction__payment_method',
            'user__first_name', 'user__last_name', 'user__username',
            'course__course_name',
        )
        .order_by('-payment_date')[:10]
    )

    # --- Cart items: LIMIT! (don't fetch all) ---
    cart_items = (
        CartItem.objects
        .select_related('user', 'course')
        .order_by('-added_at')[:50]
    )

    context = {
        'total_completed_transactions': total_completed_transactions,
        'total_revenue': total_revenue,
        'total_partner_revenue': total_partner_revenue,
        'total_ice_revenue': total_ice_revenue,
        'revenue_chart': chart_data,
        'recent_transactions': recent_transactions,
        'cart_items': cart_items,
    }
    return render(request, 'finance/dashboard.html', context)


@login_required
@user_passes_test(lambda u: u.is_superuser or getattr(u, 'is_finance', False))
def export_finance_csv(request):
    # Buat response CSV
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="finance_export.csv"'

    writer = csv.writer(response)
    # Header CSV
    writer.writerow([
        'Transaction ID', 'User', 'Course', 'Partner', 'Payment Model', 
        'Amount', 'Status', 'Payment Method', 'Created At'
    ])

    payments = Payment.objects.select_related('user', 'course__org_partner').all()

    for p in payments:
        writer.writerow([
            p.transaction_id or p.id,
            p.user.get_full_name() or p.user.username,
            p.course.course_name,
            p.course.org_partner.name,
            p.get_payment_model_display(),
            p.amount,
            p.get_status_display(),
            p.payment_method or '-',
            p.created_at.strftime('%Y-%m-%d %H:%M'),
        ])

    return response

@login_required
@user_passes_test(lambda u: u.is_superuser or getattr(u, 'is_finance', False))
def finance_data_export(request):
    # Ambil semua pembayaran atau filter sesuai kebutuhan
    payments = Payment.objects.select_related('user', 'course', 'linked_transaction').all()

    # Buat response CSV
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="finance_data_export.csv"'

    writer = csv.writer(response)
    
    # Header CSV
    writer.writerow([
        'Payment ID', 'Transaction ID', 'Merchant Ref', 'User', 'Email', 
        'Course Name', 'Course ID', 'Partner', 'Payment Model',
        'Amount', 'Status', 'Payment Method', 'Bank / VA', 'Created At', 'Updated At'
    ])

    # Isi CSV
    for p in payments:
        transaction = p.linked_transaction
        writer.writerow([
            p.id,
            transaction.transaction_id if transaction else '-',
            transaction.merchant_ref if transaction else '-',
            p.user.get_full_name() or p.user.username,
            p.user.email,
            p.course.course_name,
            p.course.id,
            p.course.org_partner.name.name if p.course.org_partner else '-',
            p.get_payment_model_display(),
            float(p.amount),
            p.get_status_display(),
            transaction.payment_method if transaction else '-',
            f"{transaction.bank_name} ({transaction.va_number})" if transaction else '-',
            p.created_at.strftime('%Y-%m-%d %H:%M'),
            p.updated_at.strftime('%Y-%m-%d %H:%M'),
        ])

    return response


@csrf_exempt
def tripay_webhook(request):
    if request.method != 'POST':
        return HttpResponseBadRequest('Invalid method')

    raw_body = request.body

    # Pastikan header signature sesuai dengan header Tripay yang kamu dapat
    signature_header = request.headers.get('X-Callback-Signature')
    if not signature_header:
        return HttpResponseBadRequest('Missing signature header')

    computed_signature = hmac.new(
        key=settings.TRIPAY_PRIVATE_KEY.encode('latin-1'),
        msg=raw_body,
        digestmod=hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(computed_signature, signature_header):
        return HttpResponseBadRequest('Invalid signature')

    try:
        data = json.loads(raw_body)
    except json.JSONDecodeError:
        return HttpResponseBadRequest('Invalid JSON payload')

    merchant_ref = data.get('merchant_ref')
    status = data.get('status')

    if not merchant_ref or not status:
        return HttpResponseBadRequest('Missing required fields')

    try:
        transaction = Transaction.objects.get(merchant_ref=merchant_ref)
    except Transaction.DoesNotExist:
        return HttpResponseBadRequest('Transaction not found')

    status_map = {
        'PAID': 'completed',
        'EXPIRED': 'cancelled',
        'FAILED': 'failed',
    }

    mapped_status = status_map.get(status.upper(), 'pending')
    transaction.status = mapped_status
    transaction.save()

    # Update semua Payment terkait
    payments = transaction.payments.all()
    payments.update(status=mapped_status)

    # Jalankan method status spesifik jika perlu
    if mapped_status == 'completed':
        cart_items = []
        for course in transaction.courses.all():
            price_obj = course.get_course_price()  # Ambil sekali saja
            if not price_obj:
                continue  # Skip jika harga tidak tersedia

            dummy_item = type('DummyCartItem', (object,), {
                'course_name': course.course_name,
                'get_course_price': price_obj  # Simpan objek harga langsung
            })()
            cart_items.append(dummy_item)

        for payment in payments:
            payment.mark_completed()
        
        send_payment_confirmation_email(transaction.user, transaction, cart_items)

    elif mapped_status in ['failed', 'cancelled']:
        for payment in payments:
            payment.mark_failed()
    else:
        for payment in payments:
            payment.save()
    
    return JsonResponse({'success': True})

@login_required
def payment_return(request):
    

    return render(request, 'payments/return.html')


@login_required

def payment_detail_view(request, pk):
    user = request.user
    payment = get_object_or_404(
        Payment.objects.select_related(
            'user',
            'course__org_partner__name',
            'linked_transaction'
        ),
        pk=pk
    )

    transaction = payment.linked_transaction  # bisa None kalau belum ada
     # === 🔒 Access Validation ===
    # Finance & Superuser bisa akses semua
    if user.is_superuser or getattr(user, 'is_finance', False):
        has_access = True
    # Partner hanya boleh akses payment yang terkait kursus partner-nya sendiri
    elif getattr(user, 'is_partner', False):
        course_partner_user = getattr(payment.course.org_partner, 'user', None)
        has_access = course_partner_user == user
    else:
        has_access = False

    if not has_access:
        messages.error(request, "Access denied. You do not have permission to view this payment.")
        return redirect('authentication:home')
    # 🧮 Hitung total semua payment yang terhubung ke transaksi
    total_course_amount = Decimal('0.00')
    total_amount = payment.amount  # default

    if transaction:
        # Jumlahkan semua payment dalam transaksi
        payments = transaction.payments.all()
        total_course_amount = sum(p.amount for p in payments)

        # Hitung total final (kursus + fee - voucher)
        total_amount = (
            total_course_amount
            + (transaction.platform_fee or Decimal('0.00'))
            - (transaction.voucher or Decimal('0.00'))
        )

    context = {
        'payment': payment,
        'transaction': transaction,
        'total_course_amount': total_course_amount,
        'total_amount': total_amount,
    }

    return render(request, 'payments/payment_detail.html', context)


@login_required
@user_passes_test(lambda u: u.is_superuser or getattr(u, 'is_partner', False) or getattr(u, 'is_finance', False))
def transaction_report_view(request):
    payments = Payment.objects.select_related('user', 'course__org_partner')

    if getattr(request.user, 'is_partner', False):
        payments = payments.filter(course__org_partner__user=request.user)

    # Filters
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    if start_date:
        payments = payments.filter(created_at__date__gte=start_date)
    if end_date:
        payments = payments.filter(created_at__date__lte=end_date)

    search = request.GET.get('search', '').strip()
    if search:
        payments = payments.filter(linked_transaction__id__icontains=search)

    paginator = Paginator(payments.order_by('-created_at'), 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'finance/transaction_report.html', {'page_obj': page_obj})




@login_required
@user_passes_test(lambda u: u.is_superuser or getattr(u, 'is_finance', False) or getattr(u, 'is_partner', False))
def invoice_receipt_view(request):
    payments = Payment.objects.select_related('user', 'course', 'course__org_partner')

    if getattr(request.user, 'is_partner', False):
        payments = payments.filter(course__org_partner__user=request.user)

    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    if start_date:
        payments = payments.filter(payment_date__date__gte=start_date)
    if end_date:
        payments = payments.filter(payment_date__date__lte=end_date)

    status = request.GET.get('status')
    if status:
        payments = payments.filter(status=status)

    paginator = Paginator(payments.order_by('-payment_date'), 10)  # 10 per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    print(f"Total payments: {payments.count()}, Page size: {len(page_obj)}")  # Debug print

    current = page_obj.number
    total = paginator.num_pages
    start = max(current - 2, 1)
    end = min(current + 2, total) + 1
    page_range = range(start, end)

    context = {
        'page_obj': page_obj,
        'page_range': page_range,
    }
    return render(request, 'finance/invoice_receipt.html', context)






@login_required
@user_passes_test(lambda u: u.is_superuser or getattr(u, 'is_finance', False) or getattr(u, 'is_partner', False))
def partner_commission_view(request):
    user = request.user
    
    # Skip missing fields check untuk superuser/finance
    if not (user.is_superuser or getattr(user, 'is_finance', False)):
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
    
    # Debug print (hapus setelah test)
    print(f"DEBUG: User {user.username} - is_superuser: {user.is_superuser}, is_finance: {getattr(user, 'is_finance', False)}")
    
    payments = Payment.objects.select_related('user', 'course__org_partner').all()

    # Filter berdasarkan role
    if getattr(request.user, 'is_partner', False):
        payments = payments.filter(course__org_partner__user=request.user)
        partner_id = None
    else:
        try:
            partner_id = int(request.GET.get('partner_id')) if request.GET.get('partner_id') else None
        except ValueError:
            partner_id = None
        if partner_id:
            payments = payments.filter(course__org_partner__id=partner_id)

    # Filter tanggal
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    if start_date:
        payments = payments.filter(created_at__date__gte=start_date)
    if end_date:
        payments = payments.filter(created_at__date__lte=end_date)

    # Filter berdasarkan ID Transaksi
    search_query = request.GET.get('search', '').strip()
    if search_query.isdigit():
        payments = payments.filter(linked_transaction__id=search_query)

    # Ringkasan
    summary = payments.values('payment_model', 'status').annotate(
        total_amount=Sum('amount'),
        count=Count('id')
    ).order_by('payment_model', 'status')

    # Pendapatan kotor (total yang dibayar user)
    total_paid = payments.filter(status='completed').aggregate(
        total=Sum('amount')
    )['total'] or 0

    # Pendapatan bersih untuk Partner & ICE Admin
    net_income_partner = payments.filter(status='completed').aggregate(
        total=Sum('snapshot_partner_earning')
    )['total'] or 0

    net_income_admin = payments.filter(status='completed').aggregate(
        total=Sum('snapshot_ice_earning')
    )['total'] or 0

    partner_courses = None
    if request.user.is_superuser or getattr(request.user, 'is_finance', False):
        partner_courses = (
            Course.objects.values(
                'id', 'course_name', 'org_partner__name__name'
            )
            .annotate(
                total_amount=Coalesce(
                    Sum('payments__amount', filter=Q(payments__status='completed')),
                    Value(0, output_field=DecimalField()),
                    output_field=DecimalField()
                )
            )
            .filter(total_amount__gt=0)  # hanya course yang punya pembayaran completed
        )

        if partner_id:
            partner_courses = partner_courses.filter(org_partner__id=partner_id)

    # Pagination
    paginator = Paginator(payments.order_by('-created_at'), 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Buat querystring tanpa parameter "page"
    get_params = request.GET.copy()
    if 'page' in get_params:
        del get_params['page']
    querystring = get_params.urlencode()

    context = {
        'summary': summary,
        'total_paid': total_paid,
        'net_income_partner': net_income_partner,
        'net_income_admin': net_income_admin,
        'page_obj': page_obj,
        'partners': Partner.objects.all() if request.user.is_superuser or getattr(request.user, 'is_finance', False) else None,  # Fix: tambah is_finance
        'partner_courses': partner_courses,
        'search_query': search_query,
        'querystring': querystring,
    }
    
    return render(request, 'finance/partner_commission.html', context)





@login_required
@user_passes_test(lambda u: u.is_superuser or getattr(u, 'is_finance', False))
def financial_export_view(request):
    payments = Payment.objects.filter(status='completed')

    if 'export' in request.GET:
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="financial_report.csv"'
        writer = csv.writer(response)
        writer.writerow(['Transaction ID', 'User', 'Course', 'Amount', 'Date'])
        for p in payments:
            writer.writerow([p.id, p.user.username, p.course.course_name, p.amount, p.created_at])
        return response

    return render(request, 'finance/financial_export.html')



@login_required
@user_passes_test(lambda u: u.is_superuser or getattr(u, 'is_finance', False) or getattr(u, 'is_partner', False))
def invoice_receipt_view(request):
    payments = Payment.objects.select_related('user', 'course', 'course__org_partner')

    # Filter berdasarkan role partner
    if getattr(request.user, 'is_partner', False):
        payments = payments.filter(course__org_partner__user=request.user)

    # Filter tanggal
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    if start_date:
        payments = payments.filter(payment_date__date__gte=start_date)
    if end_date:
        payments = payments.filter(payment_date__date__lte=end_date)

    # Filter status
    status = request.GET.get('status')
    if status:
        payments = payments.filter(status=status)

    # Pagination
    paginator = Paginator(payments.order_by('-payment_date'), 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'page_obj': page_obj,
    }
    return render(request, 'finance/invoice_receipt.html', context)


logger = logging.getLogger(__name__)
def process_payment(request, course_id, payment_type='enrollment'):
    from decimal import Decimal
    course = get_object_or_404(Course, id=course_id)
    logger.info(f"Processing payment for course {course_id}, payment_type: {payment_type}")

    # Petakan payment_type ke payment_model
    payment_model_map = {
        'enrollment': 'buy first',
        'exam': 'pay for exam',
        'certificate': 'pay for certificate'
    }
    payment_model = payment_model_map.get(payment_type, 'buy first')

    # Validasi payment_type
    if payment_type not in ['enrollment', 'exam', 'certificate']:
        messages.error(request, "Invalid payment type.")
        return redirect('courses:course_lms_detail', id=course.id, slug=course.slug)

    if payment_type in ['exam', 'certificate']:
        CartItem.objects.get_or_create(
            user=request.user,
            course=course,
            defaults={'added_at': timezone.now()}
        )
        messages.info(request, f"{course.course_name} telah ditambahkan ke keranjang. Silakan lanjutkan pembayaran melalui checkout.")
        return redirect('payments:view_cart')

    # Sudah pernah bayar
    if Payment.objects.filter(
        user=request.user,
        course=course,
        payment_model=payment_model,
        status='completed'
    ).exists():
        messages.info(request, f"Payment for {payment_type} already completed.")
        if payment_type == 'exam':
            return redirect('learner:course_learn', username=request.user.username, id=course.id, slug=course.slug)
        elif payment_type == 'certificate':
            return redirect('courses:claim_certificate', course_id=course.id)
        return redirect('courses:course_lms_detail', id=course.id, slug=course.slug)

    # Ambil harga
    course_price = CoursePrice.objects.filter(course=course, price_type__name=course.payment_model).first()
    if not course_price:
        messages.error(request, "Price not available for this course.")
        return redirect('courses:course_lms_detail', id=course.id, slug=course.slug)

    # Ambil global platform fee dan voucher
    platform_fee_obj = CalculateAdminPrice.objects.filter(name__iexact="Platform Fee").first()
    voucher_obj = CalculateAdminPrice.objects.filter(name__iexact="Voucher").first()
    platform_fee = platform_fee_obj.amount if platform_fee_obj else Decimal("0.00")
    voucher = voucher_obj.amount if voucher_obj else Decimal("0.00")

    # Hitung total bayar user
    total_payment = course_price.portal_price + platform_fee - voucher

    # Buat atau update Payment
    payment = Payment.objects.filter(
        user=request.user,
        course=course,
        payment_model=payment_model,
        status__in=['pending', 'failed']
    ).first()

    if payment:
        payment.amount = course_price.portal_price
        payment.status = 'pending'
        payment.course_price = course_price
        payment.snapshot_price = course_price.normal_price
        payment.snapshot_discount = course_price.discount_amount
        payment.snapshot_tax = course_price.tax
        payment.snapshot_ppn = course_price.ppn
        payment.snapshot_user_payment = course_price.portal_price
        payment.snapshot_partner_earning = course_price.partner_earning
        payment.snapshot_ice_earning = course_price.ice_earning
        payment.snapshot_platform_fee = platform_fee
        payment.snapshot_voucher = voucher
        payment.save()
    else:
        payment = Payment.objects.create(
            user=request.user,
            course=course,
            payment_model=payment_model,
            amount=course_price.portal_price,
            status='pending',
            course_price=course_price,
            snapshot_price=course_price.normal_price,
            snapshot_discount=course_price.discount_amount,
            snapshot_tax=course_price.tax,
            snapshot_ppn=course_price.ppn,
            snapshot_user_payment=course_price.portal_price,
            snapshot_partner_earning=course_price.partner_earning,
            snapshot_ice_earning=course_price.ice_earning,
            snapshot_platform_fee=platform_fee,
            snapshot_voucher=voucher
        )

    # Buat atau update Transaction
    transaction = None
    if payment.linked_transaction:
        transaction = payment.linked_transaction

    if not transaction:
        transaction = Transaction.objects.create(
            user=request.user,
            total_amount=total_payment,
            platform_fee=platform_fee,
            voucher=voucher,
            status='pending',
            description=f"Payment for {payment_type} in course {course.course_name}"
        )
        transaction.courses.add(course)
        payment.linked_transaction = transaction
        payment.save()

    return render(request, 'payments/payment_page.html', {
        'course': course,
        'payment': payment,
        'transaction': transaction,
        'payment_type': payment_type
    })


@login_required
@require_POST
def add_to_cart(request, course_id):
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)
    course = get_object_or_404(Course, id=course_id)

    # Cegah jika course gratis, langsung arahkan ke enroll
    if course.payment_model == 'free':
        messages.info(request, "This course is free, please register directly.")
        return redirect('courses:enroll', course_id=course.id)

    # Cek apakah sudah ada di cart
    cart_item, created = CartItem.objects.get_or_create(
        user=request.user,
        course=course,
        defaults={'added_at': now()}
    )

    if created:
        messages.success(request, f"{course.course_name} has been successfully added to your cart.")
    else:
        messages.info(request, f"{course.course_name} is already in your cart.")

    return redirect('payments:view_cart')  # pastikan URL ini ada



@login_required
def view_cart(request):
    cart_items = CartItem.objects.select_related('course').filter(user=request.user)

    platform_fee_obj = CalculateAdminPrice.objects.filter(name__iexact="Platform Fee").first()
    voucher_obj = CalculateAdminPrice.objects.filter(name__iexact="Voucher").first()
    platform_fee = platform_fee_obj.amount if platform_fee_obj else Decimal("0.00")
    voucher = voucher_obj.amount if voucher_obj else Decimal("0.00")

    sub_total = Decimal('0.00')

    # Attach harga ke setiap cart item
    for item in cart_items:
        course_price = item.course.get_course_price()
        if course_price:
            item.course_price_portal_price = course_price.portal_price
            sub_total += course_price.portal_price
        else:
            item.course_price_portal_price = Decimal('0.00')

    total_price = sub_total + platform_fee - voucher

    context = {
        'cart_items': cart_items,
        'sub_total': sub_total,
        'platform_fee': platform_fee,
        'voucher': voucher,
        'total_price': total_price,
    }
    return render(request, 'payments/cart.html', context)






@login_required
def checkout(request):
    expire_limit = timezone.now() - timezone.timedelta(hours=1)

    pending_tx = Transaction.objects.filter(
        user=request.user,
        status='pending',
        created_at__gte=expire_limit
    ).prefetch_related('courses').order_by('-created_at').first()

    # =========================
    # ✅ RESUME FLOW
    # =========================
    if pending_tx:
        cart_items = []
        total_course_price = Decimal('0.00')

        for course in pending_tx.courses.all():
            price = course.get_course_price()
            if not price:
                continue

            cart_items.append(SimpleNamespace(
                course=course,
                price=price
            ))

            total_course_price += price.portal_price

        context = {
            'cart_items': cart_items,
            'total_course_price': total_course_price,
            'platform_fee': pending_tx.platform_fee,
            'voucher': pending_tx.voucher,
            'voucher_code': '',
            'total_price': pending_tx.total_amount,
            'payment_channels': get_tripay_payment_channels(),
            'bank_name': pending_tx.bank_name,
            'va_number': pending_tx.va_number,
            'payment_url': pending_tx.payment_url,
            'selected_payment_method': pending_tx.payment_method,
            'merchant_ref': pending_tx.merchant_ref,
            'instructions': pending_tx.instructions,
            'expired_at': pending_tx.expired_at,
            'is_resume': True,
        }

        messages.info(request, "Anda memiliki transaksi pending.")
        return render(request, 'payments/checkout.html', context)

    # =========================
    # ✅ NORMAL FLOW
    # =========================
    cart_items_qs = CartItem.objects.select_related('course').filter(user=request.user)

    if not cart_items_qs.exists():
        messages.info(request, "Keranjang kamu kosong.")
        return redirect('payments:view_cart')

    cart_items = []
    total_course_price = Decimal('0.00')

    for item in cart_items_qs:
        price = item.course.get_course_price()
        if not price:
            continue

        cart_items.append(SimpleNamespace(
            course=item.course,
            price=price
        ))

        total_course_price += price.portal_price

    PLATFORM_FEE = Decimal('5000.00')

    voucher_code = request.GET.get('voucher') or request.POST.get('voucher')
    voucher_amount = Decimal('0.00')
    voucher_obj = None

    if voucher_code:
        voucher_obj, error_msg = validate_voucher(voucher_code, request.user)
        if error_msg:
            messages.warning(request, error_msg)
            return redirect('payments:checkout')

        if VoucherUsage.objects.filter(user=request.user, voucher=voucher_obj).exists():
            messages.warning(request, "Voucher sudah pernah digunakan.")
            return redirect('payments:checkout')

        voucher_amount = min(voucher_obj.amount, total_course_price + PLATFORM_FEE)

    total_price = max(total_course_price + PLATFORM_FEE - voucher_amount, Decimal('0.00'))

    if request.method == 'POST' and 'checkout' in request.POST:
        payment_method = request.POST.get('payment_method')

        if not payment_method:
            messages.error(request, "Pilih metode pembayaran.")
            return redirect('payments:checkout')

        with db_transaction.atomic():
            merchant_ref = f"user-{request.user.id}-{int(time.time())}"

            transaction = Transaction.objects.create(
                user=request.user,
                total_amount=total_price,
                status='pending',
                platform_fee=PLATFORM_FEE,
                voucher=voucher_amount,
                merchant_ref=merchant_ref
            )

            for item in cart_items:
                price = item.price

                Payment.objects.create(
                    user=request.user,
                    course=item.course,
                    amount=price.portal_price,
                    linked_transaction=transaction,
                    status='pending',
                )

                transaction.courses.add(item.course)

            if voucher_obj:
                VoucherUsage.objects.create(user=request.user, voucher=voucher_obj)

            cart_items_qs.delete()

            try:
                va_number, bank_name, payment_url, trx_id, instructions, exp_time = create_tripay_transaction(
                    transaction, payment_method, request.user
                )

                transaction.va_number = va_number
                transaction.bank_name = bank_name
                transaction.payment_url = payment_url
                transaction.transaction_id = trx_id
                transaction.instructions = instructions
                transaction.expired_at = datetime.fromtimestamp(exp_time).replace(tzinfo=dt_timezone.utc)

                transaction.save()

                return redirect('payments:transaction_detail', merchant_ref=merchant_ref)

            except Exception as e:
                transaction.status = 'failed'
                transaction.save()

                messages.error(request, str(e))
                return redirect('payments:checkout')

    context = {
        'cart_items': cart_items,
        'total_course_price': total_course_price,
        'platform_fee': PLATFORM_FEE,
        'voucher': voucher_amount,
        'voucher_code': voucher_code,
        'total_price': total_price,
        'payment_channels': get_tripay_payment_channels(),
        'bank_name': '',
        'va_number': '',
        'payment_url': '',
        'selected_payment_method': '',
        'merchant_ref': '',
        'instructions': [],
        'expired_at': None,
        'is_resume': False,
    }

    return render(request, 'payments/checkout.html', context)

@login_required

def cek_transaction_detail(request, pk):
    user = request.user
    # Ambil transaksi berdasarkan PK (tanpa filter user)
    transaction = get_object_or_404(
        Transaction.objects.prefetch_related('courses__org_partner'),
        pk=pk
    )
    # === 🔒 Access Validation ===
    if user.is_superuser or getattr(user, 'is_finance', False):
        has_access = True
    elif getattr(user, 'is_partner', False):
        # Cek apakah ada setidaknya 1 kursus dalam transaksi milik partner user
        partner_courses = transaction.courses.filter(org_partner__user=user)
        has_access = partner_courses.exists()
    else:
        has_access = False

    if not has_access:
        messages.error(request, "Access denied. You do not have permission to view this transaction.")
        return redirect('authentication:home')
    # Ambil unique partners
    partners = transaction.courses.values_list('org_partner', flat=True).distinct()
    partner = None
    if partners:
        partner = Partner.objects.get(id=partners[0])
    # ✅ Hitung total pembayaran real-time dari snapshot Payment
    course_total = transaction.payments.aggregate(total=models.Sum('amount'))['total'] or 0
    total_paid = course_total + (transaction.platform_fee or 0)

    if request.GET.get('download') == 'pdf':
        logger.info(f"[ADMIN] Generating PDF for transaction {pk} (status: {transaction.status})")
        
        html_string = render_to_string('payments/invoice_pdf.html', {
            'transaction': transaction,
            'partner': partner,
            'request': request,
            'course_total': course_total,
            'admin_view': True,  # Bisa digunakan di template kalau mau tampilkan info tambahan
        })
        html = HTML(string=html_string, base_url=request.build_absolute_uri())
        pdf = html.write_pdf()

        invoice_number = f"INV{transaction.created_at.strftime('%Y%m%d')}{transaction.id}"
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{invoice_number}.pdf"'
        return response
    
    return render(request, 'payments/admin_transaction_detail.html', {
        'transaction': transaction,
        'partner': partner,
        'total_paid': total_paid,
        'course_total': course_total,
    })

@login_required
def cart_item_delete(request, pk):
    if not request.user.is_authenticated:
        return redirect("/login/?next=%s" % request.path)
    item = get_object_or_404(CartItem, pk=pk, user=request.user)
    item.delete()
    messages.success(request, 'The item was successfully removed from the cart.')
    return redirect('payments:view_cart')

@login_required
def transaction_history(request):
    user = request.user

    # Validasi data diri wajib
    required_fields = {
        'first_name': 'First Name',
        'last_name': 'Last Name',
        'email': 'Email',
        'phone': 'Phone Number',
        'gender': 'Gender',
        'birth': 'Date of Birth',
    }

    missing_fields = [
        label for field, label in required_fields.items()
        if not getattr(user, field, None)
        or (isinstance(getattr(user, field), str) and not getattr(user, field).strip())
    ]

    if missing_fields:
        messages.warning(
            request,
            f"Please complete your profile before accessing microcredentials: {', '.join(missing_fields)}"
        )
        return redirect('authentication:edit-profile', pk=user.pk)
    
    # 1️⃣ Update status pending yang sudah kadaluarsa → Ubah ke 'cancelled' untuk konsistensi
    expire_limit = timezone.now() - timedelta(hours=1)
    Payment.objects.filter(status='pending', created_at__lt=expire_limit).update(status='cancelled')
    Transaction.objects.filter(status='pending', created_at__lt=expire_limit).update(status='cancelled')

    # 2️⃣ Ambil filter status → Ubah 'paid' ke 'completed', dan 'expired' ke 'cancelled'
    status_filter = request.GET.get('status', 'all')
    VALID_STATUSES = ['completed', 'pending', 'failed', 'cancelled']  # Konsisten dengan webhook

    # 3️⃣ Ambil transaksi user
    transactions = Transaction.objects.filter(user=request.user)
    if status_filter in VALID_STATUSES:
        transactions = transactions.filter(status=status_filter)
    elif status_filter != 'all':
        messages.warning(request, "Status filter tidak dikenali. Menampilkan semua transaksi.")
        status_filter = 'all'

    # 4️⃣ Hitung total → Ubah 'paid' ke 'completed'
    total_completed = transactions.filter(status='completed').aggregate(total=Sum('total_amount'))['total'] or 0
    total_pending = transactions.filter(status='pending').aggregate(total=Sum('total_amount'))['total'] or 0

    context = {
        'transactions': transactions.order_by('-created_at'),
        'total_transactions': transactions.count(),
        'total_completed': total_completed,  # Ubah nama variabel untuk clarity
        'total_pending': total_pending,
        'selected_status': status_filter,
    }
    return render(request, 'payments/transaction_history.html', context)



@login_required
def transaction_detail(request, merchant_ref):
    trx = get_object_or_404(Transaction.objects.select_related('user'), merchant_ref=merchant_ref, user=request.user)

    # Ambil instruksi pembayaran (kalau disimpan dalam JSONField)
    try:
        instructions = json.loads(trx.instructions_json) if trx.instructions_json else []
    except (ValueError, TypeError):
        instructions = []

    context = {
        'merchant_ref': trx.merchant_ref,
        'bank_name': trx.bank_name or '-',
        'selected_payment_method': trx.payment_method or '-',
        'expired_at': trx.expired_at,
        'total_price': trx.total_amount,
        'va_number': trx.va_number,
        'payment_url': trx.payment_url,
        'platform_fee': trx.platform_fee or 0,
        'voucher': getattr(trx, 'voucher', 0) or 0,
        'instructions': instructions,
        'cart_items': trx.courses.all(),
    }

    return render(request, 'payments/transaction_detail.html', context)




#untuk user mengunduh invoice pdf
@login_required
def transaction_invoice_detail(request, pk):
    transaction = get_object_or_404(
        Transaction.objects.prefetch_related('courses__org_partner'),
        pk=pk,
        user=request.user
    )

    # ✅ Validasi status: Hanya izinkan untuk 'completed' (konsisten dengan webhook & history)
    if transaction.status != 'completed':
        messages.warning(
            request,
            f"Invoice hanya tersedia untuk transaksi yang sudah completed. Status saat ini: {transaction.status.title()}."
        )
        return redirect('payments:transaction_history')  # Atau halaman history

    # Ambil unique partners (handle multiple courses/partners)
    partners = transaction.courses.values_list('org_partner', flat=True).distinct()
    partner = None
    if partners:
        partner = Partner.objects.get(id=partners[0])  # Atau loop kalau multiple, tapi untuk sekarang ambil first

    if request.GET.get('download') == 'pdf':
        # Tambah logger untuk debug
        logger.info(f"Generating PDF for transaction {pk} (status: {transaction.status})")
        
        html_string = render_to_string('payments/invoice_pdf.html', {
            'transaction': transaction,
            'partner': partner,
            'request': request,
        })
        html = HTML(string=html_string, base_url=request.build_absolute_uri())
        pdf = html.write_pdf()

        invoice_number = f"INV{transaction.created_at.strftime('%Y%m%d')}{transaction.id}"
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{invoice_number}.pdf"'
        return response

    return render(request, 'payments/invoice_detail.html', {
        'transaction': transaction,
        'partner': partner,
    })



@method_decorator(
    [login_required,
     user_passes_test(lambda u: u.is_superuser or getattr(u, 'is_finance', False) or getattr(u, 'is_partner', False))],
    name='dispatch'
)
class CoursePaymentDetailView(TemplateView):
    template_name = 'payments/report_per_course_detail.html'

    def get_context_data(self, course_id=None, **kwargs):
        context = super().get_context_data(**kwargs)
        course = get_object_or_404(Course, id=course_id)

        payments = Payment.objects.filter(course=course, status='completed').select_related('user')

        context.update({
            'course': course,
            'payments': payments,
            'summary': payments.aggregate(
                total_transaksi=Count('id'),
                total_amount=Sum('amount'),
                total_voucher=Sum('snapshot_voucher'),
                total_partner=Sum('snapshot_partner_earning'),
                total_ice=Sum('snapshot_ice_earning'),
                total_platform_fee=Sum('snapshot_platform_fee'),
            )
        })
        return context

@method_decorator(
    [login_required,
     user_passes_test(lambda u: u.is_superuser or getattr(u, 'is_finance', False) or getattr(u, 'is_partner', False))],
    name='dispatch'
)
class CoursePaymentReportView(TemplateView):
    template_name = 'payments/report_per_course.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Data utama per course
        report = (
            Payment.objects
            .filter(status='completed')
            .values('course__id', 'course__course_name')
            .annotate(
                total_transaksi=Count('id'),
                total_amount=Sum('amount'),
                total_voucher=Sum('snapshot_voucher'),
                total_partner=Sum('snapshot_partner_earning'),
                total_ice=Sum('snapshot_ice_earning'),
                total_platform_fee=Sum('snapshot_platform_fee'),
            )
            .order_by('-total_amount')
        )

        # 🔹 Hitung total keseluruhan untuk summary footer
        summary = {
            'total_transaksi': sum([r['total_transaksi'] or 0 for r in report]),
            'total_amount': sum([r['total_amount'] or 0 for r in report]),
            'total_voucher': sum([r['total_voucher'] or 0 for r in report]),
            'total_partner': sum([r['total_partner'] or 0 for r in report]),
            'total_ice': sum([r['total_ice'] or 0 for r in report]),
            'total_platform_fee': sum([r['total_platform_fee'] or 0 for r in report]),
        }

        context['report'] = report
        context['summary'] = summary
        return context
