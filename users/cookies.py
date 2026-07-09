from django.conf import settings


def role_for_user(user):
    try:
        return user.groups.first().name if user.groups.exists() else 'Standard User'
    except Exception:
        return 'Standard User'


def mfa_pending_for_user(user):
    return user.is_mfa_enabled and not settings.DISABLE_MFA_REQUIREMENT


def build_auth_metadata(user, *, mfa_pending=None):
    if mfa_pending is None:
        mfa_pending = mfa_pending_for_user(user)
    return {
        'user_id': user.id,
        'email': user.email,
        'username': user.username,
        'is_mfa_enabled': user.is_mfa_enabled,
        'mfa_pending': mfa_pending,
        'role': role_for_user(user),
    }


def set_token_cookies(response, access_token, refresh_token=None):
    response.set_cookie(
        settings.JWT_ACCESS_COOKIE_NAME,
        str(access_token),
        max_age=int(settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'].total_seconds()),
        httponly=settings.JWT_COOKIE_HTTPONLY,
        secure=settings.JWT_COOKIE_SECURE,
        samesite=settings.JWT_COOKIE_SAMESITE,
        path=settings.JWT_COOKIE_PATH,
    )
    if refresh_token is not None:
        response.set_cookie(
            settings.JWT_REFRESH_COOKIE_NAME,
            str(refresh_token),
            max_age=int(settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds()),
            httponly=settings.JWT_COOKIE_HTTPONLY,
            secure=settings.JWT_COOKIE_SECURE,
            samesite=settings.JWT_COOKIE_SAMESITE,
            path=settings.JWT_COOKIE_PATH,
        )
    return response


def clear_token_cookies(response):
    response.delete_cookie(
        settings.JWT_ACCESS_COOKIE_NAME,
        path=settings.JWT_COOKIE_PATH,
        samesite=settings.JWT_COOKIE_SAMESITE,
    )
    response.delete_cookie(
        settings.JWT_REFRESH_COOKIE_NAME,
        path=settings.JWT_COOKIE_PATH,
        samesite=settings.JWT_COOKIE_SAMESITE,
    )
    return response
