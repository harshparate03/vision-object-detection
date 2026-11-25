import base64
import os
from django.conf import settings
from django.core.management.base import BaseCommand
from vision.models import UserProfile


class Command(BaseCommand):
    help = 'Clear malformed or missing profile image DB references'

    def handle(self, *args, **kwargs):
        cleared = 0
        for user in UserProfile.objects.exclude(profile_image='').exclude(profile_image=None):
            val = user.profile_image.strip()
            valid = False
            if val.startswith('data:image/') and ';base64,' in val:
                try:
                    _, b64data = val.split(',', 1)
                    base64.b64decode(b64data, validate=True)
                    valid = True
                except Exception:
                    valid = False
            else:
                path = os.path.join(settings.MEDIA_ROOT, val)
                valid = os.path.exists(path)

            if not valid:
                user.profile_image = None
                user.save(update_fields=['profile_image'])
                self.stdout.write(f'Cleared broken image for: {user.username}')
                cleared += 1
        self.stdout.write(self.style.SUCCESS(f'Done. Cleared {cleared} broken profile image(s).'))
