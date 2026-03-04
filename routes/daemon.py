"""Daemon routes: status, start, stop, restart."""

from __future__ import annotations

import os
import subprocess

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from auth import get_current_user, require_admin, require_operator

SERVICE = os.environ.get("TACACS_SERVICE", "tac_plus-ng")

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _systemctl(action: str) -> dict:
    try:
        result = subprocess.run(
            ["sudo", "systemctl", action, SERVICE],
            capture_output=True, text=True, timeout=10
        )
        return {
            "ok": result.returncode == 0,
            "output": (result.stdout + result.stderr).strip()
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": f"Timeout running systemctl {action}"}


def _get_status() -> dict:
    """Return daemon status info."""
    try:
        result = subprocess.run(
            ["sudo", "systemctl", "is-active", SERVICE],
            capture_output=True, text=True, timeout=5
        )
        active = result.stdout.strip()  # "active", "inactive", "failed", etc.

        # Get full status for display
        status_result = subprocess.run(
            ["sudo", "systemctl", "status", SERVICE, "--no-pager", "-l"],
            capture_output=True, text=True, timeout=5
        )
        return {
            "active": active,
            "running": active == "active",
            "status_output": status_result.stdout.strip(),
        }
    except subprocess.TimeoutExpired:
        return {"active": "unknown", "running": False, "status_output": "Timeout"}


# ------------------------------------------------------------------
# HTMX partial: status badge (auto-refreshed)
# ------------------------------------------------------------------

@router.get("/daemon/status", response_class=HTMLResponse)
async def daemon_status(request: Request, user: dict = Depends(get_current_user)):
    status = _get_status()
    return templates.TemplateResponse(
        request, "_daemon_status.html",
        {"user": user, "status": status}
    )


# ------------------------------------------------------------------
# Actions
# ------------------------------------------------------------------

@router.post("/daemon/restart", response_class=HTMLResponse)
async def daemon_restart(request: Request, user: dict = Depends(require_operator)):
    result = _systemctl("restart")
    status = _get_status()
    return templates.TemplateResponse(
        request, "_daemon_status.html",
        {"user": user, "status": status, "action_result": result}
    )


@router.post("/daemon/start", response_class=HTMLResponse)
async def daemon_start(request: Request, user: dict = Depends(require_admin)):
    result = _systemctl("start")
    status = _get_status()
    return templates.TemplateResponse(
        request, "_daemon_status.html",
        {"user": user, "status": status, "action_result": result}
    )


@router.post("/daemon/stop", response_class=HTMLResponse)
async def daemon_stop(request: Request, user: dict = Depends(require_admin)):
    result = _systemctl("stop")
    status = _get_status()
    return templates.TemplateResponse(
        request, "_daemon_status.html",
        {"user": user, "status": status, "action_result": result}
    )
