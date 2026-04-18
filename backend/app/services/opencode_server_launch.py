from __future__ import annotations

OFFICIAL_OPENCODE_INSTALL_DIR = "$HOME/.opencode/bin"


def build_official_opencode_bootstrap_command(*, host: str, port: int) -> str:
    resolved_host = str(host or "127.0.0.1").strip() or "127.0.0.1"
    resolved_port = int(port)
    return (
        f"export PATH=\"{OFFICIAL_OPENCODE_INSTALL_DIR}:$PATH\"; "
        "if ! command -v opencode >/dev/null 2>&1; then "
        "if ! command -v curl >/dev/null 2>&1; then "
        "echo 'curl is required to install the official OpenCode CLI' >&2; exit 1; "
        "fi; "
        "curl -fsSL https://opencode.ai/install | bash -s -- --no-modify-path; "
        f"export PATH=\"{OFFICIAL_OPENCODE_INSTALL_DIR}:$PATH\"; "
        "fi; "
        f"exec opencode serve --hostname {resolved_host} --port {resolved_port}"
    )
