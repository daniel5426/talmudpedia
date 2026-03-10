from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from app.db.postgres.models.artifact_runtime import ArtifactRevision


@dataclass(frozen=True)
class BuiltArtifactBundle:
    bundle_hash: str
    payload: bytes
    manifest: dict[str, Any]


class ArtifactBundleBuilder:
    def build_revision_bundle(self, revision: ArtifactRevision) -> BuiltArtifactBundle:
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
            "config_schema": list(revision.config_schema or []),
            "inputs": list(revision.inputs or []),
            "outputs": list(revision.outputs or []),
            "reads": list(revision.reads or []),
            "writes": list(revision.writes or []),
            "version_label": revision.version_label,
            "is_published": bool(revision.is_published),
            "is_ephemeral": bool(revision.is_ephemeral),
        }

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("artifact.json", json.dumps(manifest, sort_keys=True, separators=(",", ":")))
            archive.writestr("handler.py", revision.source_code or "")
        payload = buffer.getvalue()
        bundle_hash = sha256(payload).hexdigest()
        return BuiltArtifactBundle(bundle_hash=bundle_hash, payload=payload, manifest=manifest)
