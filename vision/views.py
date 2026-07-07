from django.shortcuts import render,redirect,get_object_or_404
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash 
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.contrib import messages
from django.contrib.auth import login
from .forms import SignUpForm,CustomUserForm
from .sms_utils import send_sms
import logging
import re
from datetime import datetime
import random
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from django.contrib.auth.decorators import login_required
from django.conf import settings  # required by dashboard and other views
# detect_objects imported lazily in views
import ast
from django.utils.timezone import localtime
from datetime import timedelta
from .models import UploadHistory, UserProfile, HelpMessage, Feedback


# Logger setup for tracking sign-in attempts
logger = logging.getLogger(__name__)

def index(request):
    return render(request, 'index.html')

@login_required
def history(request):
    user_uploads = UploadHistory.objects.filter(user=request.user)
    context = []
    for upload in user_uploads:
        detected_objects = ast.literal_eval(upload.detected_objects)  # Safely parse the string
        context.append({
            'id':upload.id,
            'image_url': upload.image if upload.image else '',
            'detected_objects': detected_objects,
            'uploaded_at': (upload.uploaded_at + __import__('datetime').timedelta(hours=5, minutes=30)).strftime('%d %b %Y, %I:%M %p') + ' IST',
            'username': upload.user.username
        })
    return render(request, 'history.html', {'user_uploads': context})

def dashboard(request):
    if not request.user.is_authenticated:
        return redirect('/signin/')  # Redirect to your login page

    return render(request, 'dashboard.html'  ,{'media_url': settings.MEDIA_URL})

@login_required
def test(request):
    return render(request, 'test.html')

from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.shortcuts import render, redirect

def signin(request):
    if request.method == 'POST':
        # Clear previous messages before adding a new one
        list(messages.get_messages(request))  

        email = request.POST['email']
        password = request.POST['password']

        print(f"Email: {email}, Password: {password}")

        user = authenticate(request, email=email, password=password)
        print(f"Authenticated User: {user}")

        if user is not None:
            if user.is_active:
                login(request, user)
                messages.success(request, "You're logged in")
                return redirect('dashboard')
            else:
                messages.error(request, "You are not allowed to log in. Contact admin.")
                return redirect('signin')
        else:
            messages.error(request, 'Invalid email or password')
            return redirect('signin')

    return render(request, 'signin.html')

def logout_user(request):
    logout(request)  # Log out user and clear session
    
    # Clear previous messages before adding a new one
    list(messages.get_messages(request))  

    messages.success(request, 'You have been logged out. <br>Please Sign in again')
    return redirect('index')  # Redirect to the sign-in page

def signup(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            # Save the form but don't commit (so we can customize user creation)
            user = form.save(commit=False)
            # Set the password (hash it properly)
            user.password = make_password(form.cleaned_data['password'])
            # code for joining date add in database 
            # user.joining_date = Date.now
            user.save()  # Save the user instance
            # Authenticate using the credentials provided
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            user = authenticate(email=email, password=password)  # Ensure backend supports email authentication
            if user is not None:
                login(request, user)
                messages.success(request, 'You\'re now registered!')
                return redirect('signin')  # Redirect after successful registration
            else:
                messages.error(request, 'Error during authentication. Please try logging in manually.')
                return redirect('signin')
    else:
        form = SignUpForm()

    context = {'form': form}
    return render(request, 'signup.html', context)

User = get_user_model()

def forgot(request):
    error_message = None  # Variable to store error messages
    if request.method == 'POST':
        phone_number = request.POST.get('phone_number')
        
        # Validate phone number using a regular expression (adjust regex for your requirements)
        phone_pattern = r'^\+?[0-9]{10,15}$'
        if not re.match(phone_pattern, phone_number):
            error_message = "Invalid phone number format. Please enter a valid number."
            return render(request, 'forgot.html', {'error': error_message})
        
        try:
            # Ensure the phone number field is correctly named in your User model
            user = UserProfile.objects.get(phone=phone_number)
            
            # Store user ID in the session for later use
            request.session['user_id'] = user.id
            
            # for static otp
            # otp_code = "123456"
            
            # Generate a random 6-digit OTP Dynamic
            
            otp_code = f"{random.randint(100000, 999999)}"
            send_sms(phone_number, f"Your OTP is: {otp_code}")  # Send SMS (implement your SMS sending function)
            
            # Optionally store the OTP in the session (you could use a database instead)
            request.session['otp_code'] = otp_code
            
            return redirect('verify_otp')
        except User.DoesNotExist:
            error_message = "User with this phone number does not exist."
    
    # Render the form with error messages if validation fails
    return render(request, 'forgot.html', {'error': error_message})

def verify_otp(request):
    if request.method == 'POST':
        # Get the entered OTP and the session OTP
        entered_otp = request.POST.get('otp')
        # for key, value in request.session.items():
        #     print(f"{key}: {value}")
        generated_otp = request.session.get('otp_code')  # Get OTP from session
        
        if entered_otp == generated_otp:
            return redirect('password_reset')
            # return render(request, 'password_reset.html')  # Go to the password reset page
        else:
            print("nooooooooo")
            return render(request, 'verify_otp.html', {'error': 'Invalid OTP'})
    
    return render(request, 'verify_otp.html')


def contact(request):
    return render(request, 'contact.html')

def about(request):
    return render(request, 'about.html')

def services(request):
    return render(request, 'services.html')


def password_reset(request):
    if request.method == 'POST':
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')
        
        if new_password != confirm_password:
            return render(request, 'password_reset.html', {'error': 'Passwords do not match.'})
        
        try:
            validate_password(new_password)
        except ValidationError as e:
            return render(request, 'password_reset.html', {'error': ' '.join(e.messages)})
        
        user_id = request.session.get('user_id')
        if not user_id:
            return redirect('signin')
        
        try:
            from .models import UserProfile
            user = UserProfile.objects.get(id=user_id)
        except UserProfile.DoesNotExist:
            return redirect('signin')
        
        if check_password(new_password, user.password):
            return render(request, 'password_reset.html', {'error': 'New password cannot be the same as the old password.'})
        
        user.set_password(new_password)
        user.save()
        update_session_auth_hash(request, user)
        # Show success message with auto-redirect
        return render(request, 'password_reset.html', {'success': True})
    
    return render(request, 'password_reset.html')


from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from django.contrib import messages
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import UserProfile  # Import the model

@login_required
def remove_profile_image(request):
    if request.method != 'POST':
        return redirect('view_profile')
    user = request.user
    user.profile_image = None
    user.save(update_fields=['profile_image'])
    from django.http import JsonResponse
    from django.templatetags.static import static
    return JsonResponse({'success': True, 'default_url': static('images/default.jpg')})


@login_required
def upload_profile_image_ajax(request):
    from django.http import JsonResponse
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
        import base64
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
        new_name = request.POST.get("name")
        new_email = request.POST.get("email")
        new_phone = request.POST.get("phone")

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


from django.contrib.auth.decorators import login_required
from django.contrib.auth import update_session_auth_hash
from django.contrib import messages
from django.shortcuts import render, redirect

@login_required
def change_password(request):
    if request.method == 'POST':
        current_password = request.POST.get('currentpassword')
        new_password = request.POST.get('newpassword')
        confirm_password = request.POST.get('retypenewpassword')

        user = request.user

        # Check if current password is correct
        if not user.check_password(current_password):
            messages.error(request, "Current password is incorrect.")
            return redirect('change_password')

        # Prevent reuse of old password
        if user.check_password(new_password):
            messages.error(request, "New password cannot be the same as the old password.")
            return redirect('change_password')

        # Check password length
        if len(new_password) < 8:
            messages.error(request, "New password must be at least 8 characters long.")
            return redirect('change_password')

        # Confirm new passwords match
        if new_password != confirm_password:
            messages.error(request, "New passwords do not match.")
            return redirect('change_password')

        # Update password
        user.set_password(new_password)
        user.save()

        # Keep user logged in after password change
        update_session_auth_hash(request, user)
        messages.success(request, "Password updated successfully!")
        return redirect('change_password')

    return render(request, 'change_password.html')

from django.shortcuts import render, redirect
from django.contrib.auth import logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required

@login_required
def delete_account(request):
    if request.method == "POST":
        password = request.POST.get("password")

        # Verify the user's password before deletion
        if request.user.check_password(password):  # Check if entered password matches

            # Delete the user from the database
            user = request.user
            user.delete()

            # Log out the user after deletion
            logout(request)

            # Show success message
            messages.success(request, "Your account has been deleted successfully.")
            
            # Redirect to homepage or login page
            return redirect('signin')  # Adjust this to your desired redirect page

        else:
            # Show error message if password is incorrect
            messages.error(request, "Your password is incorrect. Please try again.")
    
    return render(request, "delete_account.html")


from django.shortcuts import render, redirect
from django.http import JsonResponse
from .forms import HelpMessageForm
from .models import HelpMessage

def help_center(request):
    return render(request, "help_center.html")

def submit_message(request):
    if request.method == "POST":
        form = HelpMessageForm(request.POST)
        if form.is_valid():
            form.save()
            return JsonResponse({"success": True, "message": "Message sent successfully!"})
        else:
            errors = {field: error.get_json_data() for field, error in form.errors.items()}
            return JsonResponse({"success": False, "message": "Validation errors", "errors": errors})
    return JsonResponse({"success": False, "message": "Invalid request"})



def terms_policy(request):
    return render(request, 'terms_policy.html')

from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import FeedbackForm
from django.apps import apps
from .models import Feedback


from django.http import JsonResponse

def submit_feedback(request):
    if request.method == 'POST':
        form = FeedbackForm(request.POST)
        if form.is_valid():
            # Save the feedback to the database
            feedback = form.save(commit=False)
            feedback.user = request.user  # Assign the logged-in user
            feedback.save()  # Save the feedback object
            return JsonResponse({"success": True, "message": "Message sent successfully!"})
        else:
            errors = {field: error.get_json_data() for field, error in form.errors.items()}
            return JsonResponse({"success": False, "message": "Validation errors", "errors": errors})
    
    return JsonResponse({"success": False, "message": "Invalid request"})


from django.shortcuts import render
from .models import UserProfile

def admin_dashboard(request):
    if not request.user.is_authenticated:
        return redirect('/') 
    
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


from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.utils.dateparse import parse_date
from .models import HelpMessage

@login_required
def help_message_view(request):
    """ View to display help messages with search and filtering capabilities """
    help_messages = HelpMessage.objects.all().order_by('-created_at')

    search_query = request.GET.get('search', '')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    if search_query:
        help_messages = help_messages.filter(name__icontains=search_query)

    if start_date and end_date:
        start_date = parse_date(start_date)
        end_date = parse_date(end_date)
        if start_date and end_date:
            help_messages = help_messages.filter(created_at__date__range=[start_date, end_date])

    return render(request, 'help_message.html', {'help_messages': help_messages})

from django.shortcuts import render
from .models import Feedback

def users_feedback_view(request):
    feedbacks = Feedback.objects.all()
    return render(request, 'user_feedback.html', {'feedbacks': feedbacks})

from django.shortcuts import render
from .models import UserProfile

def users(request):
    users = UserProfile.objects.all()
    return render(request, 'users.html', {'users': users})


import logging
import os
from django.shortcuts import render
from django.http import JsonResponse
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
import cv2
import numpy as np
import base64
import requests as http_requests
import urllib3

# Disable SSL warnings globally — needed on Windows where the system CA store
# is not used by Python's ssl module by default
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configure logging
logger = logging.getLogger(__name__)

ROBOFLOW_API_KEY = os.environ.get("ROBOFLOW_API_KEY", "")
ROBOFLOW_MODEL = "coco/17"  # Latest COCO YOLOv8 model

COLORS = [
    (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0),
    (0, 255, 255), (255, 0, 255), (128, 255, 0), (255, 128, 0),
    (0, 128, 255), (128, 0, 255)
]

def detect_with_roboflow(image):
    """Send image to Roboflow API and return annotated image + detections"""
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    _, buffer = cv2.imencode('.jpg', image)
    img_base64 = base64.b64encode(buffer).decode('utf-8')

    response = http_requests.post(
        f"https://detect.roboflow.com/{ROBOFLOW_MODEL}",
        params={"api_key": ROBOFLOW_API_KEY, "confidence": 40, "overlap": 30},
        data=img_base64,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        verify=False
    )
    response.raise_for_status()
    result = response.json()
    print(f"Roboflow predictions: {result.get('predictions', [])}")

    detections = {}
    annotated = image.copy()
    label_list = []

    for pred in result.get('predictions', []):
        label = pred['class']
        conf = pred['confidence']
        x, y, w, h = int(pred['x']), int(pred['y']), int(pred['width']), int(pred['height'])
        x1, y1 = max(0, x - w // 2), max(0, y - h // 2)
        x2, y2 = min(image.shape[1], x + w // 2), min(image.shape[0], y + h // 2)

        detections[label] = detections.get(label, 0) + 1
        label_list.append(label)

        color_idx = hash(label) % len(COLORS)
        color = COLORS[color_idx]

        # Draw thick bounding box
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 3)

        # Draw label background
        text = f"{label} {conf:.0%}"
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(annotated, (x1, y1 - th - 8), (x1 + tw + 4, y1), color, -1)
        cv2.putText(annotated, text, (x1 + 2, y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    return annotated, detections

from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
def upload_image(request):
    if request.method == 'POST' and request.FILES.get('image'):
        try:
            import os
            from django.conf import settings as django_settings
            os.makedirs(django_settings.MEDIA_ROOT, exist_ok=True)

            uploaded_file = request.FILES['image']
            file_bytes = uploaded_file.read()
            file_name = default_storage.save(uploaded_file.name, ContentFile(file_bytes))
            file_path = default_storage.path(file_name)

            image = cv2.imread(file_path)
            if image is None:
                return JsonResponse({'status': 'error', 'message': 'Failed to read image'}, status=400)

            annotated_image, detections = detect_with_roboflow(image)

            # Return as base64 data URL
            _, out_buffer = cv2.imencode('.jpg', annotated_image)
            img_base64 = base64.b64encode(out_buffer).decode('utf-8')
            annotated_image_url = f"data:image/jpeg;base64,{img_base64}"

            detected_objects = [{"label": label, "count": count} for label, count in detections.items()]

            from .models import UploadHistory
            from django.utils.timezone import now
            import base64 as _b64
            annotated_b64 = "data:image/jpeg;base64," + _b64.b64encode(out_buffer.tobytes()).decode('utf-8')
            UploadHistory.objects.create(
                user=request.user,
                image=annotated_b64,
                detected_objects=str(detected_objects),
                uploaded_at=now()
            )
            return JsonResponse({
                'status': 'success',
                'annotated_image_url': annotated_image_url,
                'detected_objects': detected_objects
            })
        except Exception as e:
            logger.exception("Error processing image")
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)


from django.contrib.auth import authenticate, login
from django.shortcuts import redirect, render
from django.contrib import messages

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
            else:
                messages.error(request, 'You do not have admin privileges.')
                return redirect('admin_login')
        else:
            messages.error(request, 'Invalid email or password.')
            return redirect('admin_login')

    return render(request, 'admin_login.html')


from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

@login_required
def delete_user(request, user_id):
    # Fetch user directly without raising 404
    user = UserProfile.objects.filter(id=user_id).first()

    # If user does not exist, show an error message
    if not user:
        messages.error(request, "User not found.")
        return redirect('admin_dashboard')

    # Ensure only admins can delete users
    if request.user.role != 'admin':
        raise PermissionDenied("You do not have permission to delete users.")

    username = user.username
    user.delete()
    messages.success(request, f'User "{username}" has been deleted successfully!')
    
    return redirect('admin_dashboard')

@login_required
def edit_user(request, user_id):
    user = get_object_or_404(UserProfile, id=user_id, role="user")

    if request.method == 'POST':
        form = CustomUserForm(request.POST, instance=user)
        if form.is_valid():
            user = form.save(commit=False)
            if 'profile_image' in request.FILES:
                import base64
                img = request.FILES['profile_image']
                img_data = base64.b64encode(img.read()).decode('utf-8')
                user.profile_image = f"data:{img.content_type};base64,{img_data}"
            user.save()
            messages.success(request, 'User updated successfully!')
            return redirect('admin_dashboard')
    else:
        form = CustomUserForm(instance=user)

    return render(request, 'edit_user.html', {'form': form, 'edit_user': user})



import os
import cv2
import time
from django.shortcuts import render
from django.http import JsonResponse
from django.core.files.storage import default_storage
from django.conf import settings
# YOLO imported lazily in get_model()

import os
from django.conf import settings
from django.http import JsonResponse
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.urls import reverse
from .video_detect import YOLODetector
from django.utils.http import urlsafe_base64_encode

# Lazy load model and detector
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
        _detector = YOLODetector()
    return _detector

import os
from django.conf import settings
from django.core.files.storage import default_storage
from django.http import JsonResponse
import urllib.parse  

def upload_video(request):
    """
    Process video: sample 20 frames via Roboflow, return annotated frames as
    a GIF-style slideshow encoded as base64 JPEG frames in JSON.
    Avoids disk storage entirely — works on Render ephemeral filesystem.
    """
    if request.method == 'POST' and request.FILES.get('video'):
        try:
            import base64 as _b64
            import tempfile

            video_file = request.FILES['video']

            if video_file.size > 50 * 1024 * 1024:
                return JsonResponse({'status': 'error', 'message': 'Video too large. Max 50MB.'})

            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tmp:
                for chunk in video_file.chunks():
                    tmp.write(chunk)
                tmp_path = tmp.name

            cap = cv2.VideoCapture(tmp_path)
            if not cap.isOpened():
                os.unlink(tmp_path)
                return JsonResponse({'status': 'error', 'message': 'Could not read video file'})

            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            frame_width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps          = max(1, int(cap.get(cv2.CAP_PROP_FPS) or 25))

            # Sample exactly 20 evenly-spaced frames
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

                # Resize to max 640px wide for speed
                h, w = frame.shape[:2]
                if w > 640:
                    scale = 640 / w
                    frame = cv2.resize(frame, (640, int(h * scale)))
                    frame_width, frame_height = 640, int(h * scale)

                _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                img_b64 = _b64.b64encode(buf).decode('utf-8')

                try:
                    import urllib3
                    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                    resp = http_requests.post(
                        f"https://detect.roboflow.com/{ROBOFLOW_MODEL}",
                        params={"api_key": ROBOFLOW_API_KEY, "confidence": 40, "overlap": 30},
                        data=img_b64,
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                        timeout=8,
                        verify=False
                    )
                    preds = resp.json().get('predictions', [])
                    annotated = frame.copy()
                    for pred in preds:
                        label = pred['class']
                        conf  = pred['confidence']
                        x, y, w2, h2 = int(pred['x']), int(pred['y']), int(pred['width']), int(pred['height'])
                        x1, y1 = max(0, x - w2//2), max(0, y - h2//2)
                        x2, y2 = min(frame_width, x + w2//2), min(frame_height, y + h2//2)
                        color = COLORS[hash(label) % len(COLORS)]
                        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 3)
                        text = f"{label} {conf:.0%}"
                        cv2.putText(annotated, text, (x1+2, max(y1-4,10)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2)
                        all_detections[label] = all_detections.get(label, 0) + 1
                except Exception:
                    annotated = frame

                _, out_buf = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
                annotated_frames.append('data:image/jpeg;base64,' + _b64.b64encode(out_buf).decode('utf-8'))

                frame_idx += step

            cap.release()

            # Build annotated mp4 in memory and return as base64 data URL
            import numpy as np
            import base64 as _b64v
            import tempfile as _tmpfile
            video_data_url = None
            if annotated_frames:
                try:
                    first_data = annotated_frames[0].split(',')[1]
                    first_img = cv2.imdecode(np.frombuffer(_b64v.b64decode(first_data), np.uint8), cv2.IMREAD_COLOR)
                    if first_img is not None:
                        out_fps = min(fps, 10)
                        fh, fw = first_img.shape[:2]

                        # Decode frames to RGB numpy arrays
                        frame_arrays = []
                        for fb64 in annotated_frames:
                            img = cv2.imdecode(np.frombuffer(_b64v.b64decode(fb64.split(',')[1]), np.uint8), cv2.IMREAD_COLOR)
                            if img is not None:
                                frame_arrays.append(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))

                        if frame_arrays:
                            import imageio.v3 as iio
                            tmp_out = _tmpfile.mktemp(suffix='.mp4')
                            iio.imwrite(
                                tmp_out,
                                frame_arrays,
                                fps=out_fps,
                                codec='libx264',
                                output_params=['-pix_fmt', 'yuv420p', '-movflags', '+faststart']
                            )
                            with open(tmp_out, 'rb') as vf:
                                video_b64 = _b64v.b64encode(vf.read()).decode('utf-8')
                            os.unlink(tmp_out)
                            video_data_url = 'data:video/mp4;base64,' + video_b64
                except Exception:
                    pass

            os.unlink(tmp_path)

            detected_objects = [{"label": k, "count": v} for k, v in all_detections.items()]
            return JsonResponse({
                'status': 'success',
                'frames': annotated_frames,
                'fps': min(fps, 10),
                'video_url': video_data_url,
                'detected_objects': detected_objects
            })

        except Exception as e:
            logger.exception("Video processing error")
            return JsonResponse({'status': 'error', 'message': str(e)})

    return JsonResponse({'status': 'error', 'message': 'Invalid request'})

def process_video(request):
    if request.method == "POST" and request.FILES.get("video"):
        video_file = request.FILES["video"]
        user = request.user  # Ensure user is logged in

        # Save uploaded video
        upload_folder = os.path.join(settings.MEDIA_ROOT, "videos")
        os.makedirs(upload_folder, exist_ok=True)
        video_path = os.path.join(upload_folder, video_file.name)

        with open(video_path, "wb+") as destination:
            for chunk in video_file.chunks():
                destination.write(chunk)

        # Process video
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return JsonResponse({"error": "Invalid video file"}, status=400)

        output_folder = os.path.join(settings.MEDIA_ROOT, "outputs")
        os.makedirs(output_folder, exist_ok=True)
        output_filename = video_file.name.replace(".mp4", "_detected.mp4")
        output_path = os.path.join(output_folder, output_filename)

        frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = int(cap.get(cv2.CAP_PROP_FPS) or 30)

        writer = cv2.VideoWriter(output_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (frame_width, frame_height))

        detections = {}

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            results = get_model()(frame, imgsz=640, conf=0.3)
            for result in results:
                for box in result.boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    class_name = get_model().names[int(box.cls)]
                    color = (0, 255, 0)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(frame, class_name, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

                    detections[class_name] = detections.get(class_name, 0) + 1

            writer.write(frame)

        cap.release()
        writer.release()

        # Save to database
        UploadHistory.objects.create(
            user=user,
            image=os.path.join("outputs", output_filename),
            detected_objects=json.dumps(detections),
        )

        return JsonResponse({
            "message": "Video processed successfully",
            "video_url": os.path.join(settings.MEDIA_URL, "outputs", output_filename),
            "detections": detections
        })

    return JsonResponse({"error": "Invalid request"}, status=400)


from django.shortcuts import render, redirect
from .models import UploadHistory
from django.utils.timezone import now

def image_detect_view(request):
    if request.method == 'POST':
        image = request.FILES.get('image')
        # Run YOLO detection here and get the result
        detection_result = detect_objects(image)  # Replace with your YOLO code

        # Save to history
        UploadHistory.objects.create(
            user=request.user,
            image=image,
            detected_objects=detection_result,
            uploaded_at=now()
        )
        return render(request, 'dashboard.html', {'result': detection_result})

    return render(request, 'image_upload.html')

def upload_history(request):
    history = UploadHistory.objects.filter(user=request.user).order_by('-uploaded_at')
    return render(request, 'upload_history.html', {'history': history})


@login_required
def delete_upload_history(request, upload_id):
    upload = get_object_or_404(UploadHistory, id=upload_id, user=request.user)
    try:
        upload.delete()
        messages.success(request, "Upload history entry deleted successfully.")
    except Exception as e:
        messages.error(request, f"An error occurred while deleting the history entry: {e}")
    
    return redirect('history')
    
def admin_history(request):
    all_uploads = UploadHistory.objects.all().order_by('-uploaded_at')  # Fetch all uploads, newest first
    context = []
    for upload in all_uploads:
        detected_objects = ast.literal_eval(upload.detected_objects)
        context.append({
            'id': upload.id,
            'image_url': upload.image if upload.image else '',
            'detected_objects': detected_objects,
            'uploaded_at': (upload.uploaded_at + __import__('datetime').timedelta(hours=5, minutes=30)).strftime('%d %b %Y, %I:%M %p') + ' IST',
            'username': upload.user.username,
            'email': upload.user.email,
        })
    return render(request, 'admin_history.html', {'all_uploads': context})


def admin_delete_history(request, pk):
    history_item = get_object_or_404(UploadHistory, pk=pk)

    try:
        history_item.delete()
        messages.success(request, "History entry deleted successfully.")
    except Exception as e:
        messages.error(request, f"An error occurred while deleting the history entry: {e}")

    return redirect('admin_history')

from django.shortcuts import render, redirect
from django.utils.dateparse import parse_date
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from reportlab.pdfgen import canvas
import io

@login_required
def admin_user_management(request):
    if not request.user.is_superuser:
        return redirect('home')  # Redirect non-admin users
    
    users = UserProfile.objects.filter(role="user")

    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    if start_date and end_date:
        users = users.filter(date_joined__date__range=[parse_date(start_date), parse_date(end_date)])

    context = {
        "users": users,
        "total_users": users.count(),
        "active_users": users.filter(is_active=True).count(),
        "inactive_users": users.filter(is_active=False).count(),
    }
    return render(request, "admin_user_management.html", context)

@login_required
def filter_users(request):
    if not request.user.is_superuser:
        return JsonResponse({"error": "Unauthorized"}, status=403)

    start_date = request.GET.get('start')
    end_date = request.GET.get('end')

    if start_date and end_date:
        users = UserProfile.objects.filter(date_joined__date__range=[start_date, end_date], role="user")
        user_data = [{"username": user.username, "email": user.email, "date_joined": user.date_joined.strftime("%Y-%m-%d")} for user in users]
        return JsonResponse(user_data, safe=False)

    return JsonResponse({"error": "Invalid date range"}, status=400)

from django.shortcuts import render
from django.http import HttpResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from datetime import datetime


from django.http import HttpResponse
from datetime import datetime
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Image, Paragraph
from reportlab.platypus import Image as PlatypusImage

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from django.core.files.storage import default_storage

def generate_report(request):
    start_date = request.POST.get('start_date')
    end_date = request.POST.get('end_date')

    print(start_date, "==========", end_date)  # Debugging

    # Convert date format
    if start_date and end_date:
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
        users = UserProfile.objects.filter(date_joined__date__range=[start_date, end_date], role="user")
    else:
        users = UserProfile.objects.filter(role="user")

    # PDF response setup
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="user_report.pdf"'

    # Create PDF document in landscape mode
    doc = SimpleDocTemplate(response, pagesize=landscape(letter))
    elements = []
    styles = getSampleStyleSheet()

    # Table Header
    data = [["Sr. No", "Profile", "Username", "Name", "Email", "Phone", "Join Date", "Status"]]

    for index, user in enumerate(users, start=1):
        profile_image_path = None  # profile_image is now base64 text, not a file path

        # Profile image handling
        if profile_image_path and default_storage.exists(profile_image_path):
            # img = Image(profile_image_path, width=40, height=40)  # Resize image
            img = PlatypusImage(profile_image_path, width=40, height=40)

        else:
            img = "No Image"

        status = Paragraph(f"<b>{'Active' if user.is_active else 'Inactive'}</b>", styles["Normal"])

        # Wrap text for long values
        username = Paragraph(user.username, styles["Normal"])
        name = Paragraph(user.name if user.name else "-", styles["Normal"])
        email = Paragraph(user.email, styles["Normal"])
        phone = Paragraph(user.phone if user.phone else "-", styles["Normal"])
        join_date = Paragraph(str(user.date_joined.date()) if user.date_joined else "-", styles["Normal"])

        data.append([index, img, username, name, email, phone, join_date, status])

    # Column Widths (Adjusted to fit content properly)
    col_widths = [50, 60, 100, 100, 160, 100, 100, 80]  # Increased Sr.No and Status column width

    # Create Table
    table = Table(data, colWidths=col_widths)

    # Table Styling
    table.setStyle(TableStyle([
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),  # Header text color
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),  # Header background
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),  # Center align text
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),  # Bold header text
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),  # Padding for header
        ('GRID', (0, 0), (-1, -1), 1, colors.black),  # Grid for all cells
        ('WORDWRAP', (0, 0), (-1, -1)),  # Wrap text inside cells
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),  # Align content to middle
        ('LEFTPADDING', (0, 0), (-1, -1), 5),  # Add padding inside cells
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]))

    elements.append(table)
    doc.build(elements)

    return response

import ast
import os
from datetime import datetime
from django.http import HttpResponse
from django.conf import settings
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Image, Spacer
from reportlab.platypus import Image as ReportLabImage
from reportlab.lib import colors
from PIL import Image as PILImage
from io import BytesIO
from .models import UploadHistory

def generate_history_report(request):
    print("Received request:", request)

    start_date = request.POST.get('start_date')
    end_date = request.POST.get('end_date')

    print("Selected Date Range:", start_date, "to", end_date)

    # Convert to proper date format
    if start_date and end_date:
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
        uploads = UploadHistory.objects.filter(uploaded_at__date__range=[start_date, end_date])
    else:
        uploads = UploadHistory.objects.all()

    # PDF response setup
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="history_report.pdf"'

    # Create PDF document
    doc = SimpleDocTemplate(response, pagesize=letter)
    elements = []

    # Define Table Header
    data = [["Sr.No", "Username", "Email", "Detected Objects", "Upload Date", "Image"]]  

    # Populate table data
    image_paths = []  # Store temp image paths for cleanup

    for index, upload in enumerate(uploads, start=1):
        # Get username and email from related User model
        username = upload.user.username if upload.user else "N/A"
        email = upload.user.email if upload.user else "N/A"

        # Convert detected_objects string to list safely
        try:
            detected_objects_list = ast.literal_eval(upload.detected_objects)  
            detected_objects = "\n".join([f"{obj['label']} ({obj['count']})" for obj in detected_objects_list])
        except Exception as e:
            print("Error parsing detected_objects:", e)
            detected_objects = "N/A"  

        # Fetch Image (stored as base64 data URL, not a file path)
        img_obj = "No Image"
        if upload.image and upload.image.startswith('data:image'):
            try:
                import base64 as _b64
                header, b64data = upload.image.split(',', 1)
                img_bytes = _b64.b64decode(b64data)
                pil_img = PILImage.open(BytesIO(img_bytes))
                pil_img.thumbnail((60, 60))
                temp_img_path = os.path.join(settings.MEDIA_ROOT, f"temp_{index}.jpg")
                pil_img.save(temp_img_path)
                image_paths.append(temp_img_path)
                img_obj = ReportLabImage(temp_img_path, width=50, height=50)
            except Exception as e:
                print(f"Error decoding image for {username}: {e}")

        # Append data to table (align text properly)
        data.append([
            index, 
            username, 
            email, 
            detected_objects, 
            upload.uploaded_at.strftime("%Y-%m-%d"), 
            img_obj
        ])

    # Define column widths to avoid text overflow
    col_widths = [30, 80, 120, 150, 80, 60]  

    # Create Table
    table = Table(data, colWidths=col_widths)  
    table.setStyle(TableStyle([
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),  
        ('BACKGROUND', (0, 0), (-1, 0), colors.gray),  
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),  
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),  
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),  
        ('GRID', (0, 0), (-1, -1), 1, colors.black),  
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')  # Ensures images align properly
    ]))

    elements.append(table)
    elements.append(Spacer(1, 12))  

    doc.build(elements)

    # Cleanup temp images
    for temp_path in image_paths:
        if os.path.exists(temp_path):
            os.remove(temp_path)  

    return response




import json
from datetime import datetime
from io import BytesIO
from django.http import HttpResponse, JsonResponse
from django.utils.dateparse import parse_date
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet

def generate_help_message_report(request):
    """ Generate a help message report with full data visibility and proper word wrapping. """
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            start_date = parse_date(data.get("start_date"))
            end_date = parse_date(data.get("end_date"))
            help_messages = data.get("messages", [])

            if not start_date or not end_date or not help_messages:
                return JsonResponse({"error": "Invalid input data"}, status=400)

            # PDF response setup
            buffer = BytesIO()
            response = HttpResponse(content_type="application/pdf")
            response["Content-Disposition"] = 'attachment; filename="help_message_report.pdf"'

            # Create PDF document
            doc = SimpleDocTemplate(buffer, pagesize=letter)
            elements = []

            # Define styles
            styles = getSampleStyleSheet()
            normal_style = styles["Normal"]
            normal_style.wordWrap = 'CJK'  # Ensures text wrapping

            # Table Headers
            data_table = [
                ["Sr.No", "Name", "Email", "Phone", "Subject", "Message", "Date"]
            ]  # Table Header

            # Populate Table Rows
            for index, message in enumerate(help_messages, start=1):
                name = Paragraph(message.get("name", "N/A"), normal_style)
                email = Paragraph(message.get("email", "N/A"), normal_style)
                phone = Paragraph(message.get("phone", "N/A"), normal_style)
                subject = Paragraph(message.get("subject", "N/A"), normal_style)
                msg_text = Paragraph(message.get("message", "N/A"), normal_style)  # Wrap text properly
                date = Paragraph(message.get("date", "N/A"), normal_style)

                data_table.append([index, name, email, phone, subject, msg_text, date])

            # Create Table with Dynamic Column Widths
            col_widths = [40, 80, 120, 80, 80, 100, 80]  # Adjusted column widths

            table = Table(data_table, colWidths=col_widths)

            # Apply Table Style
            table.setStyle(TableStyle([
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),  # Header text color
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),  # Align text to left
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),  # Header background
                ('GRID', (0, 0), (-1, -1), 1, colors.black),  # Grid lines
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),  # Align content to the top
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


import json
from datetime import datetime
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from .models import Feedback

def generate_feedback_report(request):
    if request.method == "POST":
        try:
            # Check if request is JSON or Form
            if request.content_type == "application/json":
                data = json.loads(request.body)
                start_date = data.get('start_date', '').strip()
                end_date = data.get('end_date', '').strip()
            else:
                start_date = request.POST.get('start_date', '').strip()
                end_date = request.POST.get('end_date', '').strip()

            if not start_date or not end_date:
                return JsonResponse({"error": "Missing start_date or end_date"}, status=400)

            try:
                start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
                end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
                feedbacks = Feedback.objects.filter(created_at__date__range=[start_date, end_date])
            except ValueError:
                return JsonResponse({"error": "Invalid date format"}, status=400)

            # PDF response setup
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="feedback_report.pdf"'

            # Create PDF document
            doc = SimpleDocTemplate(response, pagesize=letter)
            elements = []

            # Define styles
            styles = getSampleStyleSheet()
            styleN = styles["Normal"]

            # Table Data with Headers
            data = [["Sr.No", "User", "Feedback", "Created At"]]  # Table Header

            for index, feedback in enumerate(feedbacks, start=1):
                user = feedback.user.username if feedback.user else "Anonymous"
                feedback_text = Paragraph(feedback.feedback, styleN)  # Wrap text
                created_at = feedback.created_at.strftime("%Y-%m-%d %H:%M:%S")

                data.append([index, user, feedback_text, created_at])

            # Create Table with Column Widths
            col_widths = [50, 100, 250, 120]  # Adjust widths for better formatting
            table = Table(data, colWidths=col_widths)

            # Apply Table Style
            table.setStyle(TableStyle([
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),  # Header color
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),  # Header background
                ('GRID', (0, 0), (-1, -1), 1, colors.black),  # Grid lines
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),  # Align vertically
                ('WORDWRAP', (2, 1), (2, -1)),  # Wrap text in Feedback column
            ]))

            elements.append(table)
            doc.build(elements)

            return response

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Invalid request method"}, status=405)


from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils.dateparse import parse_date

@login_required
def help_message_filter(request):
    """ View to filter help messages based on date range and search query """
    if not request.user.is_superuser:
        return JsonResponse({"error": "Unauthorized"}, status=403)

    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    search_query = request.GET.get('search', '')

    help_messages = HelpMessage.objects.all().order_by('-created_at')

    if search_query:
        help_messages = help_messages.filter(name__icontains=search_query)

    if start_date and end_date:
        start_date = parse_date(start_date)
        end_date = parse_date(end_date)
        if start_date and end_date:
            help_messages = help_messages.filter(created_at__date__range=[start_date, end_date])

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


from django.shortcuts import render
from django.utils.dateparse import parse_date
from .models import Feedback  # Ensure this matches your model name

def users_feedback_filter(request):
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    feedbacks = Feedback.objects.all()

    if start_date and end_date:
        start_date = parse_date(start_date)
        end_date = parse_date(end_date)

        if start_date and end_date:
            feedbacks = feedbacks.filter(created_at__date__range=[start_date, end_date])

    return render(request, 'user_feedback.html', {'feedbacks': feedbacks})

import csv
from django.http import HttpResponse

@login_required
def generate_report_history(request):
    if not request.user.is_superuser:
        return JsonResponse({"error": "Unauthorized"}, status=403)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="upload_history_report.csv"'

    writer = csv.writer(response)
    writer.writerow(["ID", "Username", "Email", "Detected Objects", "Uploaded At"])

    uploads = UploadHistory.objects.all().order_by('-uploaded_at')

    for upload in uploads:
        detected_objects = ast.literal_eval(upload.detected_objects) if upload.detected_objects else []
        detected_objects_str = ', '.join([f"{obj['label']} ({obj['count']})" for obj in detected_objects])
        writer.writerow([upload.id, upload.user.username, upload.user.email, detected_objects_str, upload.uploaded_at.strftime('%Y-%m-%d %H:%M:%S')])

    return response


@login_required
def filter_history(request):
    if not request.user.is_superuser:
        return JsonResponse({"error": "Unauthorized"}, status=403)

    start_date = request.GET.get('start')
    end_date = request.GET.get('end')
    search_query = request.GET.get('search')

    uploads = UploadHistory.objects.all()

    if start_date and end_date:
        uploads = uploads.filter(uploaded_at__date__range=[parse_date(start_date), parse_date(end_date)])

    if search_query:
        uploads = uploads.filter(user__username__icontains=search_query)

    upload_data = [
        {
            "id": upload.id,
            "username": upload.user.username,
            "email": upload.user.email,
            "image_url": upload.image if upload.image else '',
            "detected_objects": ast.literal_eval(upload.detected_objects) if upload.detected_objects else [],
            "uploaded_at": upload.uploaded_at.strftime("%Y-%m-%d"),
        }
        for upload in uploads
    ]

    return JsonResponse(upload_data, safe=False)



from django.shortcuts import render
from django.http import StreamingHttpResponse, JsonResponse, HttpResponse
import cv2
import os
from PIL import Image
import numpy as np
from .object import detect_objects  # Import from detect.py

# Global variables
cap = None
is_detecting = False

def generate_frames():
    """Continuously capture frames from the webcam and apply object detection if enabled."""
    global cap, is_detecting
    if cap is None:
        cap = cv2.VideoCapture(0)  # Open webcam

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        if is_detecting:
            frame, _ = detect_objects(frame)  # Apply object detection

        success, buffer = cv2.imencode('.jpg', frame)
        if not success:
            continue  # Skip if encoding fails

        frame_bytes = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

def video_feed(request):
    """Streams video from webcam."""
    return StreamingHttpResponse(generate_frames(), content_type="multipart/x-mixed-replace; boundary=frame")

def start_detection(request):
    """Starts object detection."""
    global is_detecting
    is_detecting = True
    return JsonResponse({"message": "Detection started"})

def stop_detection(request):
    """Stops object detection but keeps webcam open."""
    global is_detecting
    is_detecting = False
    return JsonResponse({"message": "Detection stopped"})

def stop_webcam(request):
    """Stops webcam completely."""
    global cap
    if cap and cap.isOpened():
        cap.release()
        cap = None
    return JsonResponse({"message": "Webcam stopped"})

import cv2
from django.http import JsonResponse
from PIL import Image
import os

cap = None  # Global variable to store the webcam instance

def save_screenshot(request):
    """Captures and saves a screenshot from the webcam."""
    global cap
    if cap is None or not cap.isOpened():
        cap = cv2.VideoCapture(0)  # Open webcam if not already running

    ret, frame = cap.read()  # Capture a frame
    if not ret:
        return JsonResponse({"error": "Failed to capture screenshot"}, status=500)

    # Save as PNG initially
    filename_png = "screenshot.png"
    filename_jpg = "screenshot.jpg"

    cv2.imwrite(filename_png, frame)

    # Convert PNG to JPEG to avoid format issues
    try:
        img = Image.open(filename_png)
        img = img.convert("RGB")
        img.save(filename_jpg, "JPEG", quality=95)
        os.remove(filename_png)  # Remove original PNG to keep only JPEG
    except Exception as e:
        return JsonResponse({"error": f"Image conversion failed: {str(e)}"}, status=500)

    return JsonResponse({"message": "Screenshot saved successfully", "filename": filename_jpg})
