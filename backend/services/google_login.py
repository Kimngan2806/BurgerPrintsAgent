import base64
import hashlib
from functools import partial
from urllib.parse import urlencode, urlsplit

from core.config import settings


def callback_uri() -> str | None:
    if not settings.GOOGLE_OAUTH_CLIENT_ID.strip() or not settings.GOOGLE_OAUTH_CLIENT_SECRET.strip():
        return None
    uri = settings.GOOGLE_OAUTH_REDIRECT_URI.strip()
    try:
        parsed = urlsplit(uri)
        secure = parsed.scheme == 'https' or (
            parsed.scheme == 'http' and parsed.hostname in {'localhost', '127.0.0.1', '::1'}
        )
    except ValueError:
        return None
    if (secure and parsed.hostname and parsed.path == '/api/auth/google/callback'
            and not (parsed.username or parsed.password or parsed.query or parsed.fragment)):
        return uri
    return None


def authorization_url(redirect_uri: str, state: str, verifier: str, nonce: str) -> str:
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    query = urlencode({
        'client_id': settings.GOOGLE_OAUTH_CLIENT_ID.strip(),
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': 'openid email',
        'state': state,
        'nonce': nonce,
        'code_challenge': challenge,
        'code_challenge_method': 'S256',
        'prompt': 'select_account',
    })
    return f'https://accounts.google.com/o/oauth2/v2/auth?{query}'


def exchange_identity(code: str, redirect_uri: str, verifier: str, nonce: str) -> tuple[str, str]:
    import requests
    from google.auth.exceptions import GoogleAuthError
    from google.auth.transport.requests import Request
    from google.oauth2 import id_token

    client_id = settings.GOOGLE_OAUTH_CLIENT_ID.strip()
    try:
        with requests.Session() as session:
            response = session.post('https://oauth2.googleapis.com/token', data={
                'grant_type': 'authorization_code',
                'client_id': client_id,
                'client_secret': settings.GOOGLE_OAUTH_CLIENT_SECRET.strip(),
                'redirect_uri': redirect_uri,
                'code': code,
                'code_verifier': verifier,
            }, timeout=8)
            response.raise_for_status()
            token = response.json()['id_token']
            claims = id_token.verify_oauth2_token(token, partial(Request(session), timeout=8), audience=client_id)
    except (GoogleAuthError, requests.RequestException, KeyError, TypeError, ValueError) as exc:
        raise ValueError('Google identity could not be verified.') from exc

    subject, email = claims.get('sub'), claims.get('email')
    if (claims.get('nonce') != nonce or claims.get('email_verified') is not True
            or not isinstance(subject, str) or not 1 <= len(subject) <= 255
            or not isinstance(email, str) or not email or '@' not in email):
        raise ValueError('Google identity claims are incomplete.')
    return subject, email
