from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.artifact_runtime import (
    ArtifactDeployment,
    ArtifactDeploymentStatus,
    ArtifactRevision,
)

from .cloudflare_client import CloudflareArtifactClient
from .cloudflare_package_builder import CloudflareArtifactPackageBuilder
from .runtime_mode import RUNTIME_MODE_STANDARD_WORKER_TEST, artifact_cloudflare_runtime_mode


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
        tenant_id: UUID | None = None,
    ) -> ArtifactDeployment:
        effective_tenant_id = revision.tenant_id or tenant_id
        if effective_tenant_id is None:
            raise ValueError("Artifact deployments require tenant_id for deployment ownership")
        package = self._builder.build_revision_package(revision, namespace=namespace)
        deployment = await self._db.scalar(
            select(ArtifactDeployment).where(
                ArtifactDeployment.tenant_id == effective_tenant_id,
                ArtifactDeployment.namespace == namespace,
                ArtifactDeployment.build_hash == package.build_hash,
            )
        )
        if deployment is not None and deployment.status == ArtifactDeploymentStatus.READY:
            return deployment

        runtime_mode = artifact_cloudflare_runtime_mode()

        if deployment is None:
            deployment = ArtifactDeployment(
                id=uuid4(),
                tenant_id=effective_tenant_id,
                revision_id=revision.id,
                namespace=namespace,
                build_hash=package.build_hash,
                status=ArtifactDeploymentStatus.PENDING,
                worker_name=package.worker_name,
                script_name=package.script_name,
                runtime_metadata=package.metadata,
            )
            self._db.add(deployment)
            await self._db.flush()

        if runtime_mode == RUNTIME_MODE_STANDARD_WORKER_TEST:
            deployment.status = ArtifactDeploymentStatus.READY
            deployment.worker_name = "artifact-free-plan-runtime"
            deployment.script_name = "artifact-free-plan-runtime"
            deployment.deployment_id = package.build_hash
            deployment.version_id = package.build_hash[:16]
            deployment.runtime_metadata = {
                **package.metadata,
                "runtime_mode": runtime_mode,
            }
            deployment.error_payload = None
            revision.build_hash = package.build_hash
            if not revision.bundle_hash:
                revision.bundle_hash = package.build_hash
            await self._db.flush()
            return deployment

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
        deployment.worker_name = str(result.get("id") or deployment.worker_name)
        deployment.script_name = package.script_name
        deployment.deployment_id = str(result.get("deployment_id") or "") or deployment.deployment_id
        deployment.version_id = str(result.get("etag") or result.get("version_id") or "") or deployment.version_id
        deployment.runtime_metadata = {**package.metadata, **dict(result or {})}
        deployment.error_payload = None
        revision.build_hash = package.build_hash
        if not revision.bundle_hash:
            revision.bundle_hash = package.build_hash
        await self._db.flush()
        return deployment

    async def get_ready_deployment(self, *, revision_id: UUID, namespace: str) -> ArtifactDeployment | None:
        return await self._db.scalar(
            select(ArtifactDeployment).where(
                ArtifactDeployment.revision_id == revision_id,
                ArtifactDeployment.namespace == namespace,
                ArtifactDeployment.status == ArtifactDeploymentStatus.READY,
            )
        )
