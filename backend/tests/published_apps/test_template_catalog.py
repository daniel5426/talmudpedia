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
