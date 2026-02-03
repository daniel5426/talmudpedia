#!/usr/bin/env python3
"""
Artifact Scaffolding CLI Tool

Creates a new artifact directory with template files.

Usage:
    python scripts/create_artifact.py my-org/my-operator
    python scripts/create_artifact.py custom/text-splitter --input enriched_documents --output chunks
"""
import argparse
import os
from pathlib import Path

TEMPLATE_ARTIFACT_YAML = '''id: {artifact_id}
version: "1.0.0"
display_name: {display_name}
category: {category}
description: {description}

input_type: {input_type}
output_type: {output_type}

config:
  - name: example_param
    type: string
    default: ""
    description: Example configuration parameter

tags:
  - {tag}
'''

TEMPLATE_HANDLER_PY = '''"""
{display_name} Artifact

{description}
"""
from typing import Any, Dict, List


def execute(context) -> List[Dict[str, Any]]:
    """
    Execute the operator.
    
    Args:
        context: ExecutionContext with:
            - input_data: Input from previous operator
            - config: Dict with configuration values
            - metadata: Optional execution metadata
    
    Returns:
        List of processed documents.
    """
    input_data = context.input_data
    config = context.config
    
    # Get configuration
    example_param = config.get("example_param", "")
    
    # Ensure input is a list
    documents = input_data if isinstance(input_data, list) else [input_data]
    
    result = []
    for doc in documents:
        # TODO: Implement your transformation logic here
        if isinstance(doc, dict):
            # Example: pass through with minor modification
            result.append(doc)
        else:
            result.append({{"text": str(doc)}})
    
    return result
'''

TEMPLATE_README = '''# {display_name}

{description}

## Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `example_param` | string | "" | Example configuration parameter |

## Usage

This artifact can be used in any RAG pipeline by referencing:
```
{artifact_id}
```

## Testing

```bash
cd /backend
python -c "
from artifacts.{path}.handler import execute

class MockContext:
    input_data = [{{'text': 'Hello World'}}]
    config = {{'example_param': 'test'}}
    metadata = {{}}

result = execute(MockContext())
print(result)
"
```
'''

def slugify(text: str) -> str:
    """Convert text to slug format."""
    return text.lower().replace(" ", "_").replace("-", "_")


def titleize(text: str) -> str:
    """Convert slug to title format."""
    return text.replace("-", " ").replace("_", " ").title()


def main():
    parser = argparse.ArgumentParser(description="Create a new artifact")
    parser.add_argument("artifact_id", help="Full artifact ID (e.g., 'custom/text-splitter')")
    parser.add_argument("--input", default="raw_documents", help="Input data type")
    parser.add_argument("--output", default="normalized_documents", help="Output data type")
    parser.add_argument("--category", default="normalization", help="Operator category")
    parser.add_argument("--description", default="A custom operator", help="Description")
    
    args = parser.parse_args()
    
    # Parse artifact ID
    artifact_id = args.artifact_id
    parts = artifact_id.split("/")
    if len(parts) != 2:
        print(f"Error: artifact_id must be in format 'namespace/name', got: {artifact_id}")
        return 1
    
    namespace, name = parts
    display_name = titleize(name)
    
    # Determine paths
    script_dir = Path(__file__).parent
    backend_dir = script_dir.parent
    artifacts_dir = backend_dir / "artifacts"
    artifact_path = artifacts_dir / namespace / name
    
    # Check if already exists
    if artifact_path.exists():
        print(f"Error: Artifact already exists at {artifact_path}")
        return 1
    
    # Create directory
    artifact_path.mkdir(parents=True, exist_ok=True)
    
    # Create artifact.yaml
    yaml_content = TEMPLATE_ARTIFACT_YAML.format(
        artifact_id=artifact_id,
        display_name=display_name,
        category=args.category,
        description=args.description,
        input_type=args.input,
        output_type=args.output,
        tag=name.replace("-", "").replace("_", "")
    )
    (artifact_path / "artifact.yaml").write_text(yaml_content)
    
    # Create handler.py
    handler_content = TEMPLATE_HANDLER_PY.format(
        display_name=display_name,
        description=args.description
    )
    (artifact_path / "handler.py").write_text(handler_content)
    
    # Create README.md
    readme_content = TEMPLATE_README.format(
        display_name=display_name,
        description=args.description,
        artifact_id=artifact_id,
        path=f"{namespace}.{name.replace('-', '_')}"
    )
    (artifact_path / "README.md").write_text(readme_content)
    
    # Create tests directory
    tests_dir = artifact_path / "tests"
    tests_dir.mkdir(exist_ok=True)
    (tests_dir / "__init__.py").touch()
    
    print(f"✅ Created artifact: {artifact_id}")
    print(f"   Path: {artifact_path}")
    print(f"\nFiles created:")
    print(f"   - artifact.yaml")
    print(f"   - handler.py")
    print(f"   - README.md")
    print(f"   - tests/")
    print(f"\nNext steps:")
    print(f"   1. Edit handler.py to implement your logic")
    print(f"   2. Update artifact.yaml with your config schema")
    print(f"   3. Restart the backend to register the artifact")
    
    return 0


if __name__ == "__main__":
    exit(main())
