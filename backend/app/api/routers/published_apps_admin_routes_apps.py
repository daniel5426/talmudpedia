from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal, require_scopes
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppAccount,
    PublishedAppAccountStatus,
    PublishedAppCustomDomain,
    PublishedAppCustomDomainStatus,
    PublishedAppSession,
    PublishedAppStatus,
    PublishedAppVisibility,
)
from app.db.postgres.session import get_db
from app.services.published_app_draft_dev_runtime import PublishedAppDraftDevRuntimeService
from app.services.published_app_draft_revision_materializer import (
    PublishedAppDraftRevisionMaterializerError,
    PublishedAppDraftRevisionMaterializerService,
)
from app.services.published_app_templates import build_template_files, get_template, list_templates
from app.services.published_app_auth_templates import list_auth_templates

from .published_apps_admin_access import (
    _assert_can_manage_apps,
    _generate_unique_slug,
    _get_app_for_tenant,
    _get_custom_domain_for_app,
    _resolve_tenant_admin_context,
    _validate_agent,
)
from .published_apps_admin_shared import (
    APP_SLUG_PATTERN,
    CreatePublishedAppDomainRequest,
    CreatePublishedAppRequest,
    PublishedAppAuthTemplateResponse,
    PublishedAppDomainResponse,
    PublishedAppResponse,
    PublishedAppTemplateResponse,
    PublishedAppUserResponse,
    UpdatePublishedAppUserRequest,
    _app_to_response,
    _auth_template_to_response,
    _domain_to_response,
    _normalize_domain_host,
    _template_to_response,
    _validate_auth_template_key,
    _validate_allowed_origins,
    _validate_external_auth_oidc,
    _validate_providers,
    _validate_template_key,
    _validate_visibility,
    router,
)

@router.get("", response_model=List[PublishedAppResponse])
async def list_published_apps(
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    result = await db.execute(
        select(PublishedApp)
        .where(PublishedApp.tenant_id == ctx["tenant_id"])
        .order_by(PublishedApp.updated_at.desc())
    )
    return [_app_to_response(app) for app in result.scalars().all()]


@router.get("/templates", response_model=List[PublishedAppTemplateResponse])
async def list_published_app_templates(
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
):
    return [_template_to_response(template) for template in list_templates()]


@router.get("/auth/templates", response_model=List[PublishedAppAuthTemplateResponse])
async def list_published_app_auth_templates(
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
):
    return [_auth_template_to_response(template) for template in list_auth_templates()]


@router.post("", response_model=PublishedAppResponse)
async def create_published_app(
    payload: CreatePublishedAppRequest,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)

    template_key = _validate_template_key(payload.template_key)
    auth_template_key = _validate_auth_template_key(payload.auth_template_key)
    visibility = _validate_visibility(payload.visibility)
    candidate_slug = (payload.slug or "").strip().lower()
    if candidate_slug:
        if not APP_SLUG_PATTERN.match(candidate_slug):
            raise HTTPException(status_code=400, detail="Slug must be lowercase, 3-64 chars, and contain only letters, numbers, hyphens")
        slug = await _generate_unique_slug(db, candidate_slug)
    else:
        slug = await _generate_unique_slug(db, payload.name)

    providers = _validate_providers(payload.auth_providers)
    allowed_origins = _validate_allowed_origins(payload.allowed_origins)
    external_auth_oidc = _validate_external_auth_oidc(payload.external_auth_oidc)
    await _validate_agent(db, ctx["tenant_id"], payload.agent_id)

    app = PublishedApp(
        tenant_id=ctx["tenant_id"],
        agent_id=payload.agent_id,
        name=payload.name.strip(),
        description=(payload.description or "").strip() or None,
        logo_url=(payload.logo_url or "").strip() or None,
        slug=slug,
        template_key=template_key,
        visibility=PublishedAppVisibility(visibility),
        auth_enabled=payload.auth_enabled,
        auth_providers=providers,
        auth_template_key=auth_template_key,
        allowed_origins=allowed_origins,
        external_auth_oidc=external_auth_oidc,
        created_by=ctx["user"].id if ctx["user"] else None,
        status=PublishedAppStatus.draft,
    )
    db.add(app)
    runtime_service = PublishedAppDraftDevRuntimeService(db)
    try:
        await db.flush()

        template = get_template(template_key)
        files = build_template_files(
            template_key,
            runtime_context={
                "app_id": str(app.id),
                "app_slug": app.slug,
                "agent_id": str(app.agent_id),
            },
        )
        await runtime_service.provision_workspace_from_files(
            app=app,
            user_id=ctx["user"].id if ctx["user"] else None,
            files=files,
            entry_file=template.entry_file,
            trace_source="apps.create",
        )
        materializer = PublishedAppDraftRevisionMaterializerService(db)
        await materializer.materialize_live_workspace(
            app=app,
            entry_file=template.entry_file,
            source_revision_id=None,
            created_by=ctx["user"].id if ctx["user"] else None,
            origin_kind="app_init",
        )

        await db.commit()
    except PublishedAppDraftRevisionMaterializerError as exc:
        await db.rollback()
        try:
            cleanup_service = PublishedAppDraftDevRuntimeService(db)
            await cleanup_service.destroy_workspace_for_app(app_id=app.id)
            await db.commit()
        except Exception:
            await db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "APP_INIT_MATERIALIZATION_FAILED",
                "message": "App creation failed before the first durable draft revision was materialized.",
                "reason": str(exc),
            },
        ) from exc
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Published app slug or name already exists")

    await db.refresh(app)
    return _app_to_response(app)


@router.get("/{app_id}", response_model=PublishedAppResponse)
async def get_published_app(
    app_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    return _app_to_response(app)


@router.get("/{app_id}/users", response_model=List[PublishedAppUserResponse])
async def list_published_app_users(
    app_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)

    result = await db.execute(
        select(PublishedAppAccount)
        .where(PublishedAppAccount.published_app_id == app.id)
        .order_by(PublishedAppAccount.updated_at.desc())
    )
    rows = list(result.scalars().all())

    active_counts: Dict[str, int] = {}
    if rows:
        account_ids = [row.id for row in rows]
        counts_result = await db.execute(
            select(
                PublishedAppSession.app_account_id,
                func.count(PublishedAppSession.id),
            )
            .where(
                and_(
                    PublishedAppSession.published_app_id == app.id,
                    PublishedAppSession.app_account_id.in_(account_ids),
                    PublishedAppSession.revoked_at.is_(None),
                    PublishedAppSession.expires_at > datetime.now(timezone.utc),
                )
            )
            .group_by(PublishedAppSession.app_account_id)
        )
        active_counts = {str(account_id): int(count or 0) for account_id, count in counts_result.all()}

    return [
        PublishedAppUserResponse(
            app_account_id=str(account.id),
            user_id=str(account.id),
            global_user_id=str(account.global_user_id) if account.global_user_id else None,
            email=account.email,
            full_name=account.full_name,
            avatar=account.avatar,
            account_status=account.status.value if hasattr(account.status, "value") else str(account.status),
            membership_status=account.status.value if hasattr(account.status, "value") else str(account.status),
            last_login_at=account.last_login_at,
            created_at=account.created_at,
            updated_at=account.updated_at,
            active_sessions=active_counts.get(str(account.id), 0),
        )
        for account in rows
    ]


@router.patch("/{app_id}/users/{user_id}", response_model=PublishedAppUserResponse)
async def update_published_app_user_membership(
    app_id: UUID,
    user_id: UUID,
    payload: UpdatePublishedAppUserRequest,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)

    try:
        next_status = PublishedAppAccountStatus(payload.membership_status.strip().lower())
    except Exception:
        raise HTTPException(status_code=400, detail="Unsupported membership_status value")

    account_result = await db.execute(
        select(PublishedAppAccount)
        .where(
            and_(
                PublishedAppAccount.published_app_id == app.id,
                PublishedAppAccount.id == user_id,
            )
        )
        .limit(1)
    )
    account = account_result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=404, detail="Published app account not found")

    account.status = next_status
    account.updated_at = datetime.now(timezone.utc)
    if next_status == PublishedAppAccountStatus.blocked:
        sessions_result = await db.execute(
            select(PublishedAppSession).where(
                and_(
                    PublishedAppSession.published_app_id == app.id,
                    PublishedAppSession.app_account_id == user_id,
                    PublishedAppSession.revoked_at.is_(None),
                )
            )
        )
        for session in sessions_result.scalars().all():
            session.revoked_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(account)

    active_sessions_result = await db.execute(
        select(func.count(PublishedAppSession.id)).where(
            and_(
                PublishedAppSession.published_app_id == app.id,
                PublishedAppSession.app_account_id == user_id,
                PublishedAppSession.revoked_at.is_(None),
                PublishedAppSession.expires_at > datetime.now(timezone.utc),
            )
        )
    )
    active_sessions = int(active_sessions_result.scalar() or 0)
    return PublishedAppUserResponse(
        app_account_id=str(account.id),
        user_id=str(account.id),
        global_user_id=str(account.global_user_id) if account.global_user_id else None,
        email=account.email,
        full_name=account.full_name,
        avatar=account.avatar,
        account_status=account.status.value if hasattr(account.status, "value") else str(account.status),
        membership_status=account.status.value if hasattr(account.status, "value") else str(account.status),
        last_login_at=account.last_login_at,
        created_at=account.created_at,
        updated_at=account.updated_at,
        active_sessions=active_sessions,
    )


@router.get("/{app_id}/domains", response_model=List[PublishedAppDomainResponse])
async def list_published_app_domains(
    app_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    result = await db.execute(
        select(PublishedAppCustomDomain)
        .where(PublishedAppCustomDomain.published_app_id == app.id)
        .order_by(PublishedAppCustomDomain.created_at.desc())
    )
    return [_domain_to_response(item) for item in result.scalars().all()]


@router.post("/{app_id}/domains", response_model=PublishedAppDomainResponse)
async def create_published_app_domain(
    app_id: UUID,
    payload: CreatePublishedAppDomainRequest,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)

    host = _normalize_domain_host(payload.host)
    existing_result = await db.execute(
        select(PublishedAppCustomDomain).where(PublishedAppCustomDomain.host == host).limit(1)
    )
    existing = existing_result.scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Custom domain host already exists")

    domain = PublishedAppCustomDomain(
        published_app_id=app.id,
        host=host,
        status=PublishedAppCustomDomainStatus.pending,
        requested_by=ctx["user"].id if ctx.get("user") else None,
        notes=(payload.notes or "").strip() or None,
    )
    db.add(domain)
    await db.commit()
    await db.refresh(domain)
    return _domain_to_response(domain)


@router.delete("/{app_id}/domains/{domain_id}")
async def delete_published_app_domain(
    app_id: UUID,
    domain_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    domain = await _get_custom_domain_for_app(db, app_id=app.id, domain_id=domain_id)
    if domain.status != PublishedAppCustomDomainStatus.pending:
        raise HTTPException(status_code=400, detail="Only pending custom domains can be removed")
    await db.delete(domain)
    await db.commit()
    return {"status": "deleted", "id": str(domain_id)}
