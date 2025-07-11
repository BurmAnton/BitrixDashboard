from django import forms
from .models import EducationProgram, ProgramSection

class EducationProgramForm(forms.ModelForm):
    class Meta:
        model = EducationProgram
        fields = [
            'name', 'program_type', 'study_form', 'activities',
            'academic_hours', 'description', 'final_attestation'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'program_type': forms.Select(attrs={'class': 'form-select'}),
            'study_form': forms.Select(attrs={'class': 'form-select'}),
            'activities': forms.Select(attrs={'class': 'form-select'}),
            'academic_hours': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'final_attestation': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
        }

class ProgramSectionForm(forms.ModelForm):
    class Meta:
        model = ProgramSection
        fields = ['name', 'lecture_hours', 'practice_hours', 'selfstudy_hours', 'workload', 'attestation_form', 'description', 'order']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'lecture_hours': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'practice_hours': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'selfstudy_hours': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'workload': forms.NumberInput(attrs={'class': 'form-control', 'readonly': 'readonly', 'min': 0}),
            'attestation_form': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'order': forms.NumberInput(attrs={'class': 'form-control order-input', 'readonly': 'readonly', 'min': 1}),
            'DELETE': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

ProgramSectionFormSet = forms.inlineformset_factory(
    EducationProgram,
    ProgramSection,
    form=ProgramSectionForm,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True
) 