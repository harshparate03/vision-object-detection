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


    def test_otp_expiry_and_attempt_limit(self):
        import time
        for expiry, attempts in [(time.time() - 1, 0), (time.time() + 300, 5)]:
            session = self.client.session
            session.update({'user_id': self.user.id, 'otp_code': '123456', 'otp_verified': False,
                            'otp_expires_at': expiry, 'otp_attempts': attempts})
            session.save()
            response = self.client.post(reverse('verify_otp'), {'otp': '123456'})
            self.assertRedirects(response, reverse('forgot'))
            self.assertNotIn('otp_code', self.client.session)

    def test_delete_user_requires_post(self):
        self.client.force_login(self.admin)
        url = reverse('delete_user', args=[self.user.id])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertTrue(UserProfile.objects.filter(pk=self.user.pk).exists())
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertFalse(UserProfile.objects.filter(pk=self.user.pk).exists())

    def test_image_upload_requires_csrf(self):
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(reverse('upload_image')).status_code, 403)

    def test_image_dimension_limit_before_detection(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        image = BytesIO()
        Image.new('RGB', (4001, 4000)).save(image, format='PNG')
        self.client.force_login(self.user)
        with patch('vision.views.detect_with_roboflow') as detect:
            response = self.client.post(reverse('upload_image'), {
                'image': SimpleUploadedFile('large.png', image.getvalue(), content_type='image/png')})
        self.assertEqual(response.status_code, 400)
        detect.assert_not_called()

    def test_video_service_errors_are_not_success(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from unittest.mock import MagicMock
        import numpy as np
        self.client.force_login(self.user)
        capture = MagicMock()
        capture.isOpened.return_value = True
        capture.get.return_value = 25
        capture.read.return_value = (True, np.zeros((24, 24, 3), dtype=np.uint8))
        with patch('vision.views.ROBOFLOW_API_KEY', 'test'), \
             patch('vision.views.cv2.VideoCapture', return_value=capture), \
             patch('vision.views.http_requests.post') as post:
            post.return_value.raise_for_status.side_effect = RuntimeError('upstream failure')
            response = self.client.post(reverse('upload_video'), {
                'video': SimpleUploadedFile('test.mp4', b'test')})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()['status'], 'error')
        capture.release.assert_called_once()

    def test_legacy_camera_cannot_open_server_camera(self):
        with patch('vision.views.cv2.VideoCapture') as capture:
            self.assertEqual(self.client.get(reverse('video_feed')).status_code, 302)
            self.client.force_login(self.user)
            self.assertEqual(self.client.get(reverse('video_feed')).status_code, 410)
            self.assertEqual(self.client.get(reverse('start_detection')).status_code, 405)
            self.assertEqual(self.client.post(reverse('start_detection')).status_code, 410)
        capture.assert_not_called()


    def test_signin_and_dashboard_with_production_settings(self):
        from django.test import override_settings
        with override_settings(DEBUG=False, SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True):
            response = self.client.post(reverse('signin'), {
                'email': self.user.email, 'password': 'Password123!',
            }, secure=True)
            self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)
            dashboard = self.client.get(reverse('dashboard'), secure=True)
            self.assertEqual(dashboard.status_code, 200)


    def test_deactivated_session_is_rejected(self):
        self.client.force_login(self.user, backend='vision.backends.EmailAuthBackend')
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 302)
        from django.contrib.auth import authenticate
        self.assertIsNone(authenticate(email=self.user.email, password='Password123!'))

    def test_history_delete_requires_post_and_preserves_ownership(self):
        upload = UploadHistory.objects.create(user=self.user, image='', detected_objects='[]')
        self.client.force_login(self.user)
        own_url = reverse('delete_upload_history', args=[upload.pk])
        self.assertEqual(self.client.get(own_url).status_code, 405)
        self.assertTrue(UploadHistory.objects.filter(pk=upload.pk).exists())
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(own_url).status_code, 404)
        admin_url = reverse('admin_delete_history', args=[upload.pk])
        self.assertEqual(self.client.get(admin_url).status_code, 405)
        self.assertTrue(UploadHistory.objects.filter(pk=upload.pk).exists())
        self.assertEqual(self.client.post(admin_url).status_code, 302)
        self.assertFalse(UploadHistory.objects.filter(pk=upload.pk).exists())

    def test_report_rejects_invalid_reversed_and_partial_dates(self):
        self.client.force_login(self.admin)
        for route in ['generate_report', 'generate_history_report']:
            for dates in [
                {'start_date': 'bad-date', 'end_date': 'bad-date'},
                {'start_date': '2026-12-01', 'end_date': '2026-01-01'},
                {'start_date': '2026-01-01'},
            ]:
                self.assertEqual(self.client.post(reverse(route), dates).status_code, 400)

    def test_image_service_error_does_not_expose_credentials(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.force_login(self.user)
        with patch('vision.views.ROBOFLOW_API_KEY', 'private-key'), \
             patch('vision.views.detect_with_roboflow', side_effect=RuntimeError('url?api_key=private-key')):
            with self.assertLogs('vision', level='ERROR') as logs:
                response = self.client.post(reverse('upload_image'), {
                    'image': SimpleUploadedFile('image.jpg', self._jpeg_bytes(), content_type='image/jpeg')})
        self.assertEqual(response.status_code, 502)
        self.assertNotIn('private-key', response.content.decode())
        self.assertNotIn('private-key', ' '.join(logs.output))

    def test_web_admin_recovery_disabled_even_with_secret(self):
        from django.test import override_settings
        with override_settings(RESET_ADMIN_SECRET='configured-secret'):
            for route in ['db_setup', 'reset_admin']:
                self.assertEqual(self.client.get(reverse(route), {'secret': 'configured-secret'}).status_code, 403)
                self.assertEqual(self.client.post(reverse(route), {'secret': 'configured-secret'}).status_code, 403)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password('AdminPassword123!'))

    def test_sampled_video_keeps_original_duration(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from unittest.mock import MagicMock
        import cv2
        import numpy as np
        self.client.force_login(self.user)
        capture = MagicMock()
        capture.isOpened.return_value = True
        props = {cv2.CAP_PROP_FRAME_COUNT: 3000, cv2.CAP_PROP_FPS: 30,
                 cv2.CAP_PROP_FRAME_WIDTH: 24, cv2.CAP_PROP_FRAME_HEIGHT: 24}
        capture.get.side_effect = lambda prop: props[prop]
        capture.read.return_value = (True, np.zeros((24, 24, 3), dtype=np.uint8))
        with patch('vision.views.ROBOFLOW_API_KEY', 'test'), \
             patch('vision.views.cv2.VideoCapture', return_value=capture), \
             patch('vision.views.http_requests.post') as post, \
             patch.dict('sys.modules', {'imageio.v3': None}):
            post.return_value.json.return_value = {'predictions': []}
            response = self.client.post(reverse('upload_video'), {
                'video': SimpleUploadedFile('video.mp4', b'test')})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['frames']), 20)
        self.assertEqual(data['duration'], 100)
        self.assertAlmostEqual(len(data['frames']) / data['fps'], 100)


    def test_signup_applies_password_policy_and_phone_rules(self):
        from .forms import SignUpForm
        details = {'username': 'newuser', 'name': 'New User', 'email': 'new@example.com',
                   'phone': '9876543211', 'password': '12345678', 'confirm_password': '12345678'}
        form = SignUpForm(data=details)
        self.assertFalse(form.is_valid())
        self.assertIn('password', form.errors)
        details.update(password='Zebra!River92#Moon', confirm_password='Zebra!River92#Moon')
        for phone in ['123456789', '1' * 16, 'abc', '+919876543210', '9876543211']:
            details['phone'] = phone
            form = SignUpForm(data=details)
            self.assertEqual(form.is_valid(), phone in ['+919876543210', '9876543211'], form.errors)

    def test_profile_rejects_invalid_and_duplicate_details(self):
        self.client.force_login(self.user)
        original = (self.user.email, self.user.phone, self.user.name)
        for changes in [
            {'email': 'invalid-email'}, {'phone': 'abc'}, {'phone': '123456789'},
            {'email': self.admin.email}, {'phone': self.admin.phone}, {'name': 'x' * 256},
        ]:
            details = {'name': 'Alice', 'email': self.user.email, 'phone': self.user.phone}
            details.update(changes)
            self.assertEqual(self.client.post(reverse('view_profile'), details).status_code, 302)
            self.user.refresh_from_db()
            self.assertEqual((self.user.email, self.user.phone, self.user.name), original)
        self.client.post(reverse('view_profile'), {
            'name': 'Alice Updated', 'email': 'updated@example.com', 'phone': '+919876543211'})
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'updated@example.com')
        self.assertEqual(self.user.phone, '+919876543211')

    def test_profile_upload_verifies_content_and_uses_actual_mime(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.force_login(self.user)
        response = self.client.post(reverse('upload_profile_image_ajax'), {
            'profile_image': SimpleUploadedFile('fake.png', b'not an image', content_type='image/png')})
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertFalse(self.user.profile_image)
        response = self.client.post(reverse('upload_profile_image_ajax'), {
            'profile_image': SimpleUploadedFile('real.png', self._jpeg_bytes(), content_type='image/png')})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['image_url'].startswith('data:image/jpeg;base64,'))

    def test_all_pdf_reports_fit_page_width(self):
        import json
        from reportlab.platypus import Table as RealTable
        Feedback.objects.create(user=self.user, feedback='Long feedback ' * 30)
        UploadHistory.objects.create(user=self.user, detected_objects='[{"label":"person","count":1}]')
        self.client.force_login(self.admin)
        cases = [
            ('generate_report', {}, 648),
            ('generate_history_report', {}, 468),
            ('generate_feedback_report', {'start_date': '2000-01-01', 'end_date': '2100-01-01'}, 468),
            ('generate_help_message_report', {'start_date': '2000-01-01', 'end_date': '2100-01-01',
              'messages': [{'name': 'Alice', 'email': 'alice@example.com', 'phone': '9876543210',
                            'subject': 'Help', 'message': 'Long message ' * 30, 'date': '2026-11-25'}]}, 468),
        ]
        for route, payload, available_width in cases:
            with patch('vision.views.Table', wraps=RealTable) as table:
                if route == 'generate_help_message_report':
                    response = self.client.post(reverse(route), json.dumps(payload), content_type='application/json')
                else:
                    response = self.client.post(reverse(route), payload)
            self.assertEqual(response.status_code, 200, route)
            self.assertTrue(response.content.startswith(b'%PDF'), route)
            self.assertAlmostEqual(sum(table.call_args.kwargs['colWidths']), available_width)
            self.assertEqual(table.call_args.kwargs['repeatRows'], 1)
