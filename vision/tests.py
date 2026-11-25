import base64
from io import BytesIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from .models import Feedback, HelpMessage, UploadHistory, UserProfile


class VisionSecurityAndFlowTests(TestCase):
    def setUp(self):
        self.user = UserProfile.objects.create_user(
            username='alice',
            email='alice@example.com',
            name='Alice',
            phone='9876543210',
            password='Password123!',
        )
        self.admin = UserProfile.objects.create_superuser(
            username='adminuser',
            email='admin@example.com',
            name='Admin',
            phone='9123456780',
            password='AdminPassword123!',
        )

    def test_superuser_has_persisted_is_staff(self):
        refreshed = UserProfile.objects.get(pk=self.admin.pk)
        self.assertTrue(refreshed.is_staff)
        self.assertTrue(refreshed.is_superuser)
        self.assertEqual(refreshed.role, 'admin')

    def test_login_url_redirect_from_nested_route(self):
        resp = self.client.get(reverse('edit_user', args=[self.user.id]))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.url.startswith('/signin/'))

    def test_otp_bypass_blocked(self):
        session = self.client.session
        session['user_id'] = self.user.id
        session.save()

        # Without verifying OTP, password_reset must redirect to forgot
        resp = self.client.get(reverse('password_reset'))
        self.assertRedirects(resp, reverse('forgot'))

        # Empty OTP post must not verify even if otp_code is missing
        resp_verify = self.client.post(reverse('verify_otp'), {'otp': ''})
        self.assertRedirects(resp_verify, reverse('forgot'))

    def test_otp_verification_flow(self):
        with patch('vision.views.send_sms') as mock_sms:
            resp = self.client.post(reverse('forgot'), {'phone_number': '9876543210'})
            self.assertRedirects(resp, reverse('verify_otp'))
            mock_sms.assert_called_once()

        otp_code = self.client.session['otp_code']
        resp = self.client.post(reverse('verify_otp'), {'otp': otp_code})
        self.assertRedirects(resp, reverse('password_reset'))

        resp = self.client.post(
            reverse('password_reset'),
            {'new_password': 'NewStrongPassword99!', 'confirm_password': 'NewStrongPassword99!'},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context['success'])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewStrongPassword99!'))

    def test_anonymous_cannot_upload_image_or_submit_feedback(self):
        img_buf = BytesIO()
        Image.new('RGB', (10, 10), color='red').save(img_buf, format='JPEG')
        img_buf.seek(0)
        resp_img = self.client.post(reverse('upload_image'), {'image': img_buf})
        self.assertEqual(resp_img.status_code, 401)

        resp_fb = self.client.post(reverse('submit_feedback'), {'feedback': 'Nice!'})
        self.assertEqual(resp_fb.status_code, 401)

    def test_regular_user_blocked_from_admin_pages(self):
        self.client.force_login(self.user)
        for name in [
            'admin_dashboard',
            'admin_history',
            'admin_user_management',
            'help_message',
            'users_feedback',
            'users',
        ]:
            resp = self.client.get(reverse(name))
            self.assertRedirects(resp, reverse('index'), target_status_code=302)

        resp_del = self.client.get(reverse('delete_user', args=[self.user.id]))
        self.assertEqual(resp_del.status_code, 403)

    def test_admin_pages_and_reports_work(self):
        UploadHistory.objects.create(
            user=self.user,
            image='data:image/jpeg;base64,' + base64.b64encode(self._jpeg_bytes()).decode('ascii'),
            detected_objects='[{"label": "person", "count": 2}]',
        )
        UploadHistory.objects.create(
            user=self.user,
            image=None,
            detected_objects='{"car": 1}',
        )
        Feedback.objects.create(user=self.user, feedback='Great <app> & fast!')
        HelpMessage.objects.create(
            name='Alice',
            email='alice@example.com',
            phone_number='9876543210',
            subject='Help & Support',
            message='Need help <pls>',
        )

        self.client.force_login(self.admin)
        for name in [
            'admin_dashboard',
            'admin_history',
            'admin_user_management',
            'help_message',
            'users_feedback',
            'users',
        ]:
            resp = self.client.get(reverse(name))
            self.assertEqual(resp.status_code, 200, f"{name} returned {resp.status_code}")

        resp_user_pdf = self.client.post(reverse('generate_report'))
        self.assertEqual(resp_user_pdf.status_code, 200)
        self.assertEqual(resp_user_pdf['Content-Type'], 'application/pdf')

        resp_hist_pdf = self.client.post(reverse('generate_history_report'))
        self.assertEqual(resp_hist_pdf.status_code, 200)
        self.assertEqual(resp_hist_pdf['Content-Type'], 'application/pdf')

    def test_clear_stale_images_preserves_valid_base64(self):
        data_url = 'data:image/jpeg;base64,' + base64.b64encode(self._jpeg_bytes()).decode('ascii')
        self.user.profile_image = data_url
        self.user.save(update_fields=['profile_image'])

        call_command('clear_stale_images')
        self.user.refresh_from_db()
        self.assertEqual(self.user.profile_image, data_url)

    def test_history_handles_malformed_detected_objects(self):
        UploadHistory.objects.create(user=self.user, image='', detected_objects='not-valid-literal')
        self.client.force_login(self.user)
        resp = self.client.get(reverse('history'))
        self.assertEqual(resp.status_code, 200)

    def test_reset_admin_requires_env_secret(self):
        resp = self.client.get('/db_setup/?secret=vision_reset_2024')
        self.assertEqual(resp.status_code, 403)

    @staticmethod
    def _jpeg_bytes():
        buf = BytesIO()
        Image.new('RGB', (10, 10), color='blue').save(buf, format='JPEG')
        return buf.getvalue()
