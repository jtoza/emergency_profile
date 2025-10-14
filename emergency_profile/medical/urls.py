from django.urls import path
from . import views

from .views import (
    ProfileListView,
    ProfileCreateView,
    ProfileUpdateView,
    profile_detail,
    emergency_profile,
    public_profile,
    doctor_access
)

urlpatterns = [
    path('', ProfileListView.as_view(), name='profile_list'),
    path('create/', ProfileCreateView.as_view(), name='profile_create'),
    
    path('about/', views.about, name='about'),  # 👈 Move this up before <str:national_id>

    path('emergency/<str:national_id>/', emergency_profile, name='emergency_profile'),
    path('public/<str:national_id>/', public_profile, name='public_profile'),
    path('doctor-access/<str:national_id>/', doctor_access, name='doctor_access'),
    path('<str:national_id>/edit/', ProfileUpdateView.as_view(), name='profile_update'),
    path('<str:national_id>/', profile_detail, name='profile_detail'),  # 👈 Keep this LAST
]
