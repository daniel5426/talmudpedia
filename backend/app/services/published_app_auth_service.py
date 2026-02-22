import base64
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlencode
from uuid import UUID, uuid4

import jwt
import requests
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_published_app_session_token, get_password_hash, verify_password
from app.db.postgres.models.identity import User
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppExternalIdentity,
    PublishedAppSession,
    PublishedAppUserMembership,
    PublishedAppUserMembershipStatus,
)
from app.db.postgres.models.registry import IntegrationCredential


SESSION_TTL_DAYS = 7
GOOGLE_OAUTH_SCOPES = "openid email profile"
GOOGLE_OAUTH_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"


class PublishedAppAuthError(Exception):
    pass


@dataclass
class AuthResult:
    token: str
    user: User
    session: PublishedAppSession


class PublishedAppAuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_google_credential(self, tenant_id: UUID) -> Optional[IntegrationCredential]:
        result = await self.db.execute(
            select(IntegrationCredential).where(
                IntegrationCredential.tenant_id == tenant_id,
                IntegrationCredential.provider_key == "google_oauth",
                IntegrationCredential.is_enabled == True,
            ).limit(1)
        )
        return result.scalar_one_or_none()

    async def ensure_membership(self, app: PublishedApp, user: User) -> PublishedAppUserMembership:
        result = await self.db.execute(
            select(PublishedAppUserMembership).where(
                PublishedAppUserMembership.published_app_id == app.id,
                PublishedAppUserMembership.user_id == user.id,
            ).limit(1)
        )
        membership = result.scalar_one_or_none()
        if membership is None:
            membership = PublishedAppUserMembership(
                published_app_id=app.id,
                user_id=user.id,
                status=PublishedAppUserMembershipStatus.active,
                last_login_at=datetime.now(timezone.utc),
            )
            self.db.add(membership)
            await self.db.flush()
            return membership

        if membership.status == PublishedAppUserMembershipStatus.blocked:
            raise PublishedAppAuthError("User is blocked for this app")

        membership.status = PublishedAppUserMembershipStatus.active
        membership.last_login_at = datetime.now(timezone.utc)
        await self.db.flush()
        return membership

    async def create_session(self, app: PublishedApp, user: User, provider: str, metadata: Optional[dict[str, Any]] = None) -> PublishedAppSession:
        session = PublishedAppSession(
            published_app_id=app.id,
            user_id=user.id,
            jti=str(uuid4()),
            provider=provider,
            metadata_=metadata or {},
            expires_at=datetime.now(timezone.utc) + timedelta(days=SESSION_TTL_DAYS),
        )
        self.db.add(session)
        await self.db.flush()
        return session

    async def issue_auth_result(self, app: PublishedApp, user: User, provider: str, metadata: Optional[dict[str, Any]] = None) -> AuthResult:
        await self.ensure_membership(app, user)
        session = await self.create_session(app, user, provider, metadata=metadata)
        token = create_published_app_session_token(
            subject=str(user.id),
            tenant_id=str(app.tenant_id),
            app_id=str(app.id),
            session_id=str(session.id),
            provider=provider,
            scopes=["public.chat", "public.chats.read"],
            expires_delta=timedelta(days=SESSION_TTL_DAYS),
        )
        await self.db.commit()
        return AuthResult(token=token, user=user, session=session)

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

    async def _get_or_create_external_identity_user(
        self,
        *,
        app: PublishedApp,
        provider: str,
        issuer: str,
        subject: str,
        email: Optional[str],
        full_name: Optional[str],
        metadata: Optional[dict[str, Any]] = None,
    ) -> User:
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
            user = await self.db.get(User, identity.user_id)
            if user is None:
                raise PublishedAppAuthError("External identity is linked to a missing user")
            if email:
                identity.email = email
            if metadata:
                identity.metadata_ = dict(metadata)
            await self.db.flush()
            return user

        resolved_email = (email or "").strip().lower()
        user: Optional[User] = None
        if resolved_email:
            user_result = await self.db.execute(select(User).where(User.email == resolved_email).limit(1))
            user = user_result.scalar_one_or_none()

        if user is None:
            synthetic_email = resolved_email or f"oidc-{uuid4().hex}@external.local"
            user = User(
                email=synthetic_email,
                full_name=full_name,
                role="user",
                avatar=f"https://api.dicebear.com/7.x/initials/svg?seed={full_name or synthetic_email}",
            )
            self.db.add(user)
            await self.db.flush()

        identity = PublishedAppExternalIdentity(
            published_app_id=app.id,
            user_id=user.id,
            provider=provider,
            issuer=issuer,
            subject=subject,
            email=resolved_email or None,
            metadata_=dict(metadata or {}),
        )
        self.db.add(identity)
        await self.db.flush()
        return user

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

        user = await self._get_or_create_external_identity_user(
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
            user=user,
            provider="oidc",
            metadata=identity_metadata,
        )

    async def signup_with_password(self, app: PublishedApp, email: str, password: str, full_name: Optional[str] = None) -> AuthResult:
        if len(password) < 6:
            raise PublishedAppAuthError("Password must be at least 6 characters")

        result = await self.db.execute(select(User).where(User.email == email).limit(1))
        existing_user = result.scalar_one_or_none()
        if existing_user is not None:
            raise PublishedAppAuthError("A user with this email already exists")

        user = User(
            email=email,
            full_name=full_name,
            hashed_password=get_password_hash(password),
            role="user",
            avatar=f"https://api.dicebear.com/7.x/initials/svg?seed={full_name or email}",
        )
        self.db.add(user)
        await self.db.flush()
        return await self.issue_auth_result(app=app, user=user, provider="password")

    async def login_with_password(self, app: PublishedApp, email: str, password: str) -> AuthResult:
        result = await self.db.execute(select(User).where(User.email == email).limit(1))
        user = result.scalar_one_or_none()
        if user is None or not user.hashed_password or not verify_password(password, user.hashed_password):
            raise PublishedAppAuthError("Invalid email or password")
        return await self.issue_auth_result(app=app, user=user, provider="password")

    async def get_or_create_google_user(
        self,
        *,
        email: str,
        google_id: str,
        full_name: Optional[str],
        avatar: Optional[str],
    ) -> User:
        result = await self.db.execute(
            select(User).where(
                (User.google_id == google_id) | (User.email == email)
            ).limit(1)
        )
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                email=email,
                google_id=google_id,
                full_name=full_name,
                avatar=avatar,
                role="user",
            )
            self.db.add(user)
            await self.db.flush()
            return user

        if not user.google_id:
            user.google_id = google_id
        if full_name and not user.full_name:
            user.full_name = full_name
        if avatar and not user.avatar:
            user.avatar = avatar
        await self.db.flush()
        return user

    def build_google_auth_url(self, *, client_id: str, redirect_uri: str, app_slug: str, return_to: str) -> str:
        state_payload = {
            "app_slug": app_slug,
            "return_to": return_to,
            "nonce": secrets.token_urlsafe(16),
        }
        state = base64.urlsafe_b64encode(json.dumps(state_payload).encode("utf-8")).decode("utf-8")
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

    def parse_google_state(self, encoded_state: str) -> dict[str, str]:
        try:
            raw = base64.urlsafe_b64decode(encoded_state.encode("utf-8")).decode("utf-8")
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError("State payload must be an object")
            if not payload.get("app_slug") or not payload.get("return_to"):
                raise ValueError("State payload is missing required fields")
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

    async def revoke_session(self, session_id: UUID, user_id: UUID, app_id: UUID) -> bool:
        result = await self.db.execute(
            select(PublishedAppSession).where(
                and_(
                    PublishedAppSession.id == session_id,
                    PublishedAppSession.user_id == user_id,
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
