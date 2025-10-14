from django.contrib import admin
from .models import MedicalProfile

@admin.register(MedicalProfile)
class MedicalProfileAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'national_id', 'country', 'gender', 'blood_type', 'emergency_contact']
    readonly_fields = ['qr_code', 'doctor_access_code']
    list_filter = ['country', 'gender', 'blood_type']
    search_fields = ['full_name', 'national_id']