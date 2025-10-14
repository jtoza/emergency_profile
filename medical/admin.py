from django.contrib import admin
from .models import MedicalProfile, Patient, Visit, Clinic

@admin.register(MedicalProfile)
class MedicalProfileAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'national_id', 'country', 'gender', 'blood_type', 'emergency_contact']
    readonly_fields = ['qr_code', 'doctor_access_code']
    list_filter = ['country', 'gender', 'blood_type']
    search_fields = ['full_name', 'national_id']

@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ['medical_profile', 'created_at']
    search_fields = ['medical_profile__full_name', 'medical_profile__national_id']

@admin.register(Clinic)
class ClinicAdmin(admin.ModelAdmin):
    list_display = ['name', 'location', 'created_at']
    search_fields = ['name', 'location']

@admin.register(Visit)
class VisitAdmin(admin.ModelAdmin):
    list_display = ['patient', 'clinic', 'visit_date']
    list_filter = ['clinic', 'visit_date']
    search_fields = ['patient__medical_profile__full_name', 'diagnosis']