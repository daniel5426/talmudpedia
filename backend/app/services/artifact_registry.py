"""
Artifact Registry Service - Discovers and indexes code artifacts.

This service scans the /backend/artifacts directory for operator artifacts,
parses their artifact.yaml manifests, and registers them as OperatorSpecs.
"""
import os
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
import yaml

from app.rag.pipeline.registry import (
    OperatorSpec,
    OperatorCategory,
    DataType,
    ConfigFieldSpec,
    ConfigFieldType,
)

logger = logging.getLogger(__name__)

# Default artifacts directory (relative to backend root)
ARTIFACTS_DIR = Path(__file__).parent.parent.parent / "artifacts"


class ArtifactRegistryService:
    """
    Service that discovers and indexes code artifacts from the filesystem.
    
    Scans the artifacts directory for operator definitions and converts
    them to OperatorSpec objects that can be merged with the built-in registry.
    """
    
    _instance: Optional["ArtifactRegistryService"] = None
    _artifacts: Dict[str, OperatorSpec] = {}
    _artifact_versions: Dict[str, Dict[str, OperatorSpec]] = {} # id -> {version: spec}
    _artifact_paths: Dict[str, Dict[str, Path]] = {}  # id -> {version: path}

    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._artifacts = {}
        self._artifact_versions = {}
        self._artifact_paths = {}
        self.scan_artifacts()

    
    def scan_artifacts(self, artifacts_dir: Optional[Path] = None) -> int:
        """
        Scan the artifacts directory and register all valid artifacts.
        
        Args:
            artifacts_dir: Optional custom path to artifacts directory.
            
        Returns:
            Number of artifacts successfully registered.
        """
        scan_dir = artifacts_dir or ARTIFACTS_DIR
        
        if not scan_dir.exists():
            logger.warning(f"Artifacts directory does not exist: {scan_dir}")
            return 0
        
        count = 0
        # Walk through all subdirectories looking for artifact.yaml files
        for root, dirs, files in os.walk(scan_dir):
            if "artifact.yaml" in files:
                artifact_path = Path(root) / "artifact.yaml"
                try:
                    spec = self._load_artifact(artifact_path)
                    if spec:
                        aid = spec.operator_id
                        aver = spec.version
                        
                        # Register in versions map
                        if aid not in self._artifact_versions:
                            self._artifact_versions[aid] = {}
                            self._artifact_paths[aid] = {}
                        
                        self._artifact_versions[aid][aver] = spec
                        self._artifact_paths[aid][aver] = Path(root)
                        
                        # Update "latest" if this is newer or the only one
                        if aid not in self._artifacts:
                            self._artifacts[aid] = spec
                        else:
                            # Simple version comparison (can be improved)
                            current_latest = self._artifacts[aid].version
                            if aver > current_latest: # crude but works for semver usually
                                self._artifacts[aid] = spec
                        
                        count += 1
                        logger.info(f"Registered artifact: {aid} v{aver}")
                except Exception as e:
                    logger.error(f"Failed to load artifact from {artifact_path}: {e}")
        
        logger.info(f"Artifact scan complete. Registered {count} artifacts across {len(self._artifacts)} unique IDs.")
        return count

    
    def _load_artifact(self, yaml_path: Path) -> Optional[OperatorSpec]:
        """
        Load an artifact.yaml file and convert it to an OperatorSpec.
        
        Args:
            yaml_path: Path to the artifact.yaml file.
            
        Returns:
            OperatorSpec if valid, None otherwise.
        """
        with open(yaml_path, "r") as f:
            manifest = yaml.safe_load(f)
        
        if not manifest:
            logger.warning(f"Empty manifest: {yaml_path}")
            return None
        
        # Validate required fields
        required_fields = ["id", "display_name", "input_type", "output_type"]
        for field in required_fields:
            if field not in manifest:
                logger.warning(f"Missing required field '{field}' in {yaml_path}")
                return None
        
        # Parse config fields
        config_fields = self._parse_config_fields(manifest.get("config", []))
        
        # Separate required vs optional configs
        required_config = [f for f in config_fields if f.required]
        optional_config = [f for f in config_fields if not f.required]
        
        return OperatorSpec(
            operator_id=manifest["id"],
            display_name=manifest["display_name"],
            category=OperatorCategory(manifest.get("category", "custom")),
            version=str(manifest.get("version", "1.0.0")),
            description=manifest.get("description"),
            input_type=DataType(manifest["input_type"]),
            output_type=DataType(manifest["output_type"]),
            required_config=required_config,
            optional_config=optional_config,
            tags=manifest.get("tags", []),
            is_custom=False,  # Artifacts are not "custom" in the old sense
            author=manifest.get("author"),
            scope=manifest.get("scope", "rag"),
        )
    
    def _parse_config_fields(self, config_list: List[Dict[str, Any]]) -> List[ConfigFieldSpec]:
        """Convert config list from YAML to ConfigFieldSpec objects."""
        result = []
        for cfg in config_list:
            field_type_str = cfg.get("type", "string")
            field_type_map = {
                "string": ConfigFieldType.STRING,
                "integer": ConfigFieldType.INTEGER,
                "float": ConfigFieldType.FLOAT,
                "boolean": ConfigFieldType.BOOLEAN,
                "secret": ConfigFieldType.SECRET,
                "select": ConfigFieldType.SELECT,
                "model_select": ConfigFieldType.MODEL_SELECT,
                "json": ConfigFieldType.JSON,
                "code": ConfigFieldType.CODE,
                "file_path": ConfigFieldType.FILE_PATH,
            }
            field_type = field_type_map.get(field_type_str, ConfigFieldType.STRING)
            
            result.append(ConfigFieldSpec(
                name=cfg["name"],
                field_type=field_type,
                required=cfg.get("required", False),
                default=cfg.get("default"),
                description=cfg.get("description"),
                options=cfg.get("options"),
                min_value=cfg.get("min_value"),
                max_value=cfg.get("max_value"),
                placeholder=cfg.get("placeholder"),
            ))
        return result
    
    def get_all_artifacts(self) -> Dict[str, OperatorSpec]:
        """Return all registered artifacts."""
        return self._artifacts.copy()
    
    def get_artifact(self, artifact_id: str, version: Optional[str] = None) -> Optional[OperatorSpec]:
        """Get a specific artifact by ID and optionally version."""
        if version:
            return self._artifact_versions.get(artifact_id, {}).get(version)
        return self._artifacts.get(artifact_id)
    
    def get_artifact_path(self, artifact_id: str, version: Optional[str] = None) -> Optional[Path]:
        """Get the filesystem path for an artifact."""
        if version:
            return self._artifact_paths.get(artifact_id, {}).get(version)
        
        # If no version specified, return path associated with the 'latest' spec
        spec = self._artifacts.get(artifact_id)
        if spec:
            return self._artifact_paths.get(artifact_id, {}).get(spec.version)
        return None

    
    def get_handler_module_path(self, artifact_id: str, version: Optional[str] = None) -> Optional[str]:
        """
        Get the Python module path for an artifact's handler.
        
        Returns a string like 'artifacts.builtin.html_cleaner.handler'
        that can be used with importlib.
        """
        path = self.get_artifact_path(artifact_id, version)
        if not path:
            return None
        
        # Convert filesystem path to module path
        # /backend/artifacts/builtin/html_cleaner -> artifacts.builtin.html_cleaner.handler
        try:
            relative = path.relative_to(ARTIFACTS_DIR.parent)
            module_parts = list(relative.parts)
            module_parts.append("handler")
            return ".".join(module_parts)
        except ValueError:
            # Handle case where path is outside artifacts dir (e.g. during testing)
            return None

    
    def get_agent_artifacts(self) -> list:
        """
        Return all artifacts with scope=agent as AgentArtifactSpec objects.
        
        These artifacts will appear as nodes in the Agent Builder.
        """
        from app.agent.agent_artifact_spec import AgentArtifactSpec, ArtifactScope
        
        result = []
        for artifact_id, spec in self._artifacts.items():
            yaml_path = self.get_artifact_path(artifact_id)
            if not yaml_path:
                continue
            
            manifest_path = yaml_path / "artifact.yaml"
            if not manifest_path.exists():
                continue
                
            try:
                with open(manifest_path) as f:
                    manifest = yaml.safe_load(f)
                
                if manifest.get("scope") != "agent":
                    continue
                
                result.append(AgentArtifactSpec(
                    artifact_id=spec.operator_id,
                    display_name=spec.display_name,
                    version=spec.version,
                    scope=ArtifactScope.AGENT,
                    category=manifest.get("category", "custom"),
                    description=spec.description,
                    input_type=manifest.get("input_type", "any"),
                    output_type=manifest.get("output_type", "any"),
                    reads=manifest.get("reads", []),
                    writes=manifest.get("writes", []),
                    config_schema=self._build_config_schema(manifest.get("config", [])),
                    ui=manifest.get("ui", {}),
                    author=manifest.get("author"),
                    tags=manifest.get("tags", [])
                ))
            except Exception as e:
                logger.warning(f"Failed to load agent artifact {artifact_id}: {e}")
                continue
        
        return result
    
    def _build_config_schema(self, config_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Convert config list from YAML to JSON Schema format."""
        properties = {}
        required = []
        
        type_map = {
            "string": "string",
            "integer": "integer",
            "float": "number",
            "number": "number",
            "boolean": "boolean",
            "json": "object",
            "code": "string",
            "select": "string",
        }
        
        for cfg in config_list:
            name = cfg.get("name")
            if not name:
                continue
                
            prop = {
                "type": type_map.get(cfg.get("type", "string"), "string"),
                "title": cfg.get("label", name),
            }
            
            if cfg.get("default") is not None:
                prop["default"] = cfg["default"]
            if cfg.get("description"):
                prop["description"] = cfg["description"]
            if cfg.get("options"):
                prop["enum"] = [opt.get("value", opt) if isinstance(opt, dict) else opt 
                               for opt in cfg["options"]]
            
            properties[name] = prop
            
            if cfg.get("required"):
                required.append(name)
        
        return {
            "type": "object",
            "properties": properties,
            "required": required
        }

    def refresh(self) -> int:
        """Clear cache and rescan artifacts."""
        self._artifacts.clear()
        self._artifact_versions.clear()
        self._artifact_paths.clear()
        return self.scan_artifacts()


    def promote_to_artifact(self, namespace: str, name: str, manifest: Dict[str, Any], python_code: str) -> Path:
        """
        Save a custom operator as a file-based artifact.
        
        Args:
            namespace: Artifact namespace (e.g., 'custom', 'my-org').
            name: Artifact name (e.g., 'text-splitter').
            manifest: Dict containing metadata (becomes artifact.yaml).
            python_code: The Python code (becomes handler.py).
            
        Returns:
            Path to the newly created artifact directory.
        """
        artifact_dir = ARTIFACTS_DIR / namespace / name
        artifact_dir.mkdir(parents=True, exist_ok=True)
        
        # Write artifact.yaml
        with open(artifact_dir / "artifact.yaml", "w") as f:
            yaml.dump(manifest, f, sort_keys=False)
            
        # Write handler.py
        with open(artifact_dir / "handler.py", "w") as f:
            f.write(python_code)
            
        # Create a simple README.md if it doesn't exist
        readme_path = artifact_dir / "README.md"
        if not readme_path.exists():
            readme_content = f"# {manifest.get('display_name', name)}\n\n{manifest.get('description', '')}\n"
            with open(readme_path, "w") as f:
                f.write(readme_content)
            
        # Refresh registry to include the new artifact
        self.refresh()
        
        return artifact_dir

    def update_artifact(self, artifact_id: str, manifest: Dict[str, Any], python_code: Optional[str] = None, version: Optional[str] = None) -> bool:
        """
        Update an existing file-based artifact.
        """
        path = self.get_artifact_path(artifact_id, version)
        if not path:
            logger.error(f"Cannot update artifact {artifact_id} - path not found")
            return False
        
        # Update manifest
        manifest_path = path / "artifact.yaml"
        if manifest_path.exists():
            with open(manifest_path, "w") as f:
                yaml.dump(manifest, f, sort_keys=False)
        
        # Update code if provided
        if python_code is not None:
            handler_path = path / "handler.py"
            with open(handler_path, "w") as f:
                f.write(python_code)
        
        self.refresh()
        return True

    def get_artifact_code(self, artifact_id: str, version: Optional[str] = None) -> Optional[str]:
        """Read the python code for an artifact."""
        path = self.get_artifact_path(artifact_id, version)
        if not path:
            return None
        
        handler_path = path / "handler.py"
        if not handler_path.exists():
            return None
            
        with open(handler_path, "r") as f:
            return f.read()

    def delete_artifact(self, artifact_id: str, version: Optional[str] = None) -> bool:
        """Delete an artifact from filesystem (use with caution)."""
        path = self.get_artifact_path(artifact_id, version)
        if not path:
            return False
            
        import shutil
        try:
            shutil.rmtree(path)
            self.refresh()
            return True
        except Exception as e:
            logger.error(f"Failed to delete artifact {artifact_id} at {path}: {e}")
            return False



# Singleton accessor
def get_artifact_registry() -> ArtifactRegistryService:
    """Get the singleton ArtifactRegistryService instance."""
    return ArtifactRegistryService()
