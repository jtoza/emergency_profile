from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, CreateView, UpdateView
from django.urls import reverse, reverse_lazy
from django.http import Http404, JsonResponse, HttpResponse
from django.db.models import Count, Q
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth
from django.conf import settings
from django.utils import timezone
from django.template.loader import render_to_string
from django.core.mail import send_mail
from datetime import timedelta
from .models import MedicalProfile, Patient, Visit, Clinic, AccessLog
from .forms import MedicalProfileForm
import qrcode, os, base64, secrets
import json
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login, logout

# List view of profiles
class ProfileListView(ListView):
    model = MedicalProfile
    template_name = 'medical/profile_list.html'
    context_object_name = 'profiles'
    paginate_by = 12

    def get_queryset(self):
        qs = super().get_queryset().order_by('-created_at')
        q = (self.request.GET.get('q') or '').strip()
        if q:
            return qs.filter(Q(full_name__icontains=q) | Q(national_id__icontains=q))
        return qs

# Profile creation view with QR generation
class ProfileCreateView(CreateView):
    model = MedicalProfile
    form_class = MedicalProfileForm
    template_name = 'medical/profile_form.html'
    success_url = reverse_lazy('profile_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        # Create associated Patient record; QR is handled in model.save()
        Patient.objects.create(medical_profile=self.object)
        return response

# Profile update view
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['profile'] = self.object
        return context

    def get_success_url(self):
        next_url = self.request.POST.get('next') or self.request.GET.get('next')
        if next_url:
            return next_url
        return reverse('profile_detail', kwargs={'national_id': self.object.national_id})

# Single profile views
def profile_detail(request, national_id):
    profile = get_object_or_404(MedicalProfile, national_id=national_id)
    return render(request, 'medical/profile_detail.html', {'profile': profile})

def emergency_profile(request, national_id):
    profile = get_object_or_404(MedicalProfile, national_id=national_id)
    return render(request, 'medical/emergency_profile.html', {'profile': profile})

# Utilities

def _client_ip(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        # First IP in XFF is the original client IP
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _user_agent(request):
    return request.META.get('HTTP_USER_AGENT', '')


# Public profile - limited view (with logging)
def public_profile(request, national_id):
    profile = get_object_or_404(MedicalProfile, national_id=national_id)

    # Log public view
    try:
        AccessLog.objects.create(
            profile=profile,
            event_type='public_view',
            ip_address=_client_ip(request),
            user_agent=_user_agent(request),
        )
    except Exception:
        # Non-fatal logging
        pass

    # Limited info only
    context = {
        'profile': profile,
        'limited': True
    }
    return render(request, 'medical/public_profile.html', context)

# Helper to embed QR as data URI
_def_missing = object()

def _qr_data_uri_or_none(profile):
    try:
        if profile.qr_code and getattr(profile.qr_code, 'path', _def_missing) is not _def_missing:
            if profile.qr_code.path and os.path.exists(profile.qr_code.path):
                with open(profile.qr_code.path, 'rb') as f:
                    b64 = base64.b64encode(f.read()).decode('ascii')
                    return f'data:image/png;base64,{b64}'
    except Exception:
        pass
    return None

# Doctor access view with Email OTP (+ reason capture)
def doctor_access(request, national_id):
    profile = get_object_or_404(MedicalProfile, national_id=national_id)

    def _otp_key(nid: str) -> str:
        return f'otp_pending_{nid}'

    pending = request.session.get(_otp_key(profile.national_id))

    context = {
        'profile': profile,
        'otp_pending': bool(pending),
        'email_value': pending.get('email') if pending else '',
        'otp_info': None,
        'error': None,
    }

    if request.method == 'POST':
        action = request.POST.get('action')
        # Send OTP to provided email
        if action == 'send_otp':
            email = (request.POST.get('email') or '').strip()
            if not email or '@' not in email:
                context['error'] = 'Enter a valid email address to receive the OTP.'
                return render(request, 'medical/doctor_access.html', context, status=400)

            # Generate 6-digit OTP
            code = f"{secrets.randbelow(1000000):06d}"
            expires_at = (timezone.now() + timedelta(minutes=getattr(settings, 'OTP_TTL_MINUTES', 5))).isoformat()

            request.session[_otp_key(profile.national_id)] = {
                'email': email,
                'code': code,
                'expires_at': expires_at,
                'attempts': 0,
            }
            request.session.modified = True

            # Send email
            subject = 'Your One-Time Access Code'
            message = (
                f"Dear Doctor,\n\n"
                f"Your one-time access code for patient {profile.full_name} ({profile.national_id}) is: {code}.\n"
                f"This code expires in {getattr(settings, 'OTP_TTL_MINUTES', 5)} minutes.\n\n"
                f"If you did not request this code, you can ignore this email."
            )
            send_mail(subject, message, getattr(settings, 'DEFAULT_FROM_EMAIL', None), [email], fail_silently=True)

            context['otp_pending'] = True
            context['email_value'] = email
            context['otp_info'] = f'An OTP has been sent to {email}. Please enter it below.'
            return render(request, 'medical/doctor_access.html', context)

        # Verify submitted OTP
        if action == 'verify_otp':
            code_input = (request.POST.get('access_code') or '').strip()
            reason = (request.POST.get('reason') or '').strip()
            pending = request.session.get(_otp_key(profile.national_id))
            if not pending:
                context['error'] = 'Request an OTP first by entering your email.'
                return render(request, 'medical/doctor_access.html', context, status=400)

            # Check expiry and attempts
            expires_at = timezone.datetime.fromisoformat(pending['expires_at'])
            if timezone.is_naive(expires_at):
                expires_at = timezone.make_aware(expires_at, timezone.get_current_timezone())
            if timezone.now() > expires_at:
                # Expired, clear pending
                try:
                    del request.session[_otp_key(profile.national_id)]
                    request.session.modified = True
                except KeyError:
                    pass
                context['error'] = 'The OTP has expired. Please request a new one.'
                context['otp_pending'] = False
                context['email_value'] = ''
                return render(request, 'medical/doctor_access.html', context, status=400)

            attempts = int(pending.get('attempts', 0))
            max_attempts = int(getattr(settings, 'OTP_MAX_ATTEMPTS', 5))
            if attempts >= max_attempts:
                context['error'] = 'Too many attempts. Please request a new OTP.'
                return render(request, 'medical/doctor_access.html', context, status=429)

            if not reason:
                context['error'] = 'Reason for access is required.'
                context['otp_pending'] = True
                context['email_value'] = pending.get('email', '')
                return render(request, 'medical/doctor_access.html', context, status=400)

            if code_input and code_input == pending.get('code'):
                # Success: mark session verified and clear OTP
                request.session[f'doctor_access_{profile.national_id}'] = True
                request.session[f'doctor_access_{profile.national_id}_email'] = pending.get('email')
                request.session[f'doctor_access_{profile.national_id}_reason'] = reason
                try:
                    del request.session[_otp_key(profile.national_id)]
                except KeyError:
                    pass
                request.session.modified = True
                return redirect('doctor_profile', national_id=profile.national_id)
            else:
                # Increment attempts and show error
                pending['attempts'] = attempts + 1
                request.session[_otp_key(profile.national_id)] = pending
                request.session.modified = True
                context['error'] = 'Invalid code. Please try again.'
                context['otp_pending'] = True
                context['email_value'] = pending.get('email', '')
                return render(request, 'medical/doctor_access.html', context, status=401)

        # Unknown action
        context['error'] = 'Invalid action.'
        return render(request, 'medical/doctor_access.html', context, status=400)

    return render(request, 'medical/doctor_access.html', context)

# Doctor full view route (requires session verification)
# Logs access and sends rate-limited notification

def _notify_owner_if_needed(profile, event_type, log_obj):
    if not profile.owner_email:
        return
    # Cooldown minutes
    mins = int(getattr(settings, 'ACCESS_NOTIFY_COOLDOWN_MINUTES', 30))
    since = timezone.now() - timedelta(minutes=mins)
    recent = AccessLog.objects.filter(
        profile=profile, event_type=event_type, notified=True, created_at__gte=since
    ).exists()
    if recent:
        return

    subject = f"Access to your medical profile ({profile.full_name})"
    reason = log_obj.reason or 'N/A'
    viewer = log_obj.viewer_email or 'unknown'
    message = (
        f"Hello {profile.full_name},\n\n"
        f"Your medical profile was accessed.\n"
        f"Event: {log_obj.get_event_type_display()}\n"
        f"When: {log_obj.created_at:%Y-%m-%d %H:%M %Z}\n"
        f"By: {viewer}\n"
        f"Reason: {reason}\n"
        f"IP: {log_obj.ip_address or 'N/A'}\n"
        f"User-Agent: {log_obj.user_agent[:200]}\n\n"
        f"If this was unexpected, please contact support."
    )
    try:
        send_mail(subject, message, getattr(settings, 'DEFAULT_FROM_EMAIL', None), [profile.owner_email], fail_silently=True)
        log_obj.notified = True
        log_obj.save(update_fields=['notified'])
    except Exception:
        pass


def doctor_profile_view(request, national_id):
    if not request.session.get(f'doctor_access_{national_id}'):
        return redirect('doctor_access', national_id=national_id)
    profile = get_object_or_404(MedicalProfile, national_id=national_id)

    # Create access log entry
    log_obj = None
    try:
        log_obj = AccessLog.objects.create(
            profile=profile,
            event_type='doctor_view',
            viewer_email=request.session.get(f'doctor_access_{national_id}_email', ''),
            reason=request.session.get(f'doctor_access_{national_id}_reason', ''),
            ip_address=_client_ip(request),
            user_agent=_user_agent(request),
        )
    except Exception:
        pass

    if log_obj:
        _notify_owner_if_needed(profile, 'doctor_view', log_obj)

    return render(request, 'medical/doctor_profile.html', {'profile': profile, 'qr_data_uri': _qr_data_uri_or_none(profile)})

# Download full details as an elegant HTML document (requires session verification)
# Logs download and sends rate-limited notification

def doctor_profile_download(request, national_id):
    if not request.session.get(f'doctor_access_{national_id}'):
        return redirect('doctor_access', national_id=national_id)
    profile = get_object_or_404(MedicalProfile, national_id=national_id)

    # Log download event
    log_obj = None
    try:
        log_obj = AccessLog.objects.create(
            profile=profile,
            event_type='download_html',
            viewer_email=request.session.get(f'doctor_access_{national_id}_email', ''),
            reason=request.session.get(f'doctor_access_{national_id}_reason', ''),
            ip_address=_client_ip(request),
            user_agent=_user_agent(request),
        )
    except Exception:
        pass

    if log_obj:
        _notify_owner_if_needed(profile, 'download_html', log_obj)

    context = {'profile': profile, 'now': timezone.now(), 'qr_data_uri': _qr_data_uri_or_none(profile)}
    html = render_to_string('medical/doctor_profile_download.html', context)
    filename = f'medical_profile_{profile.national_id}.html'
    response = HttpResponse(html, content_type='text/html; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

# Download full details as PDF (requires session verification)
# Logs download and sends rate-limited notification

def doctor_profile_download_pdf(request, national_id):
    if not request.session.get(f'doctor_access_{national_id}'):
        return redirect('doctor_access', national_id=national_id)
    profile = get_object_or_404(MedicalProfile, national_id=national_id)

    # Log download event
    log_obj = None
    try:
        log_obj = AccessLog.objects.create(
            profile=profile,
            event_type='download_pdf',
            viewer_email=request.session.get(f'doctor_access_{national_id}_email', ''),
            reason=request.session.get(f'doctor_access_{national_id}_reason', ''),
            ip_address=_client_ip(request),
            user_agent=_user_agent(request),
        )
    except Exception:
        pass

    if log_obj:
        _notify_owner_if_needed(profile, 'download_pdf', log_obj)

    context = {'profile': profile, 'now': timezone.now(), 'qr_data_uri': _qr_data_uri_or_none(profile)}
    html_string = render_to_string('medical/doctor_profile_download.html', context)
    try:
        from weasyprint import HTML
    except Exception:
        return HttpResponse(
            'PDF generation is not available on this server. Install weasyprint (pip install weasyprint) and system dependencies. Use the HTML download in the meantime.',
            status=501,
            content_type='text/plain; charset=utf-8'
        )

    pdf_bytes = HTML(string=html_string, base_url=request.build_absolute_uri('/')).write_pdf()
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="medical_profile_{profile.national_id}.pdf"'
    return response


def about(request):
    return render(request, 'medical/about.html')

# Health monitoring landing page (client-side tools)
@login_required
def health_monitoring(request):
    return render(request, 'medical/health_monitoring.html')

# Simple signup that logs the user in then redirects to health page
def signup(request):
    if request.user.is_authenticated:
        return redirect('health_monitoring')
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('health_monitoring')
    else:
        form = UserCreationForm()
    return render(request, 'registration/signup.html', {'form': form})

# Logout via GET then redirect to home (avoids 405 when using a link)
def logout_view(request):
    logout(request)
    return redirect('home')

# --- MAIN DASHBOARD VIEW ---
def dashboard_view(request):
    # Counts
    total_patients = Patient.objects.count()
    total_visits = Visit.objects.count()

    # Repeat visits
    repeat_visits = Visit.objects.values('patient').annotate(count=Count('id')).filter(count__gt=1).count()
    repeat_rate = (repeat_visits / total_patients) * 100 if total_patients else 0

    # Gender breakdown (using MedicalProfile)
    gender_counts = MedicalProfile.objects.values('gender').annotate(count=Count('id'))

    # Top clinics by number of visits
    top_clinics = Clinic.objects.annotate(visit_count=Count('visit')).order_by('-visit_count')[:5]

    context = {
        'total_patients': total_patients,
        'total_visits': total_visits,
        'repeat_rate': round(repeat_rate, 2),
        'gender_counts': gender_counts,
        'top_clinics': top_clinics,
    }
    return render(request, 'medical/dashboard.html', context)

# --- ANALYTICS API VIEW for Patient Registrations ---
def patient_registration_stats(request):
    # Daily registrations for the past 7 days
    daily = Patient.objects.annotate(date=TruncDay('created_at')).values('date').annotate(count=Count('id')).order_by('date')

    # Weekly registrations for the past 8 weeks
    weekly = Patient.objects.annotate(week=TruncWeek('created_at')).values('week').annotate(count=Count('id')).order_by('week')

    # Monthly registrations for the past 6 months
    monthly = Patient.objects.annotate(month=TruncMonth('created_at')).values('month').annotate(count=Count('id')).order_by('month')

    return JsonResponse({
        'daily': list(daily),
        'weekly': list(weekly),
        'monthly': list(monthly),
    })


# --- Patient-visible access log timeline ---

def patient_access_log(request, national_id):
    profile = get_object_or_404(MedicalProfile, national_id=national_id)
    logs = profile.access_logs.all()[:200]
    return render(request, 'medical/access_log.html', {'profile': profile, 'logs': logs})

@csrf_exempt
def health_sync(request, national_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    profile = get_object_or_404(MedicalProfile, national_id=national_id)
    try:
        data = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    owner_email = (data.get('owner_email') or '').strip().lower()
    if profile.owner_email and profile.owner_email.lower() != owner_email:
        return JsonResponse({'error': 'Owner email mismatch'}, status=403)

    health_payload = {
        'prefs': data.get('prefs') or {},
        'meds': data.get('meds') or [],
        'bp': data.get('bp') or [],
        'hr': data.get('hr') or [],
        'steps': data.get('steps') or [],
        'water': data.get('water') or {},
        'habits': data.get('habits') or [],
        'snapshot_html': data.get('snapshot_html') or '',
        'synced_at': timezone.now().isoformat(),
    }
    profile.health_data = health_payload
    try:
        profile.save(update_fields=['health_data', 'updated_at'])
    except Exception:
        return JsonResponse({'error': 'Failed to save'}, status=500)

    return JsonResponse({'status': 'ok'})


def health_data_get(request, national_id):
    if not request.session.get(f'doctor_access_{national_id}'):
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    profile = get_object_or_404(MedicalProfile, national_id=national_id)
    return JsonResponse(profile.health_data or {}, safe=False)

def doctor_health_monitoring_view(request, national_id):
    if not request.session.get(f'doctor_access_{national_id}'):
        return redirect('doctor_access', national_id=national_id)
    profile = get_object_or_404(MedicalProfile, national_id=national_id)

    # Log access
    try:
        log_obj = AccessLog.objects.create(
            profile=profile,
            event_type='doctor_health_view',
            viewer_email=request.session.get(f'doctor_access_{national_id}_email', ''),
            reason=request.session.get(f'doctor_access_{national_id}_reason', ''),
            ip_address=_client_ip(request),
            user_agent=_user_agent(request),
        )
    except Exception:
        log_obj = None

    if log_obj:
        _notify_owner_if_needed(profile, 'doctor_view', log_obj)

    context = {
        'profile': profile,
        'health_json': json.dumps(profile.health_data or {}),
    }
    return render(request, 'medical/health_monitoring_clinician.html', context)

# -------------------------
# PWA: Manifest & Service Worker endpoints
# -------------------------

def manifest(request):
    """Serve a Web App Manifest for PWA installability."""
    app_name = 'MediTrack'
    start_url = '/'
    scope = '/'
    theme = '#4361ee'
    manifest_data = {
        "name": app_name,
        "short_name": "MediTrack",
        "start_url": start_url,
        "scope": scope,
        "display": "standalone",
        "theme_color": theme,
        "background_color": "#f9fafb",
        "icons": [
            {"src": "/static/medical/app-icon-192.svg", "sizes": "192x192", "type": "image/svg+xml", "purpose": "maskable any"},
            {"src": "/static/medical/app-icon-512.svg", "sizes": "512x512", "type": "image/svg+xml", "purpose": "maskable any"}
        ]
    }
    return HttpResponse(json.dumps(manifest_data), content_type='application/manifest+json; charset=utf-8')


def service_worker(request):
    """Serve the Service Worker JS. Must be at the origin scope ('/')."""
    sw_js = r"""
    const CACHE_NAME = 'meditrack-v1';
    const PRECACHE_URLS = [
      '/',
      '/health/',
      '/static/medical/app-icon-192.svg',
      '/static/medical/app-icon-512.svg'
    ];

    self.addEventListener('install', (event) => {
      event.waitUntil((async () => {
        try {
          const cache = await caches.open(CACHE_NAME);
          await cache.addAll(PRECACHE_URLS);
        } catch (e) { /* ignore */ }
      })());
      self.skipWaiting();
    });

    self.addEventListener('activate', (event) => {
      event.waitUntil((async () => {
        const keys = await caches.keys();
        await Promise.all(keys.map(k => { if (k !== CACHE_NAME) return caches.delete(k); }));
        await self.clients.claim();
      })());
    });

    async function fromNetwork(request) {
      const response = await fetch(request);
      if (request.method === 'GET') {
        const cache = await caches.open(CACHE_NAME);
        cache.put(request, response.clone());
      }
      return response;
    }

    async function fromCache(request) {
      const cache = await caches.open(CACHE_NAME);
      const match = await cache.match(request);
      if (match) return match;
      throw new Error('no-match');
    }

    const OFFLINE_FALLBACK = new Response(`<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Offline</title><style>body{font-family:sans-serif;padding:2rem} .card{border:1px solid #e5e7eb;border-radius:12px;padding:1rem;max-width:600px;margin:auto}</style></head><body><div class="card"><h1>Offline</h1><p>You are offline. Please reconnect to view the latest content.</p></div></body></html>`, { headers: { 'Content-Type': 'text/html; charset=utf-8' } });

    self.addEventListener('fetch', (event) => {
      const req = event.request;
      if (req.method !== 'GET') return;

      // Navigations: network-first with offline fallback
      if (req.mode === 'navigate') {
        event.respondWith((async () => {
          try { return await fromNetwork(req); } catch (e) {
            try { return await fromCache(req); } catch (_) { return OFFLINE_FALLBACK; }
          }
        })());
        return;
      }

      const url = new URL(req.url);
      // Static assets: cache-first
      if (url.pathname.startsWith('/static/')) {
        event.respondWith((async () => { try { return await fromCache(req); } catch (e) { return await fromNetwork(req); } })());
        return;
      }

      // Default: network-first with cache fallback
      event.respondWith((async () => {
        try { return await fromNetwork(req); } catch (e) { try { return await fromCache(req); } catch (_) { throw e; } }
      })());
    });
    """
    resp = HttpResponse(sw_js, content_type='application/javascript; charset=utf-8')
    resp['Service-Worker-Allowed'] = '/'
    return resp
