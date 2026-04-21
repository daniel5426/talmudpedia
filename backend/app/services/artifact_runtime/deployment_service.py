from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.db.postgres.models.artifact_runtime import (
    ArtifactDeployment,
    ArtifactDeploymentStatus,
    ArtifactRevision,
)

from .cloudflare_client import CloudflareArtifactClient
from .cloudflare_package_builder import CloudflareArtifactPackageBuilder


class ArtifactDeploymentService:
    def __init__(self, db: AsyncSession):
        self._db = db
        self._builder = CloudflareArtifactPackageBuilder()
        self._client = CloudflareArtifactClient()

    async def ensure_deployment(
        self,
        *,
        revision: ArtifactRevision,
        namespace: str,
        organization_id: UUID | None = None,
    ) -> ArtifactDeployment:
        effective_organization_id = revision.organization_id or organization_id
        if effective_organization_id is None:
            raise ValueError("Artifact deployments require organization_id for deployment ownership")
        had_bundle_hash = bool(getattr(revision, "bundle_hash", None))
        package = self._builder.build_revision_package(revision, namespace=namespace)
        deployment = await self._get_deployment_by_build_hash(
            organization_id=effective_organization_id,
            namespace=namespace,
            build_hash=package.build_hash,
        )
        if (
            deployment is not None
            and deployment.status == ArtifactDeploymentStatus.READY
            and deployment.worker_name == package.worker_name
            and deployment.script_name == package.script_name
        ):
            return deployment

        if deployment is None:
            deployment = ArtifactDeployment(
                id=uuid4(),
                organization_id=effective_organization_id,
                revision_id=revision.id,
                namespace=namespace,
                build_hash=package.build_hash,
                status=ArtifactDeploymentStatus.PENDING,
                worker_name=package.worker_name,
                script_name=package.script_name,
                runtime_metadata=package.metadata,
            )
            self._db.add(deployment)
            try:
                await self._db.flush()
            except IntegrityError:
                await self._db.rollback()
                deployment = await self._get_deployment_by_build_hash(
                    organization_id=effective_organization_id,
                    namespace=namespace,
                    build_hash=package.build_hash,
                )
                if deployment is None:
                    raise
        else:
            deployment.status = ArtifactDeploymentStatus.PENDING
            deployment.worker_name = package.worker_name
            deployment.script_name = package.script_name
            deployment.runtime_metadata = package.metadata
            deployment.error_payload = None
            deployment.deployment_id = None
            deployment.version_id = None

        try:
            result = await self._client.deploy_worker(
                script_name=package.script_name,
                modules=package.modules,
                metadata=package.metadata,
                namespace=namespace,
            )
        except Exception as exc:
            deployment.status = ArtifactDeploymentStatus.FAILED
            deployment.error_payload = {"message": str(exc), "code": "CLOUDFLARE_DEPLOY_FAILED"}
            await self._db.flush()
            raise

        deployment.status = ArtifactDeploymentStatus.READY
        deployment.worker_name = package.worker_name
        deployment.script_name = package.script_name
        deployment.deployment_id = str(result.get("id") or result.get("deployment_id") or "") or deployment.deployment_id
        deployment.version_id = str(result.get("etag") or result.get("version_id") or "") or deployment.version_id
        deployment.runtime_metadata = {**package.metadata, **dict(result or {})}
        deployment.error_payload = None
        revision.build_hash = package.build_hash
        if not had_bundle_hash:
            revision.bundle_hash = package.build_hash
        await self._db.flush()
        return deployment

    async def _get_deployment_by_build_hash(
        self,
        *,
        organization_id: UUID,
        namespace: str,
        build_hash: str,
    ) -> ArtifactDeployment | None:
        return await self._db.scalar(
            select(ArtifactDeployment).where(
                ArtifactDeployment.organization_id == organization_id,
                ArtifactDeployment.namespace == namespace,
                ArtifactDeployment.build_hash == build_hash,
            )
        )

    async def get_ready_deployment(self, *, revision_id: UUID, namespace: str) -> ArtifactDeployment | None:
        return await self._db.scalar(
            select(ArtifactDeployment).where(
                ArtifactDeployment.revision_id == revision_id,
                ArtifactDeployment.namespace == namespace,
                ArtifactDeployment.status == ArtifactDeploymentStatus.READY,
            )
        )
