from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from app.db.postgres.models.artifact_runtime import ArtifactRevision

from .source_utils import source_tree_hash


@dataclass(frozen=True)
class BuiltArtifactBundle:
    bundle_hash: str
    dependency_hash: str
    payload: bytes
    manifest: dict[str, Any]


class ArtifactBundleBuilder:
    def build_revision_bundle(self, revision: ArtifactRevision) -> BuiltArtifactBundle:
        source_files = list(revision.source_files or [])
        manifest = {
            "artifact_id": str(revision.artifact_id) if revision.artifact_id else None,
            "revision_id": str(revision.id),
            "tenant_id": str(revision.tenant_id),
            "display_name": revision.display_name,
            "description": revision.description,
            "category": revision.category,
            "scope": getattr(revision.scope, "value", revision.scope),
            "input_type": revision.input_type,
            "output_type": revision.output_type,
            "python_dependencies": list(revision.python_dependencies or []),
            "config_schema": list(revision.config_schema or []),
            "inputs": list(revision.inputs or []),
            "outputs": list(revision.outputs or []),
            "reads": list(revision.reads or []),
            "writes": list(revision.writes or []),
            "version_label": revision.version_label,
            "is_published": bool(revision.is_published),
            "is_ephemeral": bool(revision.is_ephemeral),
            "entry_module_path": revision.entry_module_path,
            "source_files": source_files,
        }
        bundle_hash = source_tree_hash(
            source_files=source_files,
            entry_module_path=revision.entry_module_path,
            python_dependencies=list(revision.python_dependencies or []),
        )
        payload = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
        dependency_hash = sha256(
            json.dumps(list(revision.python_dependencies or []), sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return BuiltArtifactBundle(
            bundle_hash=bundle_hash,
            dependency_hash=dependency_hash,
            payload=payload,
            manifest=manifest,
        )
