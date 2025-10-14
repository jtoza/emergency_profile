import qrcode
from io import BytesIO
from django.db import models
from django.core.files import File
from django.urls import reverse
from django.conf import settings
import datetime

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
    qr_code = models.ImageField(upload_to='qr/', blank=True)
    doctor_access_code = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.full_name

    def save(self, *args, **kwargs):
        if not self.doctor_access_code:
            import secrets
            self.doctor_access_code = secrets.token_urlsafe(8)
        
        if not hasattr(settings, 'DOMAIN') or not settings.DOMAIN:
            raise ValueError("DOMAIN setting is not configured in settings.py")
        
        qr_data = f"https://{settings.DOMAIN}{reverse('public_profile', args=[self.national_id])}"
        qr_img = qrcode.make(qr_data)
        buffer = BytesIO()
        qr_img.save(buffer, format='PNG')
        self.qr_code.save(f'{self.national_id}_qr.png', File(buffer), save=False)
        super().save(*args, **kwargs)

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
        return today.year - self.date_of_birth.year - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))