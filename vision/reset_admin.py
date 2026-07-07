from django.http import HttpResponse
from django.db import connection
from django.core.management import call_command
import io


def db_setup(request):
    """
    Emergency setup — checks DB, runs migrations, creates admin.
    Usage: /db_setup/?secret=vision_reset_2024
    """
    secret = request.GET.get('secret', '')
    if secret != 'vision_reset_2024':
        return HttpResponse('Unauthorized', status=403)

    output = []

    # Step 1: Check DB connection
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT version();")
            version = cursor.fetchone()
            output.append(f"✅ DB connected: {version[0][:80]}")
    except Exception as e:
        return HttpResponse(f"❌ DB connection failed: {e}", status=500)

    # Step 2: Run migrations
    try:
        buf = io.StringIO()
        call_command('migrate', '--noinput', stdout=buf, stderr=buf)
        result = buf.getvalue()
        output.append(f"✅ Migrations complete.")
        output.append(result[:500])
    except Exception as e:
        output.append(f"⚠️ Migration error: {e}")

    # Step 3: Create admin
    from vision.models import UserProfile
    email    = request.GET.get('email',    'admin@email.com')
    password = request.GET.get('password', 'Admin@1234')
    username = request.GET.get('username', 'admin')
    name     = request.GET.get('name',     'Harsh')
    phone    = request.GET.get('phone',    '9712341503')

    try:
        user = UserProfile.objects.filter(email=email).first()
        if not user:
            user = UserProfile.objects.create_superuser(
                username=username, email=email,
                name=name, phone=phone, password=password,
            )
            user.role = 'admin'
            user.is_staff = True
            user.is_superuser = True
            user.save()
            output.append(f"✅ Admin created — {email} / {password}")
        else:
            user.set_password(password)
            user.role = 'admin'
            user.is_staff = True
            user.is_superuser = True
            user.save()
            output.append(f"✅ Admin updated — {email} / {password}")
    except Exception as e:
        output.append(f"❌ Admin creation failed: {e}")

    html = "<br><br>".join(output)
    html += '<br><br><a href="/admin_login/" style="color:lime;font-size:18px;">→ Go to Admin Login</a>'
    return HttpResponse(html)


def reset_admin_password(request):
    """Alias for db_setup for backward compatibility."""
    return db_setup(request)
