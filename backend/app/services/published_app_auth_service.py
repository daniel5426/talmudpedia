from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import os
from typing import Any, Optional
from urllib.parse import urlencode
from uuid import UUID, uuid4

import jwt
import requests
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import ALGORITHM, SECRET_KEY, create_published_app_session_token, get_password_hash, verify_password
from app.db.postgres.models.identity import User
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppAccount,
    PublishedAppAccountStatus,
    PublishedAppExternalIdentity,
    PublishedAppSession,
)
from app.db.postgres.models.registry import IntegrationCredential, IntegrationCredentialCategory


SESSION_TTL_DAYS = 7
GOOGLE_OAUTH_SCOPES = "openid email profile"
GOOGLE_OAUTH_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_OAUTH_STATE_TOKEN_USE = "published_app_google_oauth_state"
GOOGLE_OAUTH_STATE_EXPIRE_MINUTES = int(os.getenv("PUBLISHED_APP_GOOGLE_OAUTH_STATE_EXPIRE_MINUTES", "10"))
PASSWORD_LOGIN_MAX_FAILURES = int(os.getenv("PUBLISHED_APP_PASSWORD_LOGIN_MAX_FAILURES", "5"))
PASSWORD_LOGIN_FAILURE_WINDOW_MINUTES = int(os.getenv("PUBLISHED_APP_PASSWORD_LOGIN_FAILURE_WINDOW_MINUTES", "15"))
PASSWORD_LOGIN_LOCKOUT_MINUTES = int(os.getenv("PUBLISHED_APP_PASSWORD_LOGIN_LOCKOUT_MINUTES", "15"))
_PASSWORD_LOGIN_THROTTLES: dict[str, dict[str, Any]] = {}


class PublishedAppAuthError(Exception):
    pass


class PublishedAppAuthRateLimitError(PublishedAppAuthError):
    pass


@dataclass
class AuthResult:
    token: str
    account: PublishedAppAccount
    session: PublishedAppSession


class PublishedAppAuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _password_login_throttle_key(*, app: PublishedApp, email: str, client_ip: Optional[str]) -> str:
        normalized_email = email.strip().lower()
        normalized_ip = str(client_ip or "").strip() or "unknown"
        return f"{app.id}:{normalized_email}:{normalized_ip}"

    @staticmethod
    def _prune_password_login_throttle(*, key: str, now: datetime) -> dict[str, Any] | None:
        state = _PASSWORD_LOGIN_THROTTLES.get(key)
        if state is None:
            return None
        locked_until = state.get("locked_until")
        window_started_at = state.get("window_started_at")
        if isinstance(locked_until, datetime) and locked_until <= now:
            _PASSWORD_LOGIN_THROTTLES.pop(key, None)
            return None
        if isinstance(window_started_at, datetime) and window_started_at + timedelta(minutes=PASSWORD_LOGIN_FAILURE_WINDOW_MINUTES) <= now:
            _PASSWORD_LOGIN_THROTTLES.pop(key, None)
            return None
        return state

    def _assert_password_login_allowed(self, *, app: PublishedApp, email: str, client_ip: Optional[str]) -> None:
        key = self._password_login_throttle_key(app=app, email=email, client_ip=client_ip)
        now = datetime.now(timezone.utc)
        state = self._prune_password_login_throttle(key=key, now=now)
        if state is None:
            return
        locked_until = state.get("locked_until")
        if isinstance(locked_until, datetime) and locked_until > now:
            raise PublishedAppAuthRateLimitError("Too many failed login attempts. Try again later.")

    def _record_password_login_failure(self, *, app: PublishedApp, email: str, client_ip: Optional[str]) -> None:
        key = self._password_login_throttle_key(app=app, email=email, client_ip=client_ip)
        now = datetime.now(timezone.utc)
        state = self._prune_password_login_throttle(key=key, now=now)
        if state is None:
            _PASSWORD_LOGIN_THROTTLES[key] = {
                "window_started_at": now,
                "failures": 1,
                "locked_until": None,
            }
            return

        failures = int(state.get("failures") or 0) + 1
        state["failures"] = failures
        if failures >= PASSWORD_LOGIN_MAX_FAILURES:
            state["locked_until"] = now + timedelta(minutes=PASSWORD_LOGIN_LOCKOUT_MINUTES)
            raise PublishedAppAuthRateLimitError("Too many failed login attempts. Try again later.")

    def _clear_password_login_failure_state(self, *, app: PublishedApp, email: str, client_ip: Optional[str]) -> None:
        key = self._password_login_throttle_key(app=app, email=email, client_ip=client_ip)
        _PASSWORD_LOGIN_THROTTLES.pop(key, None)

    async def get_google_credential(self, organization_id: UUID) -> Optional[IntegrationCredential]:
        result = await self.db.execute(
            select(IntegrationCredential).where(
                IntegrationCredential.organization_id == organization_id,
                IntegrationCredential.category == IntegrationCredentialCategory.CUSTOM,
                IntegrationCredential.provider_key == "google_oauth",
                IntegrationCredential.is_enabled == True,
            ).limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _default_avatar(seed: str) -> str:
        return f"https://api.dicebear.com/7.x/initials/svg?seed={seed}"

    async def _touch_account(
        self,
        *,
        account: PublishedAppAccount,
        full_name: Optional[str] = None,
        avatar: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> PublishedAppAccount:
        if account.status == PublishedAppAccountStatus.blocked:
            raise PublishedAppAuthError("User is blocked for this app")
        if full_name:
            account.full_name = full_name
        if avatar:
            account.avatar = avatar
        account.status = PublishedAppAccountStatus.active
        account.last_login_at = datetime.now(timezone.utc)
        if metadata:
            merged = dict(account.metadata_ or {})
            merged.update(metadata)
            account.metadata_ = merged
        await self.db.flush()
        return account

    async def _create_account(
        self,
        *,
        app: PublishedApp,
        email: str,
        full_name: Optional[str] = None,
        avatar: Optional[str] = None,
        hashed_password: Optional[str] = None,
        global_user_id: Optional[UUID] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> PublishedAppAccount:
        account = PublishedAppAccount(
            published_app_id=app.id,
            global_user_id=global_user_id,
            email=email.strip().lower(),
            full_name=full_name,
            avatar=avatar or self._default_avatar(full_name or email),
            hashed_password=hashed_password,
            status=PublishedAppAccountStatus.active,
            last_login_at=datetime.now(timezone.utc),
            metadata_=dict(metadata or {}),
        )
        self.db.add(account)
        await self.db.flush()
        return account

    async def _get_account_by_email(self, *, app_id: UUID, email: str) -> Optional[PublishedAppAccount]:
        result = await self.db.execute(
            select(PublishedAppAccount).where(
                and_(
                    PublishedAppAccount.published_app_id == app_id,
                    PublishedAppAccount.email == email.strip().lower(),
                )
            ).limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_or_create_global_human(
        self,
        *,
        email: Optional[str],
        full_name: Optional[str],
        avatar: Optional[str],
        google_id: Optional[str] = None,
    ) -> Optional[User]:
        normalized_email = (email or "").strip().lower()
        if not normalized_email and not google_id:
            return None
        result = await self.db.execute(
            select(User).where(
                (User.google_id == google_id) if google_id and not normalized_email else (
                    (User.google_id == google_id) | (User.email == normalized_email)
                    if google_id and normalized_email
                    else (User.email == normalized_email)
                )
            ).limit(1)
        )
        user = result.scalar_one_or_none()
        if user is None:
            synthetic_email = normalized_email or f"published-app-{uuid4().hex}@external.local"
            user = User(
                email=synthetic_email,
                google_id=google_id,
                full_name=full_name,
                avatar=avatar or self._default_avatar(full_name or synthetic_email),
                role="user",
            )
            self.db.add(user)
            await self.db.flush()
            return user

        if google_id and not user.google_id:
            user.google_id = google_id
        if full_name and not user.full_name:
            user.full_name = full_name
        if avatar and not user.avatar:
            user.avatar = avatar
        await self.db.flush()
        return user

    async def create_session(
        self,
        app: PublishedApp,
        account: PublishedAppAccount,
        provider: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> PublishedAppSession:
        session = PublishedAppSession(
            published_app_id=app.id,
            user_id=account.global_user_id,
            app_account_id=account.id,
            jti=str(uuid4()),
            provider=provider,
            metadata_=metadata or {},
            expires_at=datetime.now(timezone.utc) + timedelta(days=SESSION_TTL_DAYS),
        )
        self.db.add(session)
        await self.db.flush()
        return session

    async def issue_auth_result(
        self,
        *,
        app: PublishedApp,
        account: PublishedAppAccount,
        provider: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> AuthResult:
        account = await self._touch_account(account=account, metadata=metadata)
        session = await self.create_session(app, account, provider, metadata=metadata)
        token = create_published_app_session_token(
            subject=str(account.id),
            organization_id=str(app.organization_id),
            app_id=str(app.id),
            app_account_id=str(account.id),
            session_id=str(session.id),
            provider=provider,
            scopes=["public.auth", "public.chat", "public.chats.read"],
            expires_delta=timedelta(days=SESSION_TTL_DAYS),
        )
        await self.db.commit()
        return AuthResult(token=token, account=account, session=session)

    def verify_external_oidc_token(self, *, token: str, config: dict[str, Any]) -> dict[str, Any]:
        issuer = str(config.get("issuer") or "").strip().rstrip("/")
        audience = str(config.get("audience") or "").strip()
        jwks_uri = str(config.get("jwks_uri") or "").strip()
        if not issuer or not audience or not jwks_uri:
            raise PublishedAppAuthError("OIDC configuration is incomplete")

        algorithms = config.get("algorithms")
        if not isinstance(algorithms, list) or not algorithms:
            algorithms = ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"]

        try:
            jwks_client = jwt.PyJWKClient(jwks_uri)
            signing_key = jwks_client.get_signing_key_from_jwt(token).key
            payload = jwt.decode(
                token,
                signing_key,
                algorithms=algorithms,
                audience=audience,
                issuer=issuer,
            )
            if not isinstance(payload, dict):
                raise PublishedAppAuthError("OIDC token payload is invalid")
            return payload
        except PublishedAppAuthError:
            raise
        except Exception as exc:
            raise PublishedAppAuthError(f"Failed to verify external OIDC token: {exc}") from exc

    async def _get_or_create_external_identity_account(
        self,
        *,
        app: PublishedApp,
        provider: str,
        issuer: str,
        subject: str,
        email: Optional[str],
        full_name: Optional[str],
        avatar: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> PublishedAppAccount:
        result = await self.db.execute(
            select(PublishedAppExternalIdentity).where(
                and_(
                    PublishedAppExternalIdentity.published_app_id == app.id,
                    PublishedAppExternalIdentity.provider == provider,
                    PublishedAppExternalIdentity.issuer == issuer,
                    PublishedAppExternalIdentity.subject == subject,
                )
            ).limit(1)
        )
        identity = result.scalar_one_or_none()
        if identity is not None:
            if identity.app_account_id is None:
                raise PublishedAppAuthError("External identity is linked to a missing app account")
            account = await self.db.get(PublishedAppAccount, identity.app_account_id)
            if account is None:
                raise PublishedAppAuthError("External identity is linked to a missing app account")
            if email:
                account.email = email
                identity.email = email
            if metadata:
                identity.metadata_ = dict(metadata)
            await self._touch_account(account=account, full_name=full_name, avatar=avatar, metadata=metadata)
            return account

        normalized_email = (email or "").strip().lower()
        account = None
        if normalized_email:
            account = await self._get_account_by_email(app_id=app.id, email=normalized_email)
        global_user = await self._get_or_create_global_human(
            email=normalized_email or None,
            full_name=full_name,
            avatar=avatar,
        )
        if account is None:
            account = await self._create_account(
                app=app,
                email=normalized_email or f"oidc-{uuid4().hex}@external.local",
                full_name=full_name,
                avatar=avatar,
                global_user_id=global_user.id if global_user else None,
                metadata=metadata,
            )
        else:
            if global_user and account.global_user_id is None:
                account.global_user_id = global_user.id
            await self._touch_account(account=account, full_name=full_name, avatar=avatar, metadata=metadata)

        identity = PublishedAppExternalIdentity(
            published_app_id=app.id,
            user_id=global_user.id if global_user else None,
            app_account_id=account.id,
            provider=provider,
            issuer=issuer,
            subject=subject,
            email=normalized_email or None,
            metadata_=dict(metadata or {}),
        )
        self.db.add(identity)
        await self.db.flush()
        return account

    async def exchange_external_oidc(self, *, app: PublishedApp, token: str) -> AuthResult:
        config = app.external_auth_oidc or {}
        if not isinstance(config, dict) or not config:
            raise PublishedAppAuthError("External OIDC auth is not configured for this app")

        payload = self.verify_external_oidc_token(token=token, config=config)
        issuer = str(config.get("issuer") or "").strip().rstrip("/")
        subject = str(payload.get("sub") or "").strip()
        if not subject:
            raise PublishedAppAuthError("OIDC token is missing subject claim")

        email_claim = str(config.get("email_claim") or "email").strip() or "email"
        name_claim = str(config.get("name_claim") or "name").strip() or "name"
        email_raw = payload.get(email_claim)
        name_raw = payload.get(name_claim)
        email = str(email_raw).strip().lower() if isinstance(email_raw, str) else None
        full_name = str(name_raw).strip() if isinstance(name_raw, str) else None

        identity_metadata = {
            "issuer": issuer,
            "subject": subject,
            "audience": str(config.get("audience") or ""),
            "email_claim": email_claim,
            "name_claim": name_claim,
        }

        account = await self._get_or_create_external_identity_account(
            app=app,
            provider="oidc",
            issuer=issuer,
            subject=subject,
            email=email,
            full_name=full_name,
            metadata=identity_metadata,
        )
        return await self.issue_auth_result(
            app=app,
            account=account,
            provider="oidc",
            metadata=identity_metadata,
        )

    async def signup_with_password(
        self,
        app: PublishedApp,
        email: str,
        password: str,
        full_name: Optional[str] = None,
    ) -> AuthResult:
        normalized_email = email.strip().lower()
        if len(password) < 6:
            raise PublishedAppAuthError("Password must be at least 6 characters")

        existing_account = await self._get_account_by_email(app_id=app.id, email=normalized_email)
        if existing_account is not None:
            raise PublishedAppAuthError("A user with this email already exists for this app")

        global_user = await self._get_or_create_global_human(
            email=normalized_email,
            full_name=full_name,
            avatar=self._default_avatar(full_name or normalized_email),
        )
        account = await self._create_account(
            app=app,
            email=normalized_email,
            full_name=full_name,
            hashed_password=get_password_hash(password),
            global_user_id=global_user.id if global_user else None,
        )
        return await self.issue_auth_result(app=app, account=account, provider="password")

    async def login_with_password(
        self,
        app: PublishedApp,
        email: str,
        password: str,
        client_ip: Optional[str] = None,
    ) -> AuthResult:
        normalized_email = email.strip().lower()
        self._assert_password_login_allowed(app=app, email=normalized_email, client_ip=client_ip)
        account = await self._get_account_by_email(app_id=app.id, email=email)
        if account is None or not account.hashed_password or not verify_password(password, account.hashed_password):
            self._record_password_login_failure(app=app, email=normalized_email, client_ip=client_ip)
            raise PublishedAppAuthError("Invalid email or password")
        if account.status == PublishedAppAccountStatus.blocked:
            raise PublishedAppAuthError("User is blocked for this app")
        self._clear_password_login_failure_state(app=app, email=normalized_email, client_ip=client_ip)
        return await self.issue_auth_result(app=app, account=account, provider="password")

    async def get_or_create_google_account(
        self,
        *,
        app: PublishedApp,
        email: str,
        google_id: str,
        full_name: Optional[str],
        avatar: Optional[str],
    ) -> PublishedAppAccount:
        global_user = await self._get_or_create_global_human(
            email=email,
            full_name=full_name,
            avatar=avatar,
            google_id=google_id,
        )
        result = await self.db.execute(
            select(PublishedAppExternalIdentity).where(
                and_(
                    PublishedAppExternalIdentity.published_app_id == app.id,
                    PublishedAppExternalIdentity.provider == "google",
                    PublishedAppExternalIdentity.issuer == "google",
                    PublishedAppExternalIdentity.subject == google_id,
                )
            ).limit(1)
        )
        identity = result.scalar_one_or_none()
        if identity is not None and identity.app_account_id:
            account = await self.db.get(PublishedAppAccount, identity.app_account_id)
            if account is None:
                raise PublishedAppAuthError("Google identity is linked to a missing app account")
            if global_user and account.global_user_id is None:
                account.global_user_id = global_user.id
            await self._touch_account(account=account, full_name=full_name, avatar=avatar)
            return account

        account = await self._get_account_by_email(app_id=app.id, email=email)
        if account is None:
            account = await self._create_account(
                app=app,
                email=email,
                full_name=full_name,
                avatar=avatar,
                global_user_id=global_user.id if global_user else None,
                metadata={"provider": "google"},
            )
        else:
            if global_user and account.global_user_id is None:
                account.global_user_id = global_user.id
            await self._touch_account(account=account, full_name=full_name, avatar=avatar)

        identity = PublishedAppExternalIdentity(
            published_app_id=app.id,
            user_id=global_user.id if global_user else None,
            app_account_id=account.id,
            provider="google",
            issuer="google",
            subject=google_id,
            email=email,
            metadata_={"provider": "google"},
        )
        self.db.add(identity)
        await self.db.flush()
        return account

    def build_google_auth_url(
        self,
        *,
        client_id: str,
        redirect_uri: str,
        app_public_id: str,
        return_to: str,
        nonce: str,
    ) -> str:
        state_payload = {
            "app_public_id": app_public_id,
            "return_to": return_to,
            "nonce": nonce,
            "token_use": GOOGLE_OAUTH_STATE_TOKEN_USE,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=GOOGLE_OAUTH_STATE_EXPIRE_MINUTES),
            "jti": str(uuid4()),
        }
        state = jwt.encode(state_payload, SECRET_KEY, algorithm=ALGORITHM)
        query = urlencode(
            {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": GOOGLE_OAUTH_SCOPES,
                "state": state,
                "access_type": "offline",
                "prompt": "consent",
            }
        )
        return f"{GOOGLE_OAUTH_AUTH_URL}?{query}"

    def parse_google_state(self, encoded_state: str, *, expected_nonce: str) -> dict[str, str]:
        try:
            payload = jwt.decode(encoded_state, SECRET_KEY, algorithms=[ALGORITHM])
            if not isinstance(payload, dict):
                raise ValueError("State payload must be an object")
            if payload.get("token_use") != GOOGLE_OAUTH_STATE_TOKEN_USE:
                raise ValueError("State token_use is invalid")
            if not payload.get("app_public_id") or not payload.get("return_to"):
                raise ValueError("State payload is missing required fields")
            if not expected_nonce:
                raise ValueError("State cookie is missing")
            if payload.get("nonce") != expected_nonce:
                raise ValueError("State nonce mismatch")
            return payload
        except Exception as exc:
            raise PublishedAppAuthError(f"Invalid OAuth state: {exc}") from exc

    def exchange_google_code(
        self,
        *,
        code: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
    ) -> dict[str, Any]:
        response = requests.post(
            GOOGLE_OAUTH_TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
        if response.status_code >= 400:
            raise PublishedAppAuthError("Failed to exchange Google authorization code")
        payload = response.json()
        if "id_token" not in payload:
            raise PublishedAppAuthError("Google response did not include id_token")
        return payload

    def verify_google_id_token(self, *, token_value: str, client_id: str) -> dict[str, Any]:
        try:
            return id_token.verify_oauth2_token(
                token_value,
                google_requests.Request(),
                client_id,
            )
        except Exception as exc:
            raise PublishedAppAuthError(f"Invalid Google ID token: {exc}") from exc

    async def revoke_session(self, session_id: UUID, app_account_id: UUID, app_id: UUID) -> bool:
        result = await self.db.execute(
            select(PublishedAppSession).where(
                and_(
                    PublishedAppSession.id == session_id,
                    PublishedAppSession.app_account_id == app_account_id,
                    PublishedAppSession.published_app_id == app_id,
                )
            ).limit(1)
        )
        session = result.scalar_one_or_none()
        if session is None:
            return False
        session.revoked_at = datetime.now(timezone.utc)
        await self.db.commit()
        return True
