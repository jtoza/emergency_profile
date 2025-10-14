from django import forms
from django.core.validators import RegexValidator
from .models import MedicalProfile  # Recommended if no circular import

class MedicalProfileForm(forms.ModelForm):
    national_id = forms.CharField(
        label="National ID",
        validators=[
            RegexValidator(
                regex=r'^[A-Za-z0-9\-]+$',
                message='National ID can only contain letters, numbers, and hyphens',
                code='invalid_national_id'
            )
        ],
        widget=forms.TextInput(attrs={
            'placeholder': 'Enter your National ID',
            'class': 'form-control'
        })
    )

    emergency_phone = forms.CharField(
        label="Emergency Phone",
        required=False,
        validators=[
            RegexValidator(
                regex=r'^\+?[0-9\s\-]+$',
                message='Phone number can only contain numbers, spaces, hyphens, and optional + prefix',
                code='invalid_phone'
            )
        ],
        widget=forms.TextInput(attrs={
            'placeholder': 'e.g. +254 712 345678',
            'class': 'form-control'
        })
    )

    class Meta:
        model = MedicalProfile
        fields = '__all__'
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'allergies': forms.Textarea(attrs={'rows': 3, 'placeholder': 'List allergies (if any)', 'class': 'form-control'}),
            'medical_conditions': forms.Textarea(attrs={'rows': 3, 'placeholder': 'List any known conditions', 'class': 'form-control'}),
            'medications': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Current medications', 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields:
            if field not in ['gender', 'blood_type', 'country', 'allergies', 'medical_conditions', 'medications', 'date_of_birth', 'national_id', 'emergency_phone']:
                self.fields[field].widget.attrs.update({'class': 'form-control'})

        self.fields['gender'].widget.attrs.update({'class': 'form-select'})
        self.fields['blood_type'].widget.attrs.update({'class': 'form-select'})
        self.fields['country'].widget.attrs.update({'class': 'form-select'})
