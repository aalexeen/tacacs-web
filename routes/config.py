"""Config routes: read, save, check (-P), apply (save + SIGHUP)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from auth import get_current_user, require_operator

CONFIG_PATH = Path(os.environ.get("TACACS_CONFIG", "/etc/tac_plus-ng/tac_plus-ng.cfg"))
TACACS_BIN = os.environ.get("TACACS_BIN", "/usr/local/sbin/tac_plus-ng")
TACACS_SERVICE = os.environ.get("TACACS_SERVICE", "tac_plus-ng")

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _read_config() -> str:
    if not CONFIG_PATH.exists():
        raise HTTPException(status_code=404, detail=f"Config file not found: {CONFIG_PATH}")
    return CONFIG_PATH.read_text()


def _write_config(content: str) -> None:
    CONFIG_PATH.write_text(content)


def _check_config(content: str) -> dict:
    """Run tac_plus-ng -P on a temp file. Returns {ok, output}."""
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".cfg", delete=False) as f:
        f.write(content)
        tmp = f.name
    try:
        result = subprocess.run(
            ["sudo", TACACS_BIN, "-P", tmp],
            capture_output=True, text=True, timeout=10
        )
        ok = result.returncode == 0
        output = (result.stdout + result.stderr).strip()
        return {"ok": ok, "output": output}
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": "Timeout running config check"}
    finally:
        Path(tmp).unlink(missing_ok=True)


# ------------------------------------------------------------------
# Pages
# ------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def editor_page(request: Request, user: dict = Depends(get_current_user)):
    content = _read_config()
    return templates.TemplateResponse(
        request, "editor.html",
        {"user": user, "content": content, "config_path": str(CONFIG_PATH)}
    )


# ------------------------------------------------------------------
# HTMX partials
# ------------------------------------------------------------------

@router.post("/config/check", response_class=HTMLResponse)
async def check_config(
    request: Request,
    user: dict = Depends(require_operator),
):
    form = await request.form()
    content = form.get("content", "")
    result = _check_config(content)
    return templates.TemplateResponse(
        request, "_check_result.html",
        {"ok": result["ok"], "output": result["output"]}
    )


@router.post("/config/save", response_class=HTMLResponse)
async def save_config(
    request: Request,
    user: dict = Depends(require_operator),
):
    form = await request.form()
    content = form.get("content", "")

    # Check before saving
    result = _check_config(content)
    if not result["ok"]:
        return templates.TemplateResponse(
            request, "_check_result.html",
            {"ok": False, "output": "Config has errors — not saved:\n" + result["output"]}
        )

    _write_config(content)
    return templates.TemplateResponse(
        request, "_check_result.html",
        {"ok": True, "output": "Config saved successfully."}
    )


@router.post("/config/apply", response_class=HTMLResponse)
async def apply_config(
    request: Request,
    user: dict = Depends(require_operator),
):
    """Save config + send SIGHUP to reload daemon without full restart."""
    form = await request.form()
    content = form.get("content", "")

    result = _check_config(content)
    if not result["ok"]:
        return templates.TemplateResponse(
            request, "_check_result.html",
            {"ok": False, "output": "Config has errors — not applied:\n" + result["output"]}
        )

    _write_config(content)

    try:
        reload = subprocess.run(
            ["sudo", "systemctl", "reload", TACACS_SERVICE],
            capture_output=True, text=True, timeout=10
        )
        if reload.returncode != 0:
            return templates.TemplateResponse(
                request, "_check_result.html",
                {"ok": False, "output": "Saved but reload failed:\n" + (reload.stdout + reload.stderr).strip()}
            )
    except subprocess.TimeoutExpired:
        return templates.TemplateResponse(
            request, "_check_result.html",
            {"ok": False, "output": "Saved but reload timed out"}
        )

    return templates.TemplateResponse(
        request, "_check_result.html",
        {"ok": True, "output": "Config saved and daemon reloaded."}
    )
