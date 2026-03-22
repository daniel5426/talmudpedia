import json

from app.services import published_app_templates as template_service


def _write_valid_template_pack(root, key: str) -> None:
    pack_dir = root / key
    pack_dir.mkdir()
    (pack_dir / "src").mkdir()
    (pack_dir / "template.manifest.json").write_text(
        json.dumps(
            {
                "key": key,
                "name": "Classic Chat",
                "description": "A valid template pack",
                "thumbnail": "/thumb.png",
                "tags": ["chat"],
                "entry_file": "src/main.tsx",
            }
        ),
        encoding="utf-8",
    )
    (pack_dir / "src" / "main.tsx").write_text("export const main = true;\n", encoding="utf-8")
    (pack_dir / "vite.config.ts").write_text("export default { base: './' };\n", encoding="utf-8")


def test_list_templates_skips_directories_without_manifest(tmp_path, monkeypatch):
    invalid_dir = tmp_path / "scratch-project"
    invalid_dir.mkdir()
    (invalid_dir / "package.json").write_text('{"name":"scratch-project"}\n', encoding="utf-8")
    _write_valid_template_pack(tmp_path, "classic-chat")

    monkeypatch.setattr(template_service, "TEMPLATE_PACKS_ROOT", tmp_path)

    templates = template_service.list_templates()

    assert [template.key for template in templates] == ["classic-chat"]


def test_list_templates_returns_empty_when_no_valid_manifest_packs_exist(tmp_path, monkeypatch):
    invalid_dir = tmp_path / "scratch-project"
    invalid_dir.mkdir()
    (invalid_dir / "package.json").write_text('{"name":"scratch-project"}\n', encoding="utf-8")

    monkeypatch.setattr(template_service, "TEMPLATE_PACKS_ROOT", tmp_path)

    assert template_service.list_templates() == []


def test_build_template_files_prunes_hidden_and_ignored_directories(tmp_path, monkeypatch):
    _write_valid_template_pack(tmp_path, "classic-chat")
    pack_dir = tmp_path / "classic-chat"
    (pack_dir / "node_modules").mkdir()
    (pack_dir / "node_modules" / "ignored.js").write_text("ignored\n", encoding="utf-8")
    (pack_dir / ".cache").mkdir()
    (pack_dir / ".cache" / "ignored.json").write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(template_service, "TEMPLATE_PACKS_ROOT", tmp_path)
    monkeypatch.setattr(template_service, "build_common_bootstrap_files", lambda: {})
    monkeypatch.setattr(template_service, "build_opencode_bootstrap_files", lambda: {})
    monkeypatch.setattr(template_service, "build_runtime_sdk_package_files", lambda: {})

    files = template_service.build_template_files("classic-chat")

    assert "src/main.tsx" in files
    assert "vite.config.ts" in files
    assert not any(path.startswith("node_modules/") for path in files)
    assert not any(path.startswith(".cache/") for path in files)
