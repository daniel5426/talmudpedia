from __future__ import annotations

import asyncio
import os
from pathlib import Path
import shutil
import tempfile
from textwrap import dedent
from typing import Any


class CloudflareArtifactRuntimeError(RuntimeError):
    pass


class CloudflareArtifactClient:
    def _preferred_runtime_bin_dirs(self) -> list[str]:
        candidates: list[str] = []
        explicit = str(os.getenv("ARTIFACT_RUNTIME_NODE_BIN") or "").strip()
        if explicit:
            candidates.append(explicit)

        home = Path.home()
        nvm_versions_dir = home / ".nvm" / "versions" / "node"
        if nvm_versions_dir.exists():
            version_dirs = sorted(
                (path for path in nvm_versions_dir.iterdir() if path.is_dir()),
                reverse=True,
            )
            for version_dir in version_dirs:
                bin_dir = version_dir / "bin"
                if (bin_dir / "node").exists():
                    candidates.append(str(bin_dir))

        candidates.extend([
            "/opt/homebrew/bin",
            "/opt/homebrew/sbin",
        ])

        unique: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            if not candidate or candidate in seen or not Path(candidate).exists():
                continue
            seen.add(candidate)
            unique.append(candidate)
        return unique

    async def deploy_worker(
        self,
        *,
        script_name: str,
        modules: list[dict[str, Any]],
        metadata: dict[str, Any],
        namespace: str,
    ) -> dict[str, Any]:
        self._require_config()
        cloudflare_namespace = self._resolve_dispatch_namespace_name(namespace)
        with tempfile.TemporaryDirectory(prefix=f"artifact-worker-{script_name[:24]}-") as temp_dir:
            project_dir = Path(temp_dir)
            language = str(metadata.get("language") or "python").strip()
            self._write_project_files(
                project_dir=project_dir,
                script_name=script_name,
                modules=modules,
                metadata=metadata,
            )
            output = await self._run_worker_deploy(
                project_dir=project_dir,
                dispatch_namespace=cloudflare_namespace,
                language=language,
            )
        return {
            "deployment_method": "pywrangler" if language == "python" else "wrangler",
            "namespace": cloudflare_namespace,
            "script_name": script_name,
            "deploy_output": output[-12000:],
        }

    def _require_config(self) -> None:
        if not str(os.getenv("CLOUDFLARE_API_TOKEN") or "").strip():
            raise CloudflareArtifactRuntimeError("CLOUDFLARE_API_TOKEN is required")

    def _resolve_dispatch_namespace_name(self, namespace: str) -> str:
        value = str(namespace or "").strip()
        if value == "staging":
            return str(os.getenv("ARTIFACT_CF_DISPATCH_NAMESPACE_STAGING") or "talmudpedia-artifacts-staging").strip()
        if value == "production":
            return str(os.getenv("ARTIFACT_CF_DISPATCH_NAMESPACE_PRODUCTION") or "talmudpedia-artifacts-production").strip()
        return value

    def _write_project_files(
        self,
        *,
        project_dir: Path,
        script_name: str,
        modules: list[dict[str, Any]],
        metadata: dict[str, Any],
    ) -> None:
        main_module_name = str(metadata.get("main_module") or "main.py")
        entrypoint = project_dir / main_module_name
        entrypoint.parent.mkdir(parents=True, exist_ok=True)
        for module in modules:
            target = project_dir / str(module.get("name") or "")
            target.parent.mkdir(parents=True, exist_ok=True)
            content = module.get("content")
            if isinstance(content, bytes):
                target.write_bytes(content)
            else:
                target.write_text(str(content or ""), encoding="utf-8")

        compatibility_date = str(
            metadata.get("compatibility_date")
            or os.getenv("CLOUDFLARE_WORKERS_COMPATIBILITY_DATE")
            or "2026-03-24"
        ).strip()
        compatibility_flags = list(metadata.get("compatibility_flags") or ["python_workers"])
        (project_dir / "wrangler.toml").write_text(
            dedent(
                f"""
                name = "{script_name}"
                main = "{main_module_name}"
                compatibility_date = "{compatibility_date}"
                compatibility_flags = {compatibility_flags!r}
                workers_dev = false
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        (project_dir / ".wranglerignore").write_text(
            dedent(
                """
                .venv
                .venv/**
                .venv-workers
                .venv-workers/**
                __pycache__
                **/__pycache__/**
                .pytest_cache
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )

        dependencies = list((metadata.get("dependency_manifest") or {}).get("declared") or [])
        language = str(metadata.get("language") or "python").strip()
        if language == "python":
            pyproject_lines = [
                "[project]",
                f'name = "{script_name}"',
                'version = "0.1.0"',
                'requires-python = ">=3.12"',
                f"dependencies = {dependencies!r}",
                "",
                "[dependency-groups]",
                'dev = ["workers-py>=1.9.1", "workers-runtime-sdk>=1.1.1"]',
                "",
            ]
            (project_dir / "pyproject.toml").write_text("\n".join(pyproject_lines), encoding="utf-8")
            return
        package_json = {
            "name": script_name,
            "version": "0.1.0",
            "private": True,
            "type": "module",
            "dependencies": {item: "latest" for item in dependencies},
        }
        import json
        (project_dir / "package.json").write_text(json.dumps(package_json, indent=2), encoding="utf-8")

    async def _run_worker_deploy(self, *, project_dir: Path, dispatch_namespace: str, language: str) -> str:
        if language == "python":
            return await self._run_python_worker_deploy(project_dir=project_dir, dispatch_namespace=dispatch_namespace)
        install_output = ""
        if (project_dir / "package.json").exists():
            install_output = await self._run_command(
                project_dir=project_dir,
                command=("pnpm", "install", "--prod", "--no-frozen-lockfile"),
                error_prefix="pnpm install failed",
            )
        deploy_output = await self._run_command(
            project_dir=project_dir,
            command=("wrangler", "deploy", "--dispatch-namespace", dispatch_namespace),
            error_prefix=f"wrangler deploy failed for namespace={dispatch_namespace}",
        )
        return f"{install_output}\n{deploy_output}"

    async def _run_python_worker_deploy(self, *, project_dir: Path, dispatch_namespace: str) -> str:
        sync_output = await self._run_command(
            project_dir=project_dir,
            command=("uv", "run", "pywrangler", "sync"),
            error_prefix="pywrangler sync failed",
        )
        shutil.rmtree(project_dir / ".venv", ignore_errors=True)
        shutil.rmtree(project_dir / ".venv-workers", ignore_errors=True)
        deploy_output = await self._run_command(
            project_dir=project_dir,
            command=("wrangler", "deploy", "--dispatch-namespace", dispatch_namespace),
            error_prefix=f"wrangler deploy failed for namespace={dispatch_namespace}",
        )
        return f"{sync_output}\n{deploy_output}"

    async def _run_command(
        self,
        *,
        project_dir: Path,
        command: tuple[str, ...],
        error_prefix: str,
    ) -> str:
        env = dict(os.environ)
        runtime_bin_dirs = self._preferred_runtime_bin_dirs()
        if runtime_bin_dirs:
            env["PATH"] = os.pathsep.join([*runtime_bin_dirs, env.get("PATH", "")])
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(project_dir),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await process.communicate()
        output = (stdout or b"").decode("utf-8", errors="replace")
        if process.returncode != 0:
            raise CloudflareArtifactRuntimeError(
                f"{error_prefix}: {output[-4000:]}"
            )
        return output
