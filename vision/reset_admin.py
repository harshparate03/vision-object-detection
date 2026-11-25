from django.http import HttpResponse


def db_setup(request):
    """Retired: migrations run at startup; use Django admin CLI for recovery."""
    return HttpResponse('Web admin recovery is disabled. Use createsuperuser or changepassword on the server.', status=403)


def reset_admin_password(request):
    return db_setup(request)
