from django import forms
import os
from captcha.fields import CaptchaField
import logging
import unicodedata
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm, PasswordResetForm, SetPasswordForm,UserChangeForm
from authentication.models import CustomUser, Universiti
import re
from .models import CustomUser
from django.core.exceptions import ValidationError

from django.core.files.uploadedfile import UploadedFile
from django.core.mail import EmailMultiAlternatives
from django.template import loader
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.shortcuts import get_current_site
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from PIL import Image
from io import BytesIO
from django.core.files.uploadedfile import InMemoryUploadedFile
import sys
#import imghdr
from PIL import Image
from django.core.exceptions import ValidationError
logger = logging.getLogger("django.contrib.auth")


from courses.models import Comment

class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['content']  # Hanya isi content saja
        widgets = {
            'content': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Write your reply here...',
                'class': 'form-control',  # Bootstrap styling misalnya
                'style': 'resize:none;',   # Non-resizable textarea
                'maxlength': '500',        # Maksimal karakter (optional)
            }),
        }

def _unicode_ci_compare(s1, s2):
    """
    Perform case-insensitive comparison of two identifiers, using the
    recommended algorithm from Unicode Technical Report 36, section
    2.11.2(B)(2).
    """
    return (
        unicodedata.normalize("NFKC", s1).casefold()
        == unicodedata.normalize("NFKC", s2).casefold()
    )

class RegistrationForm(forms.ModelForm):
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500',
            'placeholder': 'Enter your password'
        })
    )
    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500',
            'placeholder': 'Confirm your password'
        })
    )
    captcha = CaptchaField()  # widget default sudah oke

    class Meta:
        model = CustomUser
        fields = ['email', 'username', 'password1', 'password2', 'captcha']

        widgets = {
            'email': forms.EmailInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500',
                'placeholder': 'Enter your email'
            }),
            'username': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500',
                'placeholder': 'Enter your username'
            }),
        }


    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 != password2:
            raise ValidationError("Passwords don't match.")
        return password2

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['captcha'].widget.attrs.update({
            'placeholder': 'Solve the math problem'
        })

class LoginForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'placeholder': 'Enter your email',
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500'
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Enter your password',
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500'
        })
    )
    captcha = CaptchaField()  # Add the captcha field here

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['captcha'].widget.attrs.update({
            'placeholder': 'Solve the math problem'
        })


class PasswordResetForms(forms.Form):
    email = forms.EmailField(
        label=_("Email"),
        max_length=254,
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )
    captcha = CaptchaField()  # Add the captcha field here
    def send_mail(
        self,
        subject_template_name,
        email_template_name,
        context,
        from_email,
        to_email,
        html_email_template_name=None,
    ):
        """
        Send a django.core.mail.EmailMultiAlternatives to `to_email`.
        """
        subject = loader.render_to_string(subject_template_name, context)
        # Email subject *must not* contain newlines
        subject = "".join(subject.splitlines())
        body = loader.render_to_string(email_template_name, context)

        email_message = EmailMultiAlternatives(subject, body, from_email, [to_email])
        if html_email_template_name is not None:
            html_email = loader.render_to_string(html_email_template_name, context)
            email_message.attach_alternative(html_email, "text/html")

        try:
            email_message.send()
        except Exception:
            logger.exception(
                "Failed to send password reset email to %s", context["user"].pk
            )

    def get_users(self, email):
        """Given an email, return matching user(s) who should receive a reset.

        This allows subclasses to more easily customize the default policies
        that prevent inactive users and users with unusable passwords from
        resetting their password.
        """
        email_field_name = CustomUser.get_email_field_name()
        active_users = CustomUser._default_manager.filter(
            **{
                "%s__iexact" % email_field_name: email,
                "is_active": True,
            }
        )
        return (
            u
            for u in active_users
            if u.has_usable_password()
            and _unicode_ci_compare(email, getattr(u, email_field_name))
        )

    def save(
        self,
        domain_override=None,
        subject_template_name="registration/password_reset_subject.txt",
        email_template_name="registration/password_reset_email.html",
        use_https=False,
        token_generator=default_token_generator,
        from_email=None,
        request=None,
        html_email_template_name=None,
        extra_email_context=None,
    ):
        """
        Generate a one-use only link for resetting password and send it to the
        user.
        """
        email = self.cleaned_data["email"]
        if not domain_override:
            current_site = get_current_site(request)
            site_name = current_site.name
            domain = current_site.domain
        else:
            site_name = domain = domain_override
        email_field_name = CustomUser.get_email_field_name()
        for user in self.get_users(email):
            user_email = getattr(user, email_field_name)
            context = {
                "email": user_email,
                "domain": domain,
                "site_name": site_name,
                "uid": urlsafe_base64_encode(force_bytes(user.pk)),
                "user": user,
                "token": token_generator.make_token(user),
                "protocol": "https" if use_https else "http",
                **(extra_email_context or {}),
            }
            self.send_mail(
                subject_template_name,
                email_template_name,
                context,
                from_email,
                user_email,
                html_email_template_name=html_email_template_name,
            )



class UserProfileForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = [
            'first_name', 'last_name', 'email', 'phone', 'gender', 'birth',
            'country', 'photo', 'address', 'hobby', 'education', 'university',
            'tiktok', 'youtube', 'facebook', 'instagram', 'linkedin', 'twitter'
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500 transition',
                'required': True
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500 transition',
                'required': True
            }),
            'email': forms.EmailInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500 transition',
                'required': True,
                'readonly': True,
            }),
            'phone': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500 transition',
                'required': True
            }),
            'gender': forms.Select(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500 transition',
                'required': True
            }),
            'birth': forms.DateInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500 transition',
                'type': 'date',
                'required': True
            }),
            'country': forms.Select(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500 transition'
            }),
            'photo': forms.FileInput(attrs={
                'class': 'flex-1 px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500 transition',
                'accept': 'image/*'
            }),
            'address': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500 transition',
                'rows': 4
            }),
            'hobby': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500 transition'
            }),
            'education': forms.Select(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500 transition'
            }),
            'university': forms.Select(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500 transition'
            }),
            'tiktok': forms.URLInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500 transition',
                'placeholder': 'https://tiktok.com/...'
            }),
            'youtube': forms.URLInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500 transition',
                'placeholder': 'https://youtube.com/...'
            }),
            'facebook': forms.URLInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500 transition',
                'placeholder': 'https://facebook.com/...'
            }),
            'instagram': forms.URLInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500 transition',
                'placeholder': 'https://instagram.com/...'
            }),
            'linkedin': forms.URLInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500 transition',
                'placeholder': 'https://linkedin.com/in/...'
            }),
            'twitter': forms.URLInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500 transition',
                'placeholder': 'https://twitter.com/...'
            }),
        }
        labels = {
            'first_name': 'First Name',
            'last_name': 'Last Name',
            'email': 'Email',
            'phone': 'Phone Number',
            'gender': 'Gender',
            'birth': 'Date of Birth',
            'country': 'Country',
            'photo': 'Profile Photo',
            'address': 'Address',
            'hobby': 'Hobby',
            'education': 'Education',
            'university': 'University',
            'tiktok': 'TikTok',
            'youtube': 'YouTube',
            'facebook': 'Facebook',
            'instagram': 'Instagram',
            'linkedin': 'LinkedIn',
            'twitter': 'Twitter',
        }


    def clean_email(self):
        email = self.cleaned_data.get('email')
        if CustomUser.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Email ini sudah digunakan.")
        return email

    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if not phone:
            raise forms.ValidationError("Nomor telepon wajib diisi.")
        if not re.match(r'^\+?\d{8,15}$', phone):
            raise forms.ValidationError("Nomor telepon tidak valid.")
        return phone

    def clean_birth(self):
        birth = self.cleaned_data.get('birth')
        if not birth:
            raise forms.ValidationError("Tanggal lahir wajib diisi.")
        return birth

    def clean_gender(self):
        gender = self.cleaned_data.get('gender')
        if not gender:
            raise forms.ValidationError("Jenis kelamin wajib diisi.")
        return gender

    def clean(self):
        cleaned_data = super().clean()
        social_fields = ['tiktok', 'youtube', 'facebook', 'instagram', 'linkedin', 'twitter']
        for field in social_fields:
            url = cleaned_data.get(field)
            if url and not re.match(r'^https?://', url):
                self.add_error(field, "URL harus dimulai dengan http:// atau https://")
        return cleaned_data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)  # ✅ benar
        self.fields['photo'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Upload your photo',
            'required': True
        })
        # ✅ simpan foto lama untuk pengecekan
        self.old_photo = self.instance.photo

    def clean_photo(self):
        photo = self.cleaned_data.get('photo')

        if photo:
            if isinstance(photo, UploadedFile):
                content_type = photo.content_type
                # validate content_type here, e.g.:
                if content_type not in ['image/jpeg', 'image/png']:
                    raise forms.ValidationError("Unsupported file type.")
            # else, it's an existing ImageFieldFile, skip content_type check

        return photo

    def save(self, commit=True):
        user = super().save(commit=False)
        photo = self.cleaned_data.get('photo')

        if photo:
            # ✅ Hapus foto lama jika diganti
            if self.old_photo and self.old_photo != photo:
                try:
                    old_path = self.old_photo.path
                    if os.path.isfile(old_path):
                        os.remove(old_path)
                except Exception as e:
                    print(f"Gagal menghapus foto lama: {e}")

            # ✅ Proses WebP
            img = Image.open(photo)

            # Resize jika terlalu besar
            max_size = (300, 300)
            img.thumbnail(max_size)

            # Konversi ke WebP
            output = BytesIO()
            img.convert("RGB").save(output, format="WEBP", quality=85)
            output.seek(0)

            # Simpan file WebP
            filename = f"{photo.name.rsplit('.', 1)[0]}.webp"
            user.photo = InMemoryUploadedFile(
                output, 'ImageField', filename, 'image/webp',
                sys.getsizeof(output), None
            )

        if commit:
            user.save()
        return user


       
class UserPhoto(UserChangeForm):
    class Meta:
        model = CustomUser
        fields = ['photo']

    def __init__(self, *args, **kwargs):
        super(UserPhoto, self).__init__(*args, **kwargs)
        self.fields['photo'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Upload your photo',
            'required': True
        })

    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        if not photo:
            raise ValidationError("Foto wajib diunggah.")

        if photo.size > 100 * 1024:
            raise ValidationError("Ukuran file tidak boleh lebih dari 100KB.")

        # Validasi tipe file
        if not photo.content_type.startswith('image/'):
            raise ValidationError("Hanya file gambar yang diperbolehkan.")

        # Validasi format file (opsional, lebih ketat)
        try:
            img = Image.open(photo)
            if img.format.lower() not in ['jpeg', 'jpg', 'png', 'webp']:
                raise ValidationError("Format gambar tidak dikenali atau tidak didukung.")
        except Exception:
            raise ValidationError("File bukan gambar yang valid.")

        return photo