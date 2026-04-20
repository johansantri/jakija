"""
URL configuration for mysite project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path,include
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponseForbidden

def blocked(request):
    return HttpResponseForbidden("Not allowed")

urlpatterns = [
    path('', include('authentication.urls')),
    path('', include('courses.urls', namespace='courses')),
    path('', include('notification.urls', namespace='notification')),
    path('', include('partner.urls', namespace='partner')),
    path('', include('instructor.urls', namespace='instructor')),
    path('', include('learner.urls', namespace='learner')),
    path('', include('blog.urls', namespace='blog')),
    path('', include('licensing.urls', namespace='licensing')),
    path('', include('payments.urls', namespace='payments')),
    path('', include("lti_consumer.urls", namespace="lti_consumer")),
    path('kuruk/', admin.site.urls),
    path('captcha/', include('captcha.urls')),

    #block
    path('accounts/login/', blocked),
    path('accounts/signup/', blocked),
    path('accounts/password/reset/', blocked),
    
    path('accounts/',include("allauth.urls")),
    path('select2/', include('django_select2.urls')),  # <- tambahkan ini
]+ static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += [
    path("ckeditor5/", include('django_ckeditor_5.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
