from django.http import HttpResponse
from vision.models import UserProfile


def reset_admin_password(request):
    """
    One-time setup view — creates or resets the admin account.
    Protected by a secret key in the URL.

    Usage:
      /reset_admin/?secret=vision_reset_2024
      /reset_admin/?secret=vision_reset_2024&email=admin@email.com&password=Admin@1234
    """
    secret = request.GET.get('secret', '')
    if secret != 'vision_reset_2024':
        return HttpResponse('Unauthorized', status=403)

    email    = request.GET.get('email',    'admin@email.com')
    password = request.GET.get('password', 'Admin@1234')
    username = request.GET.get('username', 'admin')
    name     = request.GET.get('name',     'Harsh')
    phone    = request.GET.get('phone',    '9712341503')

    try:
        user = UserProfile.objects.filter(email=email).first()

        if not user:
            # Create brand new admin
            user = UserProfile.objects.create_superuser(
                username=username,
                email=email,
                name=name,
                phone=phone,
                password=password,
            )
            user.role        = 'admin'
            user.is_staff    = True
            user.is_superuser = True
            user.save()
            return HttpResponse(
                f'✅ Admin created!<br>'
                f'Email: {email}<br>'
                f'Password: {password}<br>'
                f'<a href="/admin_login/">Go to Admin Login</a>'
            )
        else:
            # Reset existing user password and make admin
            user.set_password(password)
            user.role        = 'admin'
            user.is_staff    = True
            user.is_superuser = True
            user.save()
            return HttpResponse(
                f'✅ Admin updated!<br>'
                f'Email: {user.email}<br>'
                f'Password: {password}<br>'
                f'<a href="/admin_login/">Go to Admin Login</a>'
            )

    except Exception as e:
        return HttpResponse(f'❌ Error: {str(e)}', status=500)
