# licensing/forms.py
from django import forms
from .models import Invitation, License
from authentication.models import CustomUser
from django.core.exceptions import ValidationError

class InvitationForm(forms.Form):
    invitee_emails = forms.CharField(
        widget=forms.Textarea(attrs={
            'rows': 5,
            'class': 'w-full p-3 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
            'placeholder': 'Enter email addresses (one per line or separated by commas)'
        }),
        label="Invitee Emails",
        required=True
    )

class LicenseForm(forms.ModelForm):
    user_email = forms.EmailField(
        widget=forms.EmailInput(attrs={'placeholder': 'Masukkan email pemilik lisensi'}),
        required=True,
        label='Email Pemilik'
    )

    class Meta:
        model = License
        fields = [
            'name', 'license_type', 'start_date', 'expiry_date', 'status',
            'description', 'university', 'max_users', 'subscription_type',
            'subscription_frequency'
        ]
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 4}),
        }

    def clean_user_email(self):
        email = self.cleaned_data.get('user_email')
        try:
            user = CustomUser.objects.get(email=email)
            # Cek apakah user sudah punya lisensi lain sebagai owner
            if License.objects.filter(owner=user).exclude(pk=self.instance.pk).exists():
                raise ValidationError(f"Email {email} sudah digunakan sebagai pemilik lisensi lain.")
            return user
        except CustomUser.DoesNotExist:
            raise ValidationError(f"Email {email} tidak ditemukan.")

    def clean(self):
        cleaned_data = super().clean()
        max_users = cleaned_data.get('max_users')
        if max_users is not None and max_users < 1:
            raise ValidationError("Maksimum pengguna harus minimal 1.")
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        user = self.cleaned_data['user_email']
        instance.owner = user

        if commit:
            instance.save()
            # Tambahkan owner ke dalam daftar pengguna (jika belum ada)
            instance.users.add(user)
            user.is_subscription = True
            user.save()
        return instance
