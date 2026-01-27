from django import forms
from courses.models import SectionReport

class SectionReportForm(forms.ModelForm):
    class Meta:
        model = SectionReport
        fields = ['section', 'material', 'assessment', 'status']
        widgets = {
            'status': forms.HiddenInput(attrs={'value': SectionReport.STATUS_PENDING})
        }