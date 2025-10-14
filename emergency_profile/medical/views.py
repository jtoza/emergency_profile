from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, CreateView, UpdateView
from django.urls import reverse_lazy
from django.http import Http404
from .models import MedicalProfile
from .forms import MedicalProfileForm
import qrcode
import os
from django.conf import settings

class ProfileListView(ListView):
    model = MedicalProfile
    template_name = 'medical/profile_list.html'
    context_object_name = 'profiles'


class ProfileCreateView(CreateView):
    model = MedicalProfile
    form_class = MedicalProfileForm
    template_name = 'medical/profile_form.html'
    success_url = reverse_lazy('profile_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        # Generate QR code
        qr_data = f"http://{self.request.get_host()}/public/{self.object.national_id}/"
        qr_img = qrcode.make(qr_data)
        qr_path = os.path.join(settings.MEDIA_ROOT, 'qr_codes', f"{self.object.national_id}.png")
        os.makedirs(os.path.dirname(qr_path), exist_ok=True)
        qr_img.save(qr_path)
        return response


class ProfileUpdateView(UpdateView):
    model = MedicalProfile
    form_class = MedicalProfileForm
    template_name = 'medical/edit_profile.html'
    success_url = reverse_lazy('profile_list')
    slug_field = 'national_id'
    slug_url_kwarg = 'national_id'

    def get_object(self, queryset=None):
        national_id = self.kwargs.get('national_id')
        return get_object_or_404(MedicalProfile, national_id=national_id)


def profile_detail(request, national_id):
    profile = get_object_or_404(MedicalProfile, national_id=national_id)
    return render(request, 'medical/profile_detail.html', {'profile': profile})


def emergency_profile(request, national_id):
    profile = get_object_or_404(MedicalProfile, national_id=national_id)
    return render(request, 'medical/emergency_profile.html', {'profile': profile})


def public_profile(request, national_id):
    profile = get_object_or_404(MedicalProfile, national_id=national_id)
    return render(request, 'medical/public_profile.html', {'profile': profile})


def doctor_access(request, national_id):
    profile = get_object_or_404(MedicalProfile, national_id=national_id)
    return render(request, 'medical/doctor_access.html', {'profile': profile})

def about(request):
    return render(request, 'medical/about.html')