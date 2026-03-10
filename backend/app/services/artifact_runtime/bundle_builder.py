from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from app.db.postgres.models.artifact_runtime import ArtifactRevision

from .dependency_packager import build_dependency_manifest_payload, package_python_dependencies


@dataclass(frozen=True)
class BuiltArtifactBundle:
    bundle_hash: str
    dependency_hash: str
    payload: bytes
    manifest: dict[str, Any]


class ArtifactBundleBuilder:
    def build_revision_bundle(self, revision: ArtifactRevision) -> BuiltArtifactBundle:
        packaged_dependencies = package_python_dependencies(revision.python_dependencies or [])
        dependency_manifest = build_dependency_manifest_payload(packaged_dependencies)
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
            "dependency_manifest": dependency_manifest,
        }

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("artifact.json", json.dumps(manifest, sort_keys=True, separators=(",", ":")))
            archive.writestr(
                "dependencies.json",
                json.dumps(dependency_manifest, sort_keys=True, separators=(",", ":")),
            )
            archive.writestr("handler.py", revision.source_code or "")
            archive.writestr("runtime/runner.py", self._runner_source())
            for packaged_file in packaged_dependencies.files:
                archive.write(packaged_file.source_path, packaged_file.archive_path)
        payload = buffer.getvalue()
        bundle_hash = sha256(payload).hexdigest()
        return BuiltArtifactBundle(
            bundle_hash=bundle_hash,
            dependency_hash=packaged_dependencies.dependency_hash,
            payload=payload,
            manifest=manifest,
        )

    @staticmethod
    def _runner_source() -> str:
        runner_path = Path(__file__).resolve().parents[2] / "artifact_worker" / "runner.py"
        return runner_path.read_text(encoding="utf-8")
