import ast
import base64
import csv
import io
import json
import logging
import os
import secrets
import time
import re
import tempfile
from datetime import datetime
from io import BytesIO
from xml.sax.saxutils import escape

import cv2
import numpy as np
import requests as http_requests
from PIL import Image as PILImage
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.utils.dateparse import parse_date
from django.utils.timezone import localtime, now
from django.views.decorators.http import require_POST
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Image as ReportLabImage, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .forms import CustomUserForm, FeedbackForm, HelpMessageForm, SignUpForm
from .models import Feedback, HelpMessage, UploadHistory, UserProfile
from .sms_utils import send_sms

logger = logging.getLogger(__name__)
User = get_user_model()

ROBOFLOW_API_KEY = os.environ.get("ROBOFLOW_API_KEY", "")
ROBOFLOW_MODEL = "coco/17"
ROBOFLOW_SSL_VERIFY = os.environ.get("ROBOFLOW_SSL_VERIFY", "True") == "True"

COLORS = [
    (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0),
    (0, 255, 255), (255, 0, 255), (128, 255, 0), (255, 128, 0),
    (0, 128, 255), (128, 0, 255),
]


def _is_admin(user):
    return bool(user and user.is_authenticated and (user.is_superuser or getattr(user, 'role', '') == 'admin'))


def _parse_detected_objects(raw):
    """Safely parse UploadHistory.detected_objects into a list of {'label', 'count'} dicts."""
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        return [{"label": k, "count": v} for k, v in raw.items()]
    parsed = None
    try:
        parsed = ast.literal_eval(raw)
    except Exception:
        try:
            parsed = json.loads(raw)
        except Exception:
            return []
    if isinstance(parsed, dict):
        return [{"label": k, "count": v} for k, v in parsed.items()]
    if isinstance(parsed, list):
        return parsed
    return []


def index(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'index.html')


@login_required
def history(request):
    user_uploads = UploadHistory.objects.filter(user=request.user).order_by('-uploaded_at')
    context = []
    for upload in user_uploads:
        context.append({
            'id': upload.id,
            'image_url': upload.image or '',
            'detected_objects': _parse_detected_objects(upload.detected_objects),
            'uploaded_at': localtime(upload.uploaded_at).strftime('%d %b %Y, %I:%M %p') + ' IST',
            'username': upload.user.username,
        })
    return render(request, 'history.html', {'user_uploads': context})


def dashboard(request):
    if not request.user.is_authenticated:
        return redirect('signin')
    return render(request, 'dashboard.html', {'media_url': settings.MEDIA_URL})


@login_required
def test(request):
    return render(request, 'test.html')


def signin(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        list(messages.get_messages(request))
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')

        user = authenticate(request, email=email, password=password)
        if user is not None:
            if user.is_active:
                login(request, user)
                messages.success(request, "You're logged in")
                return redirect('dashboard')
            messages.error(request, "You are not allowed to log in. Contact admin.")
            return redirect('signin')

        messages.error(request, 'Invalid email or password')
        return redirect('signin')

    return render(request, 'signin.html')


def logout_user(request):
    logout(request)
    list(messages.get_messages(request))
    messages.success(request, 'You have been logged out. <br>Please Sign in again')
    return redirect('index')


def signup(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            raw_password = form.cleaned_data['password']
            user.set_password(raw_password)
            user.save()
            auth_user = authenticate(request, email=form.cleaned_data['email'], password=raw_password)
            if auth_user is not None:
                login(request, auth_user)
                messages.success(request, "You're now registered!")
                return redirect('dashboard')
            messages.error(request, 'Registered successfully. Please sign in manually.')
            return redirect('signin')
    else:
        form = SignUpForm()

    return render(request, 'signup.html', {'form': form})


def forgot(request):
    error_message = None
    if request.method == 'POST':
        phone_number = (request.POST.get('phone_number') or '').strip()
        phone_pattern = r'^\+?[0-9]{10,15}$'
        if not re.match(phone_pattern, phone_number):
            error_message = "Invalid phone number format. Please enter a valid number."
            return render(request, 'forgot.html', {'error': error_message})

        try:
            user = UserProfile.objects.get(phone=phone_number)
            otp_code = str(secrets.randbelow(900000) + 100000)
            send_sms(phone_number, f"Your OTP is: {otp_code}")

            request.session['user_id'] = user.id
            request.session['otp_code'] = otp_code
            request.session['otp_verified'] = False
            request.session['otp_expires_at'] = time.time() + 300
            request.session['otp_attempts'] = 0
            return redirect('verify_otp')
        except UserProfile.DoesNotExist:
            error_message = "User with this phone number does not exist."
        except Exception as e:
            logger.exception("Failed to send OTP SMS")
            error_message = f"Failed to send OTP: {e}"

    return render(request, 'forgot.html', {'error': error_message})


def verify_otp(request):
    if not request.session.get('otp_code') or not request.session.get('user_id'):
        return redirect('forgot')

    if time.time() >= request.session.get('otp_expires_at', 0) or request.session.get('otp_attempts', 0) >= 5:
        for key in ('otp_code', 'user_id', 'otp_verified', 'otp_expires_at', 'otp_attempts'):
            request.session.pop(key, None)
        return redirect('forgot')

    if request.method == 'POST':
        request.session['otp_attempts'] = request.session.get('otp_attempts', 0) + 1
        entered_otp = (request.POST.get('otp') or '').strip()
        generated_otp = request.session.get('otp_code')

        if generated_otp and entered_otp and secrets.compare_digest(entered_otp, generated_otp):
            request.session['otp_verified'] = True
            return redirect('password_reset')
        return render(request, 'verify_otp.html', {'error': 'Invalid OTP'})

    return render(request, 'verify_otp.html')


def contact(request):
    return render(request, 'contact.html')


def about(request):
    return render(request, 'about.html')


def services(request):
    return render(request, 'services.html')


def password_reset(request):
    user_id = request.session.get('user_id')
    otp_verified = request.session.get('otp_verified', False)
    if not user_id or not otp_verified or time.time() >= request.session.get('otp_expires_at', 0):
        return redirect('forgot')

    if request.method == 'POST':
        new_password = request.POST.get('new_password') or ''
        confirm_password = request.POST.get('confirm_password') or ''

        if new_password != confirm_password:
            return render(request, 'password_reset.html', {'error': 'Passwords do not match.'})

        try:
            validate_password(new_password)
        except ValidationError as e:
            return render(request, 'password_reset.html', {'error': ' '.join(e.messages)})

        try:
            user = UserProfile.objects.get(id=user_id)
        except UserProfile.DoesNotExist:
            return redirect('signin')

        if user.check_password(new_password):
            return render(request, 'password_reset.html', {'error': 'New password cannot be the same as the old password.'})

        user.set_password(new_password)
        user.save()

        request.session.pop('otp_expires_at', None)
        request.session.pop('otp_attempts', None)
        request.session.pop('otp_code', None)
        request.session.pop('otp_verified', None)
        request.session.pop('user_id', None)

        if request.user.is_authenticated and request.user.id == user.id:
            update_session_auth_hash(request, user)

        return render(request, 'password_reset.html', {'success': True})

    return render(request, 'password_reset.html')


@login_required
def remove_profile_image(request):
    if request.method != 'POST':
        return redirect('view_profile')
    user = request.user
    user.profile_image = None
    user.save(update_fields=['profile_image'])
    return JsonResponse({'success': True, 'default_url': static('images/default.jpg')})


@login_required
def upload_profile_image_ajax(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid method'}, status=405)
    user = request.user
    image = request.FILES.get('profile_image')
    if not image:
        return JsonResponse({'success': False, 'error': 'No image provided'}, status=400)
    allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
    if image.content_type not in allowed_types:
        return JsonResponse({'success': False, 'error': 'Invalid file type. Use JPEG, PNG, GIF or WebP.'}, status=400)
    if image.size > 5 * 1024 * 1024:
        return JsonResponse({'success': False, 'error': 'File too large. Max 5MB.'}, status=400)
    try:
        img_data = base64.b64encode(image.read()).decode('utf-8')
        data_url = f"data:{image.content_type};base64,{img_data}"
        user.profile_image = data_url
        user.save(update_fields=['profile_image'])
        return JsonResponse({'success': True, 'image_url': data_url})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def view_profile(request):
    user = request.user
    if request.method == "POST":
        new_name = (request.POST.get("name") or "").strip()
        new_email = (request.POST.get("email") or "").strip()
        new_phone = (request.POST.get("phone") or "").strip()

        if not new_name or not new_email or not new_phone:
            messages.error(request, "Name, email, and phone are required.")
            return redirect("view_profile")

        if UserProfile.objects.filter(email=new_email).exclude(id=user.id).exists():
            messages.error(request, "This email is already in use.")
            return redirect("view_profile")

        if UserProfile.objects.filter(phone=new_phone).exclude(id=user.id).exists():
            messages.error(request, "This phone number is already in use.")
            return redirect("view_profile")

        user.name = new_name
        user.email = new_email
        user.phone = new_phone
        user.save()
        messages.success(request, "Profile updated successfully!")
        return redirect("view_profile")

    return render(request, "view_profile.html")


@login_required
def change_password(request):
    if request.method == 'POST':
        current_password = request.POST.get('currentpassword') or ''
        new_password = request.POST.get('newpassword') or ''
        confirm_password = request.POST.get('retypenewpassword') or ''

        user = request.user

        if not user.check_password(current_password):
            messages.error(request, "Current password is incorrect.")
            return redirect('change_password')

        if user.check_password(new_password):
            messages.error(request, "New password cannot be the same as the old password.")
            return redirect('change_password')

        if len(new_password) < 8:
            messages.error(request, "New password must be at least 8 characters long.")
            return redirect('change_password')

        if new_password != confirm_password:
            messages.error(request, "New passwords do not match.")
            return redirect('change_password')

        try:
            validate_password(new_password, user)
        except ValidationError as e:
            messages.error(request, ' '.join(e.messages))
            return redirect('change_password')

        user.set_password(new_password)
        user.save()
        update_session_auth_hash(request, user)
        messages.success(request, "Password updated successfully!")
        return redirect('change_password')

    return render(request, 'change_password.html')


@login_required
def delete_account(request):
    if request.method == "POST":
        password = request.POST.get("password") or ""
        if request.user.check_password(password):
            user = request.user
            logout(request)
            user.delete()
            messages.success(request, "Your account has been deleted successfully.")
            return redirect('signin')
        messages.error(request, "Your password is incorrect. Please try again.")

    return render(request, "delete_account.html")


def help_center(request):
    return render(request, "help_center.html")


def submit_message(request):
    if request.method == "POST":
        form = HelpMessageForm(request.POST)
        if form.is_valid():
            form.save()
            return JsonResponse({"success": True, "message": "Message sent successfully!"})
        errors = {field: error.get_json_data() for field, error in form.errors.items()}
        return JsonResponse({"success": False, "message": "Validation errors", "errors": errors})
    return JsonResponse({"success": False, "message": "Invalid request"})


def terms_policy(request):
    return render(request, 'terms_policy.html')


def submit_feedback(request):
    if not request.user.is_authenticated:
        return JsonResponse({"success": False, "message": "Authentication required"}, status=401)
    if request.method == 'POST':
        form = FeedbackForm(request.POST)
        if form.is_valid():
            feedback = form.save(commit=False)
            feedback.user = request.user
            feedback.save()
            return JsonResponse({"success": True, "message": "Message sent successfully!"})
        errors = {field: error.get_json_data() for field, error in form.errors.items()}
        return JsonResponse({"success": False, "message": "Validation errors", "errors": errors})

    return JsonResponse({"success": False, "message": "Invalid request"})


def admin_dashboard(request):
    if not request.user.is_authenticated:
        return redirect('admin_login')
    if not _is_admin(request.user):
        return redirect('index')

    users = UserProfile.objects.filter(role="user").order_by('-id')
    feedbacks = Feedback.objects.all().order_by('-created_at')
    help_messages = HelpMessage.objects.all().order_by('-created_at')
    context = {
        'users': users,
        'total_users': users.count(),
        'active_users': users.filter(is_active=True).count(),
        'inactive_users': users.filter(is_active=False).count(),
        'feedbacks': feedbacks,
        'help_messages': help_messages,
    }
    return render(request, 'admin_dashboard.html', context)


def admin_logout(request):
    """Logs out the admin and redirects to the admin login page."""
    logout(request)
    messages.success(request, 'Admin logged out successfully.')
    return redirect('admin_login')


@login_required
def help_message_view(request):
    """View to display help messages with search and filtering capabilities."""
    if not _is_admin(request.user):
        return redirect('index')

    help_messages = HelpMessage.objects.all().order_by('-created_at')
    search_query = request.GET.get('search', '')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    if search_query:
        help_messages = help_messages.filter(name__icontains=search_query)

    if start_date and end_date:
        start_d = parse_date(start_date)
        end_d = parse_date(end_date)
        if start_d and end_d:
            help_messages = help_messages.filter(created_at__date__range=[start_d, end_d])

    return render(request, 'help_message.html', {'help_messages': help_messages})


@login_required
def users_feedback_view(request):
    if not _is_admin(request.user):
        return redirect('index')
    feedbacks = Feedback.objects.select_related('user').all().order_by('-created_at')
    return render(request, 'user_feedback.html', {'feedbacks': feedbacks})


@login_required
def users(request):
    if not _is_admin(request.user):
        return redirect('index')
    all_users = UserProfile.objects.all().order_by('-id')
    return render(request, 'users.html', {'users': all_users})


def detect_with_roboflow(image):
    """Send image to Roboflow API and return annotated image + detections."""
    if not ROBOFLOW_API_KEY:
        raise RuntimeError("ROBOFLOW_API_KEY is not configured.")

    _, buffer = cv2.imencode('.jpg', image)
    img_base64 = base64.b64encode(buffer).decode('utf-8')

    response = http_requests.post(
        f"https://detect.roboflow.com/{ROBOFLOW_MODEL}",
        params={"api_key": ROBOFLOW_API_KEY, "confidence": 40, "overlap": 30},
        data=img_base64,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=20,
        verify=ROBOFLOW_SSL_VERIFY,
    )
    response.raise_for_status()
    result = response.json()

    detections = {}
    boxes = []
    annotated = image.copy()

    for pred in result.get('predictions', []):
        label = pred['class']
        conf = pred['confidence']
        x, y, w, h = int(pred['x']), int(pred['y']), int(pred['width']), int(pred['height'])
        x1, y1 = max(0, x - w // 2), max(0, y - h // 2)
        x2, y2 = min(image.shape[1], x + w // 2), min(image.shape[0], y + h // 2)

        detections[label] = detections.get(label, 0) + 1
        boxes.append({
            'label': label,
            'confidence': round(float(conf), 3),
            'x1': x1,
            'y1': y1,
            'x2': x2,
            'y2': y2,
        })
        color = COLORS[hash(label) % len(COLORS)]

        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 3)
        text = f"{label} {conf:.0%}"
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        label_top = max(0, y1 - th - 8)
        cv2.rectangle(annotated, (x1, label_top), (x1 + tw + 4, label_top + th + 8), color, -1)
        cv2.putText(annotated, text, (x1 + 2, label_top + th + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    return annotated, detections, boxes


def upload_image(request):
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'Authentication required'}, status=401)
    if request.method == 'POST' and request.FILES.get('image'):
        try:
            uploaded_file = request.FILES['image']
            if uploaded_file.size > 10 * 1024 * 1024:
                return JsonResponse({'status': 'error', 'message': 'Image too large. Max 10MB.'}, status=413)
            file_bytes = uploaded_file.read()
            try:
                with PILImage.open(BytesIO(file_bytes)) as probe:
                    if probe.width * probe.height > 16000000:
                        raise ValueError('Image exceeds 16 megapixels.')
                    probe.verify()
            except Exception:
                return JsonResponse({'status': 'error', 'message': 'Invalid image or image exceeds 16 megapixels.'}, status=400)
            np_arr = np.frombuffer(file_bytes, np.uint8)
            image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            if image is None:
                return JsonResponse({'status': 'error', 'message': 'Failed to read image'}, status=400)

            if not ROBOFLOW_API_KEY:
                return JsonResponse({'status': 'error', 'message': 'Detection service is not configured.'}, status=503)
            try:
                annotated_image, detections, boxes = detect_with_roboflow(image)
            except Exception:
                logger.error('Image detection service failed')
                return JsonResponse({'status': 'error', 'message': 'Image detection service failed. Please try again.'}, status=502)

            ok, out_buffer = cv2.imencode('.jpg', annotated_image)
            if not ok:
                return JsonResponse({'status': 'error', 'message': 'Failed to encode annotated image'}, status=500)

            img_base64 = base64.b64encode(out_buffer).decode('utf-8')
            annotated_image_url = f"data:image/jpeg;base64,{img_base64}"
            detected_objects = [{"label": label, "count": count} for label, count in detections.items()]

            source = request.POST.get('source', 'upload')
            if source != 'webcam':
                UploadHistory.objects.create(
                    user=request.user,
                    image=annotated_image_url,
                    detected_objects=json.dumps(detected_objects),
                    uploaded_at=now(),
                )
            return JsonResponse({
                'status': 'success',
                'annotated_image_url': annotated_image_url,
                'detected_objects': detected_objects,
                'boxes': boxes,
                'image_width': int(image.shape[1]),
                'image_height': int(image.shape[0]),
            })
        except Exception as e:
            logger.error('Image processing failed')
            return JsonResponse({'status': 'error', 'message': 'Image processing failed. Please try again.'}, status=500)

    return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)


def admin_login(request):
    if request.user.is_authenticated:
        if request.user.role == 'admin' and request.user.is_superuser:
            return redirect('admin_dashboard')
        return redirect('index')

    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '').strip()

        user = authenticate(request, email=email, password=password)
        if user is not None:
            if user.role == 'admin' and user.is_superuser:
                login(request, user, backend='vision.backends.EmailAuthBackend')
                messages.success(request, "Welcome, Admin!")
                return redirect('admin_dashboard')
            messages.error(request, 'You do not have admin privileges.')
            return redirect('admin_login')
        messages.error(request, 'Invalid email or password.')
        return redirect('admin_login')

    return render(request, 'admin_login.html')


@login_required
def delete_user(request, user_id):
    if not _is_admin(request.user):
        raise PermissionDenied("You do not have permission to delete users.")

    user = UserProfile.objects.filter(id=user_id).first()
    if not user:
        messages.error(request, "User not found.")
        return redirect('admin_dashboard')

    if request.method != 'POST':
        return HttpResponse(status=405, headers={'Allow': 'POST'})
    username = user.username
    user.delete()
    messages.success(request, f'User "{username}" has been deleted successfully!')
    return redirect('admin_dashboard')


@login_required
def edit_user(request, user_id):
    if not _is_admin(request.user):
        raise PermissionDenied("You do not have permission to edit users.")

    user = get_object_or_404(UserProfile, id=user_id, role="user")

    if request.method == 'POST':
        form = CustomUserForm(request.POST, instance=user)
        if form.is_valid():
            user = form.save(commit=False)
            if 'profile_image' in request.FILES:
                img = request.FILES['profile_image']
                img_data = base64.b64encode(img.read()).decode('utf-8')
                user.profile_image = f"data:{img.content_type};base64,{img_data}"
            user.save()
            messages.success(request, 'User updated successfully!')
            return redirect('admin_dashboard')
    else:
        form = CustomUserForm(instance=user)

    return render(request, 'edit_user.html', {'form': form, 'edit_user': user})


_model = None
_detector = None


def get_model():
    global _model
    if _model is None:
        from ultralytics import YOLO
        _model = YOLO('yolov8n.pt')
    return _model


def get_detector():
    global _detector
    if _detector is None:
        from .video_detect import YOLODetector
        _detector = YOLODetector()
    return _detector


def upload_video(request):
    """
    Process video: sample 20 frames via Roboflow, return annotated frames as
    base64 JPEG frames (and an optional MP4 data URL if imageio/ffmpeg is available).
    """
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'Authentication required'}, status=401)
    if request.method == 'POST' and request.FILES.get('video'):
        tmp_path = None
        cap = None
        try:
            if not ROBOFLOW_API_KEY:
                return JsonResponse({'status': 'error', 'message': 'Detection service is not configured.'}, status=503)
            video_file = request.FILES['video']
            if video_file.size > 50 * 1024 * 1024:
                return JsonResponse({'status': 'error', 'message': 'Video too large. Max 50MB.'}, status=413)

            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tmp:
                for chunk in video_file.chunks():
                    tmp.write(chunk)
                tmp_path = tmp.name

            cap = cv2.VideoCapture(tmp_path)
            if not cap.isOpened():
                return JsonResponse({'status': 'error', 'message': 'Could not read video file'}, status=400)

            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = max(1, int(cap.get(cv2.CAP_PROP_FPS) or 25))

            max_frames = 20
            step = max(1, total_frames // max_frames)

            annotated_frames = []
            all_detections = {}
            frame_idx = 0

            while len(annotated_frames) < max_frames:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame = cap.read()
                if not ret:
                    break

                h, w = frame.shape[:2]
                if w > 640:
                    scale = 640 / w
                    frame = cv2.resize(frame, (640, int(h * scale)))
                    frame_width, frame_height = 640, int(h * scale)

                _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                img_b64 = base64.b64encode(buf).decode('utf-8')

                try:
                    resp = http_requests.post(
                        f"https://detect.roboflow.com/{ROBOFLOW_MODEL}",
                        params={"api_key": ROBOFLOW_API_KEY, "confidence": 40, "overlap": 30},
                        data=img_b64,
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                        timeout=8,
                        verify=ROBOFLOW_SSL_VERIFY,
                    )
                    resp.raise_for_status()
                    result = resp.json()
                    if not isinstance(result.get('predictions'), list):
                        raise ValueError('Invalid detection response')
                    preds = result['predictions']
                    annotated = frame.copy()
                    for pred in preds:
                        label = pred['class']
                        conf = pred['confidence']
                        x, y, w2, h2 = int(pred['x']), int(pred['y']), int(pred['width']), int(pred['height'])
                        x1, y1 = max(0, x - w2 // 2), max(0, y - h2 // 2)
                        x2, y2 = min(frame_width, x + w2 // 2), min(frame_height, y + h2 // 2)
                        color = COLORS[hash(label) % len(COLORS)]
                        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 3)
                        text = f"{label} {conf:.0%}"
                        cv2.putText(annotated, text, (x1 + 2, max(y1 - 4, 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                        all_detections[label] = all_detections.get(label, 0) + 1
                except Exception:
                    logger.error('Video detection service failed')
                    return JsonResponse({'status': 'error', 'message': 'Video detection service failed. Please try again.'}, status=502)

                _, out_buf = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
                annotated_frames.append('data:image/jpeg;base64,' + base64.b64encode(out_buf).decode('utf-8'))
                frame_idx += step

            cap.release()
            cap = None

            if not annotated_frames:
                return JsonResponse({'status': 'error', 'message': 'Video contains no readable frames.'}, status=400)
            video_duration = total_frames / fps if total_frames > 0 else frame_idx / fps
            playback_fps = len(annotated_frames) / video_duration
            video_data_url = None
            if annotated_frames:
                try:
                    import imageio.v3 as iio
                    out_fps = playback_fps
                    frame_arrays = []
                    for fb64 in annotated_frames:
                        img = cv2.imdecode(np.frombuffer(base64.b64decode(fb64.split(',', 1)[1]), np.uint8), cv2.IMREAD_COLOR)
                        if img is not None:
                            frame_arrays.append(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))

                    if frame_arrays:
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tmp_out_f:
                            tmp_out = tmp_out_f.name
                        try:
                            iio.imwrite(
                                tmp_out,
                                frame_arrays,
                                fps=out_fps,
                                codec='libx264',
                                output_params=['-pix_fmt', 'yuv420p', '-movflags', '+faststart'],
                            )
                            with open(tmp_out, 'rb') as vf:
                                video_b64 = base64.b64encode(vf.read()).decode('utf-8')
                            video_data_url = 'data:video/mp4;base64,' + video_b64
                        finally:
                            if os.path.exists(tmp_out):
                                os.unlink(tmp_out)
                except Exception:
                    logger.debug("Optional MP4 encoding skipped; returning frame slideshow", exc_info=True)

            detected_objects = [{"label": k, "count": v} for k, v in all_detections.items()]
            return JsonResponse({
                'status': 'success',
                'frames': annotated_frames,
                'fps': playback_fps,
                'duration': round(video_duration, 2),
                'video_url': video_data_url,
                'detected_objects': detected_objects,
            })

        except Exception as e:
            logger.exception("Video processing error")
            return JsonResponse({'status': 'error', 'message': 'Video processing failed.'}, status=500)
        finally:
            if cap is not None:
                cap.release()
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)


@login_required
@require_POST
def delete_upload_history(request, upload_id):
    upload = get_object_or_404(UploadHistory, id=upload_id, user=request.user)
    try:
        upload.delete()
        messages.success(request, "Upload history entry deleted successfully.")
    except Exception as e:
        messages.error(request, f"An error occurred while deleting the history entry: {e}")

    return redirect('history')


@login_required
def admin_history(request):
    if not _is_admin(request.user):
        return redirect('index')

    all_uploads = UploadHistory.objects.select_related('user').all().order_by('-uploaded_at')
    context = []
    for upload in all_uploads:
        context.append({
            'id': upload.id,
            'image_url': upload.image or '',
            'detected_objects': _parse_detected_objects(upload.detected_objects),
            'uploaded_at': localtime(upload.uploaded_at).strftime('%d %b %Y, %I:%M %p') + ' IST',
            'uploaded_at_iso': localtime(upload.uploaded_at).strftime('%Y-%m-%d'),
            'username': upload.user.username,
            'email': upload.user.email,
        })
    return render(request, 'admin_history.html', {'all_uploads': context})


@login_required
def admin_delete_history(request, pk):
    if not _is_admin(request.user):
        raise PermissionDenied("You do not have permission to delete history.")

    if request.method != 'POST':
        return HttpResponse(status=405, headers={'Allow': 'POST'})
    history_item = get_object_or_404(UploadHistory, pk=pk)
    try:
        history_item.delete()
        messages.success(request, "History entry deleted successfully.")
    except Exception as e:
        messages.error(request, f"An error occurred while deleting the history entry: {e}")

    return redirect('admin_history')


@login_required
def admin_user_management(request):
    if not _is_admin(request.user):
        return redirect('index')

    users_qs = UserProfile.objects.filter(role="user").order_by('-id')
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    if start_date and end_date:
        start_d = parse_date(start_date)
        end_d = parse_date(end_date)
        if start_d and end_d:
            users_qs = users_qs.filter(date_joined__date__range=[start_d, end_d])

    context = {
        "users": users_qs,
        "total_users": users_qs.count(),
        "active_users": users_qs.filter(is_active=True).count(),
        "inactive_users": users_qs.filter(is_active=False).count(),
    }
    return render(request, "admin_dashboard.html", context)


@login_required
def filter_users(request):
    if not _is_admin(request.user):
        return JsonResponse({"error": "Unauthorized"}, status=403)

    start_date = request.GET.get('start')
    end_date = request.GET.get('end')

    if start_date and end_date:
        start_d = parse_date(start_date)
        end_d = parse_date(end_date)
        if start_d and end_d:
            users_qs = UserProfile.objects.filter(date_joined__date__range=[start_d, end_d], role="user")
            user_data = [
                {"username": u.username, "email": u.email, "date_joined": u.date_joined.strftime("%Y-%m-%d") if u.date_joined else ""}
                for u in users_qs
            ]
            return JsonResponse(user_data, safe=False)

    return JsonResponse({"error": "Invalid date range"}, status=400)


@login_required
def generate_report(request):
    if not _is_admin(request.user):
        raise PermissionDenied("Unauthorized")

    start_date = request.POST.get('start_date')
    end_date = request.POST.get('end_date')

    if bool(start_date) != bool(end_date):
        return JsonResponse({'error': 'Provide both start_date and end_date.'}, status=400)
    if start_date and end_date:
        try:
            start_d = datetime.strptime(start_date, "%Y-%m-%d").date()
            end_d = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            return JsonResponse({'error': 'Invalid date format. Use YYYY-MM-DD.'}, status=400)
        if start_d > end_d:
            return JsonResponse({'error': 'Start date must be before end date.'}, status=400)
        users_qs = UserProfile.objects.filter(date_joined__date__range=[start_d, end_d], role="user")
    else:
        users_qs = UserProfile.objects.filter(role="user")

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="user_report.pdf"'

    doc = SimpleDocTemplate(response, pagesize=landscape(letter))
    elements = []
    styles = getSampleStyleSheet()

    data = [["Sr. No", "Profile", "Username", "Name", "Email", "Phone", "Join Date", "Status"]]

    for index_num, user in enumerate(users_qs, start=1):
        img = "No Image"
        if user.profile_image and user.profile_image.startswith('data:image'):
            try:
                _, b64data = user.profile_image.split(',', 1)
                pil_img = PILImage.open(BytesIO(base64.b64decode(b64data))).convert("RGB")
                pil_img.thumbnail((60, 60))
                img_buf = BytesIO()
                pil_img.save(img_buf, format="JPEG")
                img_buf.seek(0)
                img = ReportLabImage(img_buf, width=40, height=40)
            except Exception:
                img = "No Image"

        status = Paragraph(f"<b>{'Active' if user.is_active else 'Inactive'}</b>", styles["Normal"])
        username = Paragraph(escape(user.username), styles["Normal"])
        name = Paragraph(escape(user.name or "-"), styles["Normal"])
        email = Paragraph(escape(user.email), styles["Normal"])
        phone = Paragraph(escape(user.phone or "-"), styles["Normal"])
        join_date = Paragraph(str(user.date_joined.date()) if user.date_joined else "-", styles["Normal"])

        data.append([index_num, img, username, name, email, phone, join_date, status])

    col_widths = [50, 60, 100, 100, 160, 100, 100, 80]
    table = Table(data, colWidths=col_widths)
    table.setStyle(TableStyle([
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('WORDWRAP', (0, 0), (-1, -1)),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]))

    elements.append(table)
    doc.build(elements)
    return response


@login_required
def generate_history_report(request):
    if not _is_admin(request.user):
        raise PermissionDenied("Unauthorized")

    start_date = request.POST.get('start_date')
    end_date = request.POST.get('end_date')

    if bool(start_date) != bool(end_date):
        return JsonResponse({'error': 'Provide both start_date and end_date.'}, status=400)
    if start_date and end_date:
        try:
            start_d = datetime.strptime(start_date, "%Y-%m-%d").date()
            end_d = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            return JsonResponse({'error': 'Invalid date format. Use YYYY-MM-DD.'}, status=400)
        if start_d > end_d:
            return JsonResponse({'error': 'Start date must be before end date.'}, status=400)
        uploads = UploadHistory.objects.select_related('user').filter(uploaded_at__date__range=[start_d, end_d])
    else:
        uploads = UploadHistory.objects.select_related('user').all()

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="history_report.pdf"'

    doc = SimpleDocTemplate(response, pagesize=letter)
    elements = []
    data = [["Sr.No", "Username", "Email", "Detected Objects", "Upload Date", "Image"]]

    for index_num, upload in enumerate(uploads, start=1):
        username = upload.user.username if upload.user else "N/A"
        email = upload.user.email if upload.user else "N/A"

        detected_list = _parse_detected_objects(upload.detected_objects)
        detected_objects = "\n".join(
            [f"{obj.get('label', '?')} ({obj.get('count', 0)})" for obj in detected_list if isinstance(obj, dict)]
        ) or "N/A"

        img_obj = "No Image"
        if upload.image and upload.image.startswith('data:image'):
            try:
                _, b64data = upload.image.split(',', 1)
                pil_img = PILImage.open(BytesIO(base64.b64decode(b64data))).convert("RGB")
                pil_img.thumbnail((60, 60))
                img_buf = BytesIO()
                pil_img.save(img_buf, format="JPEG")
                img_buf.seek(0)
                img_obj = ReportLabImage(img_buf, width=50, height=50)
            except Exception as e:
                logger.warning("Error decoding image for %s: %s", username, e)

        data.append([
            index_num,
            username,
            email,
            detected_objects,
            upload.uploaded_at.strftime("%Y-%m-%d"),
            img_obj,
        ])

    col_widths = [30, 80, 120, 150, 80, 60]
    table = Table(data, colWidths=col_widths)
    table.setStyle(TableStyle([
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (0, 0), (-1, 0), colors.gray),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))

    elements.append(table)
    elements.append(Spacer(1, 12))
    doc.build(elements)
    return response


@login_required
def generate_help_message_report(request):
    """Generate a help message report with full data visibility and proper word wrapping."""
    if not _is_admin(request.user):
        return JsonResponse({"error": "Unauthorized"}, status=403)

    if request.method == "POST":
        try:
            data = json.loads(request.body)
            start_date = parse_date(data.get("start_date", ""))
            end_date = parse_date(data.get("end_date", ""))
            help_messages = data.get("messages", [])

            if not start_date or not end_date or not help_messages:
                return JsonResponse({"error": "Invalid input data"}, status=400)

            buffer = BytesIO()
            response = HttpResponse(content_type="application/pdf")
            response["Content-Disposition"] = 'attachment; filename="help_message_report.pdf"'

            doc = SimpleDocTemplate(buffer, pagesize=letter)
            elements = []
            styles = getSampleStyleSheet()
            normal_style = styles["Normal"]
            normal_style.wordWrap = 'CJK'

            data_table = [["Sr.No", "Name", "Email", "Phone", "Subject", "Message", "Date"]]

            for index_num, message in enumerate(help_messages, start=1):
                name = Paragraph(escape(str(message.get("name", "N/A"))), normal_style)
                email = Paragraph(escape(str(message.get("email", "N/A"))), normal_style)
                phone = Paragraph(escape(str(message.get("phone", "N/A"))), normal_style)
                subject = Paragraph(escape(str(message.get("subject", "N/A"))), normal_style)
                msg_text = Paragraph(escape(str(message.get("message", "N/A"))), normal_style)
                date = Paragraph(escape(str(message.get("date", "N/A"))), normal_style)
                data_table.append([index_num, name, email, phone, subject, msg_text, date])

            col_widths = [40, 80, 120, 80, 80, 100, 80]
            table = Table(data_table, colWidths=col_widths)
            table.setStyle(TableStyle([
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]))

            elements.append(table)
            doc.build(elements)

            buffer.seek(0)
            response.write(buffer.read())
            return response

        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON format"}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Invalid request method"}, status=400)


@login_required
def generate_feedback_report(request):
    if not _is_admin(request.user):
        return JsonResponse({"error": "Unauthorized"}, status=403)

    if request.method == "POST":
        try:
            if "application/json" in (request.content_type or ""):
                data = json.loads(request.body)
                start_date = (data.get('start_date') or '').strip()
                end_date = (data.get('end_date') or '').strip()
            else:
                start_date = (request.POST.get('start_date') or '').strip()
                end_date = (request.POST.get('end_date') or '').strip()

            if not start_date or not end_date:
                return JsonResponse({"error": "Missing start_date or end_date"}, status=400)

            try:
                start_d = datetime.strptime(start_date, "%Y-%m-%d").date()
                end_d = datetime.strptime(end_date, "%Y-%m-%d").date()
                feedbacks = Feedback.objects.select_related('user').filter(created_at__date__range=[start_d, end_d])
            except ValueError:
                return JsonResponse({"error": "Invalid date format"}, status=400)

            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="feedback_report.pdf"'

            doc = SimpleDocTemplate(response, pagesize=letter)
            elements = []
            styles = getSampleStyleSheet()
            style_n = styles["Normal"]

            data = [["Sr.No", "User", "Feedback", "Created At"]]
            for index_num, feedback in enumerate(feedbacks, start=1):
                user = feedback.user.username if feedback.user else "Anonymous"
                feedback_text = Paragraph(escape(feedback.feedback), style_n)
                created_at = feedback.created_at.strftime("%Y-%m-%d %H:%M:%S")
                data.append([index_num, user, feedback_text, created_at])

            col_widths = [50, 100, 250, 120]
            table = Table(data, colWidths=col_widths)
            table.setStyle(TableStyle([
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('WORDWRAP', (2, 1), (2, -1)),
            ]))

            elements.append(table)
            doc.build(elements)
            return response

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Invalid request method"}, status=405)


@login_required
def help_message_filter(request):
    """View to filter help messages based on date range and search query."""
    if not _is_admin(request.user):
        return JsonResponse({"error": "Unauthorized"}, status=403)

    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    search_query = request.GET.get('search', '')

    help_messages = HelpMessage.objects.all().order_by('-created_at')
    if search_query:
        help_messages = help_messages.filter(name__icontains=search_query)

    if start_date and end_date:
        start_d = parse_date(start_date)
        end_d = parse_date(end_date)
        if start_d and end_d:
            help_messages = help_messages.filter(created_at__date__range=[start_d, end_d])

    message_data = [
        {
            "name": message.name,
            "email": message.email,
            "phone": message.phone_number,
            "subject": message.subject,
            "message": message.message,
            "date": message.created_at.strftime("%Y-%m-%d %H:%M"),
        }
        for message in help_messages
    ]
    return JsonResponse(message_data, safe=False)


@login_required
def users_feedback_filter(request):
    if not _is_admin(request.user):
        return redirect('index')

    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    feedbacks = Feedback.objects.select_related('user').all().order_by('-created_at')

    if start_date and end_date:
        start_d = parse_date(start_date)
        end_d = parse_date(end_date)
        if start_d and end_d:
            feedbacks = feedbacks.filter(created_at__date__range=[start_d, end_d])

    return render(request, 'user_feedback.html', {'feedbacks': feedbacks})


@login_required
def generate_report_history(request):
    if not _is_admin(request.user):
        return JsonResponse({"error": "Unauthorized"}, status=403)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="upload_history_report.csv"'

    writer = csv.writer(response)
    writer.writerow(["ID", "Username", "Email", "Detected Objects", "Uploaded At"])

    uploads = UploadHistory.objects.select_related('user').all().order_by('-uploaded_at')
    for upload in uploads:
        detected_objects = _parse_detected_objects(upload.detected_objects)
        detected_objects_str = ', '.join(
            [f"{obj.get('label', '?')} ({obj.get('count', 0)})" for obj in detected_objects if isinstance(obj, dict)]
        )
        writer.writerow([
            upload.id,
            upload.user.username,
            upload.user.email,
            detected_objects_str,
            upload.uploaded_at.strftime('%Y-%m-%d %H:%M:%S'),
        ])

    return response


@login_required
def filter_history(request):
    if not _is_admin(request.user):
        return JsonResponse({"error": "Unauthorized"}, status=403)

    start_date = request.GET.get('start')
    end_date = request.GET.get('end')
    search_query = request.GET.get('search')

    uploads = UploadHistory.objects.select_related('user').all()
    if start_date and end_date:
        start_d = parse_date(start_date)
        end_d = parse_date(end_date)
        if start_d and end_d:
            uploads = uploads.filter(uploaded_at__date__range=[start_d, end_d])

    if search_query:
        uploads = uploads.filter(user__username__icontains=search_query)

    upload_data = [
        {
            "id": upload.id,
            "username": upload.user.username,
            "email": upload.user.email,
            "image_url": upload.image or '',
            "detected_objects": _parse_detected_objects(upload.detected_objects),
            "uploaded_at": upload.uploaded_at.strftime("%Y-%m-%d"),
        }
        for upload in uploads
    ]
    return JsonResponse(upload_data, safe=False)


@login_required
def video_feed(request):
    return JsonResponse({'error': 'Use the webcam on the dashboard to access your browser camera.'}, status=410)


@login_required
@require_POST
def start_detection(request):
    return video_feed(request)


@login_required
@require_POST
def stop_detection(request):
    return video_feed(request)


@login_required
@require_POST
def stop_webcam(request):
    return video_feed(request)
