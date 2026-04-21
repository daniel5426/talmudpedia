from __future__ import annotations

from typing import List
from uuid import UUID

from app.db.postgres.models.artifact_runtime import ArtifactKind
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.operators import CustomOperator
from app.rag.pipeline.registry import ConfigFieldSpec, DataType, OperatorRegistry, OperatorSpec
from app.services.artifact_runtime.registry_service import ArtifactRegistryService


async def sync_custom_operators(db: AsyncSession, organization_id: UUID) -> list[OperatorSpec]:
    query = select(CustomOperator).where(CustomOperator.organization_id == organization_id, CustomOperator.is_active == True)
    result = await db.execute(query)
    custom_ops = result.scalars().all()

    artifact_registry = ArtifactRegistryService(db)
    specs: List[OperatorSpec] = []
    for op in custom_ops:
        required_config = []
        optional_config = []
        if op.config_schema:
            for field in op.config_schema:
                try:
                    parsed = ConfigFieldSpec(**field)
                    if parsed.required:
                        required_config.append(parsed)
                    else:
                        optional_config.append(parsed)
                except Exception:
                    continue

        artifact = await artifact_registry.get_artifact_for_custom_operator(
            organization_id=organization_id,
            custom_operator_id=op.id,
        )
        if artifact is not None and artifact.kind != ArtifactKind.RAG_OPERATOR:
            artifact = None
        specs.append(
            OperatorSpec(
                operator_id=op.name,
                display_name=op.display_name,
                category=op.category,
                version=op.version,
                description=op.description,
                input_type=DataType(op.input_type),
                output_type=DataType(op.output_type),
                required_config=required_config,
                optional_config=optional_config,
                is_custom=True,
                python_code=op.python_code,
                author=str(op.created_by) if op.created_by else None,
                artifact_id=str(artifact.id) if artifact else None,
                artifact_revision_id=(
                    str(artifact.latest_published_revision_id)
                    if artifact and artifact.latest_published_revision_id
                    else None
                ),
            )
        )

    OperatorRegistry.get_instance().load_custom_operators(specs, str(organization_id))
    return specs
