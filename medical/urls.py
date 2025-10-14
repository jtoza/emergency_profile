from django.urls import path
from django.views.generic import TemplateView, RedirectView
from django.contrib.auth import views as auth_views
from . import views

from .views import (
    ProfileListView,
    ProfileCreateView,
    ProfileUpdateView,
    profile_detail,
    emergency_profile,
    public_profile,
    doctor_access,
    doctor_profile_view,
    doctor_profile_download,
    doctor_profile_download_pdf,
    health_monitoring,
    doctor_health_monitoring_view,
    health_sync,
    patient_registration_stats,
    health_data_get,
    manifest,
    service_worker,
)

urlpatterns = [
    path('', TemplateView.as_view(template_name='medical/landing.html'), name='home'),
    path('profiles/', ProfileListView.as_view(), name='profile_list'),
    path('create/', ProfileCreateView.as_view(), name='profile_create'),
    
    path('about/', views.about, name='about'),  
    path('accounts/login/', auth_views.LoginView.as_view(template_name='registration/login.html', redirect_authenticated_user=True), name='login'),
    path('accounts/login', auth_views.LoginView.as_view(template_name='registration/login.html', redirect_authenticated_user=True), name='login_no_slash'),
    path('accounts/logout/', views.logout_view, name='logout'),
    path('accounts/logout', views.logout_view, name='logout_no_slash'),
    path('accounts/signup/', views.signup, name='signup'),  
    path('accounts/signup', views.signup, name='signup_no_slash'),  
    # Some auth flows default to /accounts/profile/; redirect it to the Health page
    path('accounts/profile/', RedirectView.as_view(pattern_name='health_monitoring', permanent=False)),  

    path('emergency/<str:national_id>/', emergency_profile, name='emergency_profile'),
    path('public/<str:national_id>/', public_profile, name='public_profile'),
    path('doctor-access/<str:national_id>/', doctor_access, name='doctor_access'),
    path('doctor/<str:national_id>/', doctor_profile_view, name='doctor_profile'),
    path('doctor/<str:national_id>/download/', doctor_profile_download, name='doctor_profile_download'),
    path('doctor/<str:national_id>/download.pdf', doctor_profile_download_pdf, name='doctor_profile_download_pdf'),
    path('<str:national_id>/edit/', ProfileUpdateView.as_view(), name='profile_update'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('health/', health_monitoring, name='health_monitoring'),
    path('doctor/<str:national_id>/health/', doctor_health_monitoring_view, name='doctor_health_monitoring'),
    path('api/health/<str:national_id>/', health_data_get, name='health_data_get'),
    path('api/health-sync/<str:national_id>/', health_sync, name='health_sync'),
    path('manifest.webmanifest', manifest, name='manifest'),
    path('service-worker.js', service_worker, name='service_worker'),
    path('api/analytics/registrations/', patient_registration_stats, name='patient_registration_stats'),
    path('<str:national_id>/access-log/', views.patient_access_log, name='patient_access_log'),
    path('<str:national_id>/', profile_detail, name='profile_detail'),  
]
