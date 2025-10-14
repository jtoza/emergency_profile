import qrcode
from io import BytesIO
from django.db import models
from django.core.files import File
from django.urls import reverse
from django.conf import settings
import datetime
from django.utils import timezone
import secrets


class MedicalProfile(models.Model):
    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
        ('O', 'Other'),
        ('U', 'Prefer not to say'),
    ]
    
    BLOOD_TYPE_CHOICES = [
        ('A+', 'A+'),
        ('A-', 'A-'),
        ('B+', 'B+'),
        ('B-', 'B-'),
        ('AB+', 'AB+'),
        ('AB-', 'AB-'),
        ('O+', 'O+'),
        ('O-', 'O-'),
    ]
    
    full_name = models.CharField(max_length=100)
    national_id = models.CharField(max_length=20, unique=True)
    date_of_birth = models.DateField(null=True, blank=True)
    country = models.CharField(max_length=50, default='Kenya')
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, default='U')
    blood_type = models.CharField(max_length=3, choices=BLOOD_TYPE_CHOICES, blank=True)
    allergies = models.TextField(blank=True)
    medical_conditions = models.TextField(blank=True)
    medications = models.TextField(blank=True)
    emergency_contact = models.CharField(max_length=100)
    emergency_phone = models.CharField(max_length=20, blank=True)
    owner_email = models.EmailField(blank=True)
    qr_code = models.ImageField(upload_to='qr/', blank=True)
    doctor_access_code = models.CharField(max_length=100, blank=True)
    # Synced health monitoring data (preferences, meds, bp, hydration, habits, optional snapshot_html)
    health_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.full_name

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        old_national_id = None

        # If updating, check old national_id from DB
        if not is_new:
            old_national_id = MedicalProfile.objects.filter(pk=self.pk).values_list("national_id", flat=True).first()

        # Generate doctor access code if missing
        if not self.doctor_access_code:
            self.doctor_access_code = secrets.token_urlsafe(8)

        # Save first to ensure we have a primary key
        super().save(*args, **kwargs)

        # Only generate QR if needed
        if is_new or self.national_id != old_national_id or not self.qr_code:
            if not hasattr(settings, 'DOMAIN') or not settings.DOMAIN:
                raise ValueError("DOMAIN setting is not configured in settings.py")

            qr_data = f"http://{settings.DOMAIN}{reverse('public_profile', args=[self.national_id])}"
            qr_img = qrcode.make(qr_data)
            buffer = BytesIO()
            qr_img.save(buffer, format='PNG')
            self.qr_code.save(f'{self.national_id}_qr.png', File(buffer), save=False)

            # Save only the QR field to avoid re-triggering everything
            super().save(update_fields=["qr_code"])

    def get_public_data(self):
        return {
            'full_name': self.full_name,
            'country': self.country,
            'gender': self.get_gender_display(),
            'emergency_contact': self.emergency_contact,
            'emergency_phone': self.emergency_phone,
            'qr_code': self.qr_code.url if self.qr_code else '',
            'age': self.get_age() if self.date_of_birth else None
        }

    def get_full_data(self):
        return {
            'full_name': self.full_name,
            'national_id': self.national_id,
            'date_of_birth': self.date_of_birth.strftime('%Y-%m-%d') if self.date_of_birth else None,
            'country': self.country,
            'gender': self.get_gender_display(),
            'blood_type': self.get_blood_type_display(),
            'allergies': self.allergies,
            'medical_conditions': self.medical_conditions,
            'medications': self.medications,
            'emergency_contact': self.emergency_contact,
            'emergency_phone': self.emergency_phone,
            'qr_code': self.qr_code.url if self.qr_code else '',
            'age': self.get_age() if self.date_of_birth else None
        }

    def get_age(self):
        if not self.date_of_birth:
            return None
        today = datetime.date.today()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )


class Patient(models.Model):
    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
        ('O', 'Other'),
    ]
    
    medical_profile = models.OneToOneField(MedicalProfile, on_delete=models.CASCADE, related_name='patient_record')
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.medical_profile.full_name


class Clinic(models.Model):
    name = models.CharField(max_length=100)
    location = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.name} ({self.location})"


class Visit(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='visits')
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE)
    visit_date = models.DateTimeField(auto_now_add=True)
    diagnosis = models.TextField(blank=True)
    treatment = models.TextField(blank=True)
    
    def __str__(self):
        return f"{self.patient} at {self.clinic} on {self.visit_date.strftime('%Y-%m-%d')}"


class AccessLog(models.Model):
    EVENT_CHOICES = [
        ('public_view', 'Public Profile Viewed'),
        ('doctor_view', 'Doctor Full View'),
        ('doctor_health_view', 'Doctor Health Monitoring View'),
        ('download_html', 'Doctor Download HTML'),
        ('download_pdf', 'Doctor Download PDF'),
    ]

    profile = models.ForeignKey(MedicalProfile, on_delete=models.CASCADE, related_name='access_logs')
    event_type = models.CharField(max_length=20, choices=EVENT_CHOICES)
    viewer_email = models.EmailField(blank=True)
    reason = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    notified = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        who = self.viewer_email or 'anonymous'
        return f"{self.get_event_type_display()} by {who} on {self.created_at:%Y-%m-%d %H:%M}"


class ProfileAnalytics(models.Model):
    profile = models.OneToOneField(MedicalProfile, on_delete=models.CASCADE, related_name='analytics')
    total_scans = models.PositiveIntegerField(default=0)
    last_scan = models.DateTimeField(null=True, blank=True)
    doctor_access_count = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"Analytics for {self.profile.full_name}"


class QRScanLog(models.Model):
    ACCESS_CHOICES = [
        ('public', 'Public'),
        ('emergency', 'Emergency'),
        ('doctor', 'Doctor'),
    ]

    profile = models.ForeignKey(MedicalProfile, on_delete=models.CASCADE, related_name='scans')
    scanned_at = models.DateTimeField(auto_now_add=True)
    scanned_by = models.CharField(max_length=100, null=True, blank=True)
    access_type = models.CharField(max_length=10, choices=ACCESS_CHOICES, default='public')

    class Meta:
        ordering = ['-scanned_at']

    def __str__(self):
        return f"{self.get_access_type_display()} scan for {self.profile.full_name} at {self.scanned_at:%Y-%m-%d %H:%M}"
