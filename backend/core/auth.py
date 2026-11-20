import hashlib
import uuid
from datetime import timedelta

import jwt
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from .models import RefreshToken, User

ISSUER = "polls-api"


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def decode(token, kind):
    try:
        claims = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=["HS256"],
            issuer=ISSUER,
            options={"require": ["sub", "exp", "iat", "iss", "jti", "type"]},
        )
        if claims["type"] != kind:
            raise ValueError
        int(claims["sub"])
        return claims
    except (jwt.PyJWTError, ValueError, TypeError):
        raise AuthenticationFailed("Токен недействителен или истёк.")


def encode(user, kind, expires, **extra):
    return jwt.encode(
        {
            "sub": str(user.pk),
            "type": kind,
            "exp": expires,
            "iat": timezone.now(),
            "iss": ISSUER,
            "jti": uuid.uuid4().hex,
            **extra,
        },
        settings.SECRET_KEY,
        algorithm="HS256",
    )


def issue_tokens(user):
    expires = timezone.now() + timedelta(days=30)
    refresh = encode(user, "refresh", expires)
    session = RefreshToken.objects.create(user=user, token_hash=digest(refresh), expires_at=expires)
    access = encode(user, "access", timezone.now() + timedelta(minutes=15), sid=session.pk)
    return {"access": access, "refresh": refresh}


@transaction.atomic
def rotate_tokens(raw):
    claims = decode(raw, "refresh")
    # Every session mutation locks the user before the session to avoid deadlocks.
    user = User.objects.select_for_update().filter(pk=int(claims["sub"])).first()
    if not user or user.is_banned:
        raise AuthenticationFailed("Сессия недействительна.")
    session = (
        RefreshToken.objects.select_for_update()
        .filter(user=user, token_hash=digest(raw), expires_at__gt=timezone.now())
        .first()
    )
    if not session:
        raise AuthenticationFailed("Сессия недействительна.")
    session.delete()
    return issue_tokens(user)


class SessionJWTAuthentication(BaseAuthentication):
    def authenticate(self, request):
        header = get_authorization_header(request).split()
        if not header:
            return None
        if len(header) != 2 or header[0].lower() != b"bearer":
            raise AuthenticationFailed("Ожидается Authorization: Bearer <access>.")
        try:
            token = header[1].decode()
        except UnicodeDecodeError:
            raise AuthenticationFailed("Неверный токен.")
        return authenticate_access(token)

    def authenticate_header(self, request):
        return "Bearer"


def authenticate_access(token):
    claims = decode(token, "access")
    user = User.objects.select_related("role").filter(pk=int(claims["sub"]), is_banned=False).first()
    if (
        not user
        or not RefreshToken.objects.filter(
            pk=claims.get("sid"), user=user, expires_at__gt=timezone.now()
        ).exists()
    ):
        raise AuthenticationFailed("Сессия завершена.")
    return user, claims


class JWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "core.auth.SessionJWTAuthentication"
    name = "bearerAuth"

    def get_security_definition(self, auto_schema):
        return {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}


class PublicEndpointAuthentication(SessionJWTAuthentication):
    """Public credential endpoints ignore stale access tokens, but return proper 401 challenges."""

    def authenticate(self, request):
        return None


class PublicEndpointScheme(JWTAuthenticationScheme):
    target_class = "core.auth.PublicEndpointAuthentication"
