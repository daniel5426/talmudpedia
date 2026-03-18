from __future__ import annotations

import json
from pathlib import Path

from app.core.env_loader import load_backend_env


def main() -> None:
    load_backend_env(override=False, prefer_test_env=True)

    from app.services.node_surface_inventory import (
        build_node_surface_inventory,
        render_node_surface_inventory_markdown,
    )

    root = Path(__file__).resolve().parents[2]
    generated_dir = root / "docs" / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)

    inventory = build_node_surface_inventory()

    json_path = generated_dir / "node_surface_inventory.json"
    markdown_path = generated_dir / "node_surface_inventory.md"

    json_path.write_text(
        json.dumps(inventory, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        render_node_surface_inventory_markdown(inventory, last_updated="2026-03-18") + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
