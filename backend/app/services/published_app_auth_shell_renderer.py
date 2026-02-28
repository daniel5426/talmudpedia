from __future__ import annotations

import html
import json
from typing import Any

from app.db.postgres.models.published_apps import PublishedApp
from app.services.published_app_auth_templates import get_auth_template


def _style_for_template(auth_template_key: str) -> dict[str, str]:
    try:
        template = get_auth_template(auth_template_key or "auth-classic")
        tokens = dict(template.style_tokens or {})
    except Exception:
        tokens = {"layout": "card", "tone": "neutral"}

    layout = tokens.get("layout", "card")
    tone = tokens.get("tone", "neutral")

    if layout == "split":
        container = "grid grid-cols-1 lg:grid-cols-2 min-h-screen"
        hero = "display:flex;"
    elif layout == "minimal":
        container = "min-h-screen flex items-center justify-center p-4"
        hero = "display:none;"
    else:
        container = "min-h-screen flex items-center justify-center p-4"
        hero = "display:none;"

    return {
        "layout": layout,
        "tone": tone,
        "container_class": container,
        "hero_style": hero,
    }


def _safe_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=True).replace("</", "<\\/")


def render_published_app_auth_shell(
    *,
    app: PublishedApp,
    return_to: str,
    action: str = "login",
    error_message: str | None = None,
) -> str:
    style = _style_for_template(str(app.auth_template_key or "auth-classic"))
    app_name = html.escape(app.name or "Published App")
    description = html.escape(app.description or "Authenticate to access this app.")
    logo_url = html.escape((app.logo_url or "").strip())
    providers = [str(p).strip().lower() for p in list(app.auth_providers or []) if str(p).strip()]
    has_password = "password" in providers
    has_google = "google" in providers
    has_external_exchange = bool(app.external_auth_oidc)
    initial_mode = "signup" if action == "signup" and has_password else "login"

    boot_payload = {
        "returnTo": return_to or "/",
        "mode": initial_mode,
        "providers": providers,
        "hasExternalExchange": has_external_exchange,
        "error": error_message or "",
    }

    tone_css = {
        "neutral": ("#0b1020", "#f6f7fb", "#ffffff"),
        "soft": ("#102018", "#f1f7f3", "#ffffff"),
        "editorial": ("#1a1022", "#f7f1fb", "#ffffff"),
    }.get(style["tone"], ("#0b1020", "#f6f7fb", "#ffffff"))
    text_color, bg_color, card_color = tone_css

    password_tabs_html = ""
    if has_password:
        password_tabs_html = """
          <div class="tabs" role="tablist" aria-label="Authentication mode">
            <button id="tab-login" type="button" data-mode="login" class="tab-btn">Login</button>
            <button id="tab-signup" type="button" data-mode="signup" class="tab-btn">Sign Up</button>
          </div>
        """

    google_html = ""
    if has_google:
        google_html = """
          <button type="button" id="google-button" class="button button-secondary">Continue with Google</button>
        """

    exchange_html = ""
    if has_external_exchange:
        exchange_html = """
          <details class="exchange-panel">
            <summary>External SSO token exchange</summary>
            <p class="muted">Paste an external OIDC JWT to exchange for an app session (integration flow).</p>
            <textarea id="exchange-token" rows="4" placeholder="eyJhbGciOi..."></textarea>
            <button type="button" id="exchange-button" class="button button-secondary">Exchange Token</button>
          </details>
        """

    logo_html = f'<img src="{logo_url}" alt="{app_name} logo" class="logo" />' if logo_url else ""
    error_html = (
        f'<div id="error-box" class="error">{html.escape(error_message)}</div>' if error_message else '<div id="error-box" class="error hidden"></div>'
    )

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{app_name} - Sign In</title>
    <style>
      :root {{
        color-scheme: light;
        --bg: {bg_color};
        --text: {text_color};
        --card: {card_color};
        --muted: #5f6b85;
        --border: #d8deea;
        --accent: #0f5fff;
        --accent-2: #eef3ff;
        --danger: #b42318;
        --danger-bg: #fdecec;
      }}
      * {{ box-sizing: border-box; }}
      body {{ margin:0; font-family: ui-sans-serif, system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); }}
      .shell {{ {'' if style['layout'] != 'split' else 'display:grid;grid-template-columns:1fr;'} min-height:100vh; }}
      @media (min-width: 960px) {{
        .shell.split {{ display:grid; grid-template-columns: 1.05fr 1fr; }}
      }}
      .hero {{
        {style["hero_style"]}
        padding: 48px;
        background:
          radial-gradient(circle at 20% 20%, rgba(15,95,255,.10), transparent 50%),
          radial-gradient(circle at 80% 10%, rgba(15,95,255,.12), transparent 45%),
          linear-gradient(180deg, rgba(255,255,255,.75), rgba(255,255,255,.35));
        border-right: 1px solid rgba(0,0,0,.05);
      }}
      .hero-inner {{ max-width: 420px; }}
      .hero h1 {{ margin: 14px 0 8px; font-size: 2rem; line-height: 1.1; }}
      .hero p {{ margin: 0; color: var(--muted); line-height: 1.45; }}
      .panel-wrap {{ min-height:100vh; display:flex; align-items:center; justify-content:center; padding: 18px; }}
      .panel {{
        width: 100%;
        max-width: 440px;
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: 16px;
        box-shadow: 0 12px 40px rgba(16,24,40,.08);
        padding: 18px;
      }}
      .minimal .panel {{
        border-radius: 12px;
        box-shadow: none;
      }}
      .brand {{
        display:flex;
        align-items:center;
        gap:12px;
        margin-bottom: 10px;
      }}
      .logo {{
        width: 40px; height: 40px; border-radius: 10px; object-fit: cover;
        border: 1px solid rgba(0,0,0,.08);
        background: #fff;
      }}
      .brand h2 {{ margin:0; font-size: 1.1rem; }}
      .brand p {{ margin:2px 0 0; color: var(--muted); font-size: .92rem; }}
      .tabs {{
        display:grid; grid-template-columns:1fr 1fr; gap:6px;
        background:#f5f7fb; border:1px solid var(--border); border-radius: 12px; padding:4px; margin: 12px 0 14px;
      }}
      .tab-btn {{
        border:0; background:transparent; padding:8px 10px; border-radius: 8px; cursor:pointer; color: var(--muted); font-weight:600;
      }}
      .tab-btn.active {{ background:#fff; color: var(--text); box-shadow: 0 1px 2px rgba(16,24,40,.08); }}
      form {{ display:flex; flex-direction:column; gap:10px; }}
      label {{ font-size:.9rem; font-weight:600; }}
      input, textarea {{
        width:100%; border:1px solid var(--border); border-radius:10px; padding:10px 12px; font:inherit; background:#fff; color: var(--text);
      }}
      textarea {{ resize: vertical; min-height: 86px; }}
      .field {{ display:flex; flex-direction:column; gap:6px; }}
      .button {{
        border:1px solid transparent; border-radius:10px; padding:10px 12px; font-weight:600; cursor:pointer; font:inherit;
      }}
      .button[disabled] {{ opacity:.7; cursor:wait; }}
      .button-primary {{ background: var(--accent); color: white; }}
      .button-secondary {{ background: white; color: var(--text); border-color: var(--border); margin-top: 8px; width: 100%; }}
      .hidden {{ display:none !important; }}
      .muted {{ color: var(--muted); font-size: .9rem; }}
      .row {{ display:flex; gap:8px; }}
      .error {{
        margin-top: 10px; border: 1px solid #f3c9c9; background: var(--danger-bg); color: var(--danger);
        border-radius: 10px; padding: 10px 12px; font-size:.9rem;
      }}
      .exchange-panel {{ margin-top: 12px; border-top:1px solid var(--border); padding-top: 10px; }}
      .exchange-panel summary {{ cursor:pointer; font-weight:600; }}
      .footer {{ margin-top:12px; color: var(--muted); font-size:.85rem; text-align:center; }}
    </style>
  </head>
  <body>
    <div class="shell {html.escape(style['layout'])}">
      <aside class="hero">
        <div class="hero-inner">
          {logo_html}
          <h1>{app_name}</h1>
          <p>{description}</p>
        </div>
      </aside>
      <main class="panel-wrap {html.escape(style['layout'])}">
        <section class="panel" aria-label="Authentication">
          <div class="brand">
            {logo_html}
            <div>
              <h2>{app_name}</h2>
              <p>{description}</p>
            </div>
          </div>
          {password_tabs_html}
          <form id="auth-form">
            <div id="field-name" class="field hidden">
              <label for="full-name">Full name</label>
              <input id="full-name" autocomplete="name" />
            </div>
            <div class="field">
              <label for="email">Email</label>
              <input id="email" type="email" autocomplete="email" required />
            </div>
            <div class="field">
              <label for="password">Password</label>
              <input id="password" type="password" autocomplete="current-password" minlength="6" required />
            </div>
            <button type="submit" id="submit-button" class="button button-primary">{'Sign Up' if initial_mode == 'signup' else 'Login'}</button>
          </form>
          {google_html}
          {exchange_html}
          {error_html}
          <p class="footer">This sign-in page is hosted by the platform and branded for this app.</p>
        </section>
      </main>
    </div>
    <script>
      (function() {{
        const config = {_safe_json(boot_payload)};
        const authForm = document.getElementById("auth-form");
        const submitButton = document.getElementById("submit-button");
        const errorBox = document.getElementById("error-box");
        const fullNameField = document.getElementById("field-name");
        const emailEl = document.getElementById("email");
        const passwordEl = document.getElementById("password");
        const fullNameEl = document.getElementById("full-name");
        const googleButton = document.getElementById("google-button");
        const exchangeButton = document.getElementById("exchange-button");
        const exchangeTokenEl = document.getElementById("exchange-token");
        let mode = (config.mode === "signup") ? "signup" : "login";

        function setError(message) {{
          if (!errorBox) return;
          const text = String(message || "").trim();
          errorBox.textContent = text || "";
          errorBox.classList.toggle("hidden", !text);
        }}

        function setMode(nextMode) {{
          mode = nextMode === "signup" ? "signup" : "login";
          if (fullNameField) {{
            fullNameField.classList.toggle("hidden", mode !== "signup");
          }}
          if (submitButton) {{
            submitButton.textContent = mode === "signup" ? "Create Account" : "Login";
          }}
          document.querySelectorAll(".tab-btn").forEach((btn) => {{
            const active = btn.getAttribute("data-mode") === mode;
            btn.classList.toggle("active", active);
            btn.setAttribute("aria-selected", active ? "true" : "false");
          }});
          setError("");
        }}

        document.querySelectorAll(".tab-btn").forEach((btn) => {{
          btn.addEventListener("click", () => setMode(btn.getAttribute("data-mode") || "login"));
        }});

        async function postJson(path, payload) {{
          const resp = await fetch(path, {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            credentials: "same-origin",
            body: JSON.stringify(payload || {{}}),
          }});
          let data = {{}};
          try {{ data = await resp.json(); }} catch (_err) {{}}
          if (!resp.ok) {{
            throw new Error(data.detail || data.message || "Authentication failed");
          }}
          return data;
        }}

        authForm && authForm.addEventListener("submit", async (event) => {{
          event.preventDefault();
          setError("");
          submitButton && (submitButton.disabled = true);
          try {{
            const payload = {{
              email: String(emailEl && emailEl.value || "").trim(),
              password: String(passwordEl && passwordEl.value || ""),
            }};
            if (mode === "signup") {{
              const fullName = String(fullNameEl && fullNameEl.value || "").trim();
              if (fullName) payload.full_name = fullName;
            }}
            const endpoint = mode === "signup" ? "/_talmudpedia/auth/signup" : "/_talmudpedia/auth/login";
            await postJson(endpoint, payload);
            window.location.assign(config.returnTo || window.location.pathname);
          }} catch (err) {{
            setError(err instanceof Error ? err.message : "Authentication failed");
          }} finally {{
            submitButton && (submitButton.disabled = false);
          }}
        }});

        if (googleButton) {{
          googleButton.addEventListener("click", () => {{
            const target = "/_talmudpedia/auth/google/start?return_to=" + encodeURIComponent(config.returnTo || window.location.pathname);
            window.location.assign(target);
          }});
        }}

        if (exchangeButton && exchangeTokenEl) {{
          exchangeButton.addEventListener("click", async () => {{
            setError("");
            exchangeButton.disabled = true;
            try {{
              const token = String(exchangeTokenEl.value || "").trim();
              if (!token) throw new Error("External token is required");
              await postJson("/_talmudpedia/auth/exchange", {{ token }});
              window.location.assign(config.returnTo || window.location.pathname);
            }} catch (err) {{
              setError(err instanceof Error ? err.message : "Token exchange failed");
            }} finally {{
              exchangeButton.disabled = false;
            }}
          }});
        }}

        setMode(mode);
        if (config.error) setError(config.error);
      }})();
    </script>
  </body>
</html>
"""

