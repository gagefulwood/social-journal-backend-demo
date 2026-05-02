from django.conf import settings
from django.urls import reverse
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
import pyotp

from users.models import Users


class AuthCookieTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.password = 'Password123!'
        self.user = Users.objects.create_user(
            email='casey@example.com',
            username='casey',
            first_name='Casey',
            last_name='Example',
            password=self.password,
        )

    def login(self):
        return self.client.post(
            reverse('auth-token'),
            {'identifier': self.user.email, 'password': self.password},
            format='json',
        )

    def assert_auth_cookies(self, response, *, refresh_expected=True):
        access_name = settings.JWT_ACCESS_COOKIE_NAME
        self.assertIn(access_name, response.cookies)
        access_cookie = response.cookies[access_name]
        self.assertEqual(
            access_cookie['max-age'],
            int(settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'].total_seconds()),
        )
        self.assertTrue(access_cookie['httponly'])
        self.assertEqual(bool(access_cookie['secure']), settings.JWT_COOKIE_SECURE)
        self.assertEqual(access_cookie['samesite'], settings.JWT_COOKIE_SAMESITE)

        if refresh_expected:
            refresh_name = settings.JWT_REFRESH_COOKIE_NAME
            self.assertIn(refresh_name, response.cookies)
            refresh_cookie = response.cookies[refresh_name]
            self.assertEqual(
                refresh_cookie['max-age'],
                int(settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds()),
            )
            self.assertTrue(refresh_cookie['httponly'])
            self.assertEqual(bool(refresh_cookie['secure']), settings.JWT_COOKIE_SECURE)
            self.assertEqual(refresh_cookie['samesite'], settings.JWT_COOKIE_SAMESITE)

    def assert_no_token_body(self, response):
        self.assertNotIn('access', response.data)
        self.assertNotIn('refresh', response.data)
        self.assertNotIn('access_token', response.data)
        self.assertNotIn('refresh_token', response.data)

    def test_login_sets_http_only_cookies_and_returns_metadata_only(self):
        response = self.login()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assert_auth_cookies(response)
        self.assert_no_token_body(response)
        self.assertEqual(response.data['user_id'], self.user.id)
        self.assertEqual(response.data['email'], self.user.email)
        self.assertEqual(response.data['username'], self.user.username)
        self.assertFalse(response.data['is_mfa_enabled'])
        self.assertFalse(response.data['mfa_pending'])
        self.assertEqual(response.data['role'], 'Standard User')

    def test_access_cookie_authenticates_protected_endpoint(self):
        login_response = self.login()
        self.client.cookies[settings.JWT_ACCESS_COOKIE_NAME] = (
            login_response.cookies[settings.JWT_ACCESS_COOKIE_NAME].value
        )

        response = self.client.get(reverse('user-profile'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], self.user.email)

    def test_authorization_header_does_not_authenticate_without_cookie(self):
        token = RefreshToken.for_user(self.user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        response = self.client.get(reverse('user-profile'))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_reads_refresh_cookie_and_rotates_cookies(self):
        login_response = self.login()
        old_refresh = login_response.cookies[settings.JWT_REFRESH_COOKIE_NAME].value
        self.client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = old_refresh

        response = self.client.post(reverse('auth-token-refresh'), {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assert_auth_cookies(response)
        self.assert_no_token_body(response)
        self.assertEqual(response.data['user_id'], self.user.id)
        self.assertNotEqual(
            response.cookies[settings.JWT_REFRESH_COOKIE_NAME].value,
            old_refresh,
        )

    def test_refresh_blacklists_old_refresh_cookie_after_rotation(self):
        login_response = self.login()
        old_refresh = login_response.cookies[settings.JWT_REFRESH_COOKIE_NAME].value
        self.client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = old_refresh

        first_response = self.client.post(
            reverse('auth-token-refresh'),
            {},
            format='json',
        )
        self.assertEqual(first_response.status_code, status.HTTP_200_OK)

        self.client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = old_refresh
        second_response = self.client.post(
            reverse('auth-token-refresh'),
            {},
            format='json',
        )

        self.assertEqual(second_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_rejects_malformed_cookie(self):
        self.client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = 'not-a-jwt'

        response = self.client.post(reverse('auth-token-refresh'), {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data['detail'], 'Refresh token is invalid.')

    def test_refresh_rejects_body_token_without_cookie(self):
        refresh = RefreshToken.for_user(self.user)

        response = self.client.post(
            reverse('auth-token-refresh'),
            {'refresh': str(refresh)},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data['detail'], 'Refresh cookie is required.')

    def test_protected_endpoint_requires_access_cookie(self):
        response = self.client.get(reverse('user-profile'))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_blacklists_refresh_cookie_and_clears_cookies(self):
        login_response = self.login()
        self.client.cookies[settings.JWT_ACCESS_COOKIE_NAME] = (
            login_response.cookies[settings.JWT_ACCESS_COOKIE_NAME].value
        )
        self.client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = (
            login_response.cookies[settings.JWT_REFRESH_COOKIE_NAME].value
        )

        response = self.client.post(reverse('auth-logout'), {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['detail'], 'Logged out')
        self.assertEqual(response.cookies[settings.JWT_ACCESS_COOKIE_NAME]['max-age'], 0)
        self.assertEqual(response.cookies[settings.JWT_REFRESH_COOKIE_NAME]['max-age'], 0)

        refresh_response = self.client.post(
            reverse('auth-token-refresh'),
            {},
            format='json',
        )
        self.assertEqual(refresh_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_rejects_get_with_method_not_allowed(self):
        login_response = self.login()
        self.client.cookies[settings.JWT_ACCESS_COOKIE_NAME] = (
            login_response.cookies[settings.JWT_ACCESS_COOKIE_NAME].value
        )

        response = self.client.get(reverse('auth-logout'))

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_mfa_verify_sets_cookies_and_returns_metadata_only(self):
        secret = pyotp.random_base32()
        self.user.mfa_secret = secret
        self.user.save(update_fields=['mfa_secret'])
        refresh = RefreshToken.for_user(self.user)
        self.client.cookies[settings.JWT_ACCESS_COOKIE_NAME] = str(refresh.access_token)

        response = self.client.post(
            reverse('auth-mfa-verify'),
            {'totp_code': pyotp.TOTP(secret).now()},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assert_auth_cookies(response)
        self.assert_no_token_body(response)
        self.assertEqual(response.data['detail'], 'MFA successfully enabled.')
        self.assertTrue(response.data['is_mfa_enabled'])
        self.assertFalse(response.data['mfa_pending'])
