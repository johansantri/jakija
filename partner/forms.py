from django import forms
from django.core.exceptions import ValidationError
from courses.models import Partner, Universiti
from authentication.models import Universiti
from django_ckeditor_5.widgets import CKEditor5Widget
from PIL import Image
from io import BytesIO
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.core.exceptions import ValidationError

class PartnerRequestForm(forms.ModelForm):

    description = forms.CharField(
        widget=CKEditor5Widget(attrs={'class': 'django_ckeditor_5'}, config_name='default')  # <-- Tambah config_name dan class wajib
    )
    # Ubah ke ChoiceField biasa supaya bisa tambah 'other' tanpa error validasi model
    university_choice = forms.ChoiceField(
        choices=[],  # Akan diisi di __init__
        required=False,
        label="Universitas"
    )
    new_university_name = forms.CharField(
        label="Nama Universitas/org Baru",
        required=False,
        widget=forms.TextInput(attrs={'class': 'block w-full border border-gray-300 rounded-md px-3 py-2 shadow-sm focus:outline-none focus:ring-primary focus:border-primary'}),
        help_text="Isi jika universitas/org tidak ada di daftar."
    )

    class Meta:
        model = Partner
        fields = [
            'university_choice', 'new_university_name',
            'phone', 'address', 'description',
            'npwp', 'npwp_file', 'business_type',
            'account_number', 'account_holder_name', 'bank_name',
            'logo', 'is_pkp', 'agreed_to_terms'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Buat choices dari model + 'other'
        choices = [(u.id, u.name) for u in Universiti.objects.all()]
        choices.append(('other', 'Lainnya/other'))
        self.fields['university_choice'].choices = [('', '-- Pilih Universitas --')] + choices

        # Semua field wajib kecuali is_pkp & new_university_name
        for field_name, field in self.fields.items():
            if field_name not in ['is_pkp', 'new_university_name']:
                field.required = True
            else:
                field.required = False

        # Tambahkan Tailwind classes ke widget fields
        tailwind_attrs = {
            'university_choice': 'block w-full border border-gray-300 rounded-md px-3 py-2 shadow-sm focus:outline-none focus:ring-primary focus:border-primary',
            'new_university_name': 'block w-full border border-gray-300 rounded-md px-3 py-2 shadow-sm focus:outline-none focus:ring-primary focus:border-primary',
            'phone': 'block w-full border border-gray-300 rounded-md px-3 py-2 shadow-sm focus:outline-none focus:ring-primary focus:border-primary',
            'address': 'block w-full border border-gray-300 rounded-md px-3 py-2 shadow-sm focus:outline-none focus:ring-primary focus:border-primary',
            'description': 'block w-full border border-gray-300 rounded-md px-3 py-2 shadow-sm focus:outline-none focus:ring-primary focus:border-primary',
            'npwp': 'block w-full border border-gray-300 rounded-md px-3 py-2 shadow-sm focus:outline-none focus:ring-primary focus:border-primary',
            'npwp_file': 'block w-full border border-gray-300 rounded-md px-3 py-2 shadow-sm focus:outline-none focus:ring-primary focus:border-primary text-sm file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-primary file:text-white hover:file:bg-blue-700',
            'business_type': 'block w-full border border-gray-300 rounded-md px-3 py-2 shadow-sm focus:outline-none focus:ring-primary focus:border-primary',
            'account_number': 'block w-full border border-gray-300 rounded-md px-3 py-2 shadow-sm focus:outline-none focus:ring-primary focus:border-primary',
            'account_holder_name': 'block w-full border border-gray-300 rounded-md px-3 py-2 shadow-sm focus:outline-none focus:ring-primary focus:border-primary',
            'bank_name': 'block w-full border border-gray-300 rounded-md px-3 py-2 shadow-sm focus:outline-none focus:ring-primary focus:border-primary',
            'logo': 'block w-full border border-gray-300 rounded-md px-3 py-2 shadow-sm focus:outline-none focus:ring-primary focus:border-primary text-sm file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-primary file:text-white hover:file:bg-blue-700',
            'is_pkp': 'h-4 w-4 text-primary focus:ring-primary border-gray-300 rounded',
            'agreed_to_terms': 'h-4 w-4 text-primary focus:ring-primary border-gray-300 rounded',
        }

        

        for field_name, css_class in tailwind_attrs.items():
            if field_name in self.fields and field_name != 'description':  # <-- Tambah kondisi ini
                self.fields[field_name].widget.attrs.update({'class': css_class})

    def clean(self):
        cleaned_data = super().clean()
        university_choice = cleaned_data.get('university_choice')
        new_university = cleaned_data.get('new_university_name')

        # Jika pilih 'other', validasi new_university_name
        if university_choice == 'other':
            if not new_university or not new_university.strip():
                raise ValidationError("Isi nama universitas baru jika memilih 'Lainnya'.")
            # Set university_choice ke None supaya save() pakai new_university
            cleaned_data['university_choice'] = None
        elif not university_choice:
            raise ValidationError("Pilih universitas atau isi universitas baru.")

        return cleaned_data

    def clean_agreed_to_terms(self):
        agreed = self.cleaned_data.get('agreed_to_terms')
        if not agreed:
            raise ValidationError(
                "You must agree to the contract terms and applicable rules to proceed."
            )
        return agreed

    def clean_logo(self):
        logo = self.cleaned_data.get("logo")

        if not logo:
            return logo

        # Validasi ukuran maksimal 3MB
        if logo.size > 3 * 1024 * 1024:
            raise ValidationError("Logo must be under 3MB.")

        img = Image.open(logo)

        # Validasi format
        if img.format not in ["JPEG", "JPG", "PNG", "WEBP"]:
            raise ValidationError("Unsupported image format.")

        # Convert RGBA ke RGB
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # Resize maksimal
        max_size = (600, 600)
        img.thumbnail(max_size)

        # Convert ke WEBP
        buffer = BytesIO()
        img.save(buffer, format="WEBP", quality=85)
        buffer.seek(0)

        return InMemoryUploadedFile(
            buffer,
            "ImageField",
            logo.name.split('.')[0] + ".webp",
            "image/webp",
            buffer.getbuffer().nbytes,
            None
        )

    def save(self, commit=True):
        partner = super().save(commit=False)

        new_university = self.cleaned_data.get('new_university_name')
        university_choice = self.cleaned_data.get('university_choice')

        if new_university:
            university_obj, created = Universiti.objects.get_or_create(name=new_university.strip())
            partner.name = university_obj
        else:
            # university_choice sekarang adalah ID string, convert ke instance
            university_id = int(university_choice) if university_choice else None
            partner.name = Universiti.objects.get(id=university_id) if university_id else None

        if commit:
            partner.save()
        return partner
