from pathlib import Path
from typing import Optional, Dict, Any
from uuid import UUID, uuid4
from datetime import datetime, timezone
import json

from fastapi import UploadFile


class PipelineInputStorage:
    def __init__(self, base_path: Optional[str] = None):
        self._base_path = Path(base_path or "/tmp/talmudpedia/pipeline_inputs").resolve()

    def _ensure_tenant_dir(self, tenant_id: UUID) -> Path:
        tenant_dir = self._base_path / str(tenant_id)
        tenant_dir.mkdir(parents=True, exist_ok=True)
        return tenant_dir

    def _metadata_path(self, tenant_dir: Path, upload_id: str) -> Path:
        return tenant_dir / f"{upload_id}.json"

    def is_managed_path(self, path: str) -> bool:
        resolved = Path(path).resolve()
        try:
            resolved.relative_to(self._base_path)
            return True
        except ValueError:
            return False

    def path_exists(self, path: str) -> bool:
        return Path(path).exists()

    async def save_upload(self, tenant_id: UUID, file: UploadFile) -> Dict[str, Any]:
        tenant_dir = self._ensure_tenant_dir(tenant_id)
        filename = file.filename or "upload"
        extension = Path(filename).suffix
        upload_id = uuid4().hex
        output_path = tenant_dir / f"{upload_id}{extension}"
        content = await file.read()
        output_path.write_bytes(content)
        metadata = {
            "upload_id": upload_id,
            "tenant_id": str(tenant_id),
            "filename": filename,
            "path": str(output_path),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "job_id": None,
        }
        self._metadata_path(tenant_dir, upload_id).write_text(json.dumps(metadata))
        return metadata

    def cleanup_expired(self, ttl_seconds: int) -> int:
        cutoff = datetime.now(timezone.utc).timestamp() - ttl_seconds
        removed = 0
        if not self._base_path.exists():
            return removed
        for metadata_file in self._base_path.rglob("*.json"):
            try:
                metadata = json.loads(metadata_file.read_text())
                created_at = metadata.get("created_at")
                job_id = metadata.get("job_id")
                if not created_at or job_id:
                    continue
                created_ts = datetime.fromisoformat(created_at).timestamp()
                if created_ts >= cutoff:
                    continue
                path = metadata.get("path")
                if path:
                    try:
                        Path(path).unlink(missing_ok=True)
                    except Exception:
                        pass
                metadata_file.unlink(missing_ok=True)
                removed += 1
            except Exception:
                continue
        return removed

    def assign_job(self, tenant_id: UUID, upload_id: str, job_id: UUID) -> bool:
        tenant_dir = self._base_path / str(tenant_id)
        metadata_path = self._metadata_path(tenant_dir, upload_id)
        if not metadata_path.exists():
            return False
        try:
            metadata = json.loads(metadata_path.read_text())
            metadata["job_id"] = str(job_id)
            metadata_path.write_text(json.dumps(metadata))
            return True
        except Exception:
            return False
