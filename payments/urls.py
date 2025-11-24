from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    path('add-to-cart/<int:course_id>/course', views.add_to_cart, name='add_to_cart'),
    path('cart/', views.view_cart, name='view_cart'),  # contoh tampilan cart
    path('checkout/', views.checkout, name='checkout'),
    path('cart/delete/<int:pk>/', views.cart_item_delete, name='cart_item_delete'),
    path('transactions/', views.transaction_history, name='transaction_history'),
    path('transactions/<int:pk>/invoice/detail', views.transaction_invoice_detail, name='transaction_invoice_detail'),
    path('course/<int:course_id>/payment/<str:payment_type>/', views.process_payment, name='process_payment'),
    path('transactions/process_payment/', views.transaction_report_view, name='payment_report'),
    path('invoices/', views.invoice_receipt_view, name='invoice_receipt'),
    path('commissions/', views.partner_commission_view, name='partner_commission'),
    path('export/', views.financial_export_view, name='financial_export'),
    path('transaction/<int:pk>/user', views.cek_transaction_detail, name='cek_transaction_detail'),

    path('report/<int:pk>/detail', views.payment_detail_view, name='payment_detail'),
    path('payments/tripay-callback/', views.tripay_webhook, name='tripay_webhook'),
    path('payments/return/', views.payment_return, name='payment_return'),
    path('finance/export/', views.finance_data_export, name='finance_data_export'),
    path('dashboard/finance', views.finance_dashboard, name='dashboard'),
    path('export-csv/', views.export_finance_csv, name='export_csv'),
    path('transaction/<str:merchant_ref>/', views.transaction_detail, name='transaction_detail'),
    path('reports/per-course/', views.CoursePaymentReportView.as_view(), name='report_per_course'),
    path('reports/per-course/<int:course_id>/', views.CoursePaymentDetailView.as_view(), name='report_per_course_detail'),
    
]