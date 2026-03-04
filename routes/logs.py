"""Logs routes: view access/authentication/authorization/accounting logs."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from auth import get_current_user

LOG_DIR = Path(os.environ.get("TACACS_LOG_DIR", "/var/log/tac_plus-ng"))
DEFAULT_LINES = 200

LOG_TYPES = {
    "access": "access.log",
    "authentication": "authentication.log",
    "authorization": "authorization.log",
    "accounting": "accounting.log",
}

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _read_log(log_type: str, lines: int = DEFAULT_LINES) -> list[str]:
    """Read last N lines from log file. Tries dated path first, then flat."""
    filename = LOG_TYPES.get(log_type)
    if not filename:
        return [f"Unknown log type: {log_type}"]

    # Try dated path: /var/log/tac_plus-ng/YYYY/MM/access-YYYY-MM-DD.log
    today = date.today()
    stem = filename.replace(".log", "")
    dated_path = LOG_DIR / f"{today.year}" / f"{today.month:02d}" / f"{stem}-{today}.log"
    flat_path = LOG_DIR / filename

    path = dated_path if dated_path.exists() else flat_path

    if not path.exists():
        return [f"Log file not found: {path}"]

    try:
        all_lines = path.read_text(errors="replace").splitlines()
        return all_lines[-lines:] if len(all_lines) > lines else all_lines
    except PermissionError:
        return [f"Permission denied: {path}"]


# ------------------------------------------------------------------
# Pages
# ------------------------------------------------------------------

@router.get("/logs", response_class=HTMLResponse)
async def logs_page(
    request: Request,
    log_type: str = "access",
    lines: int = DEFAULT_LINES,
    user: dict = Depends(get_current_user),
):
    if log_type not in LOG_TYPES:
        log_type = "access"
    log_lines = _read_log(log_type, lines)
    return templates.TemplateResponse(
        request, "logs.html",
        {
            "user": user,
            "log_type": log_type,
            "log_types": list(LOG_TYPES.keys()),
            "lines": lines,
            "log_lines": log_lines,
        }
    )


# ------------------------------------------------------------------
# HTMX partial: log content refresh
# ------------------------------------------------------------------

@router.get("/logs/content", response_class=HTMLResponse)
async def logs_content(
    request: Request,
    log_type: str = "access",
    lines: int = DEFAULT_LINES,
    user: dict = Depends(get_current_user),
):
    if log_type not in LOG_TYPES:
        log_type = "access"
    log_lines = _read_log(log_type, lines)
    return templates.TemplateResponse(
        request, "_log_content.html",
        {"log_lines": log_lines, "log_type": log_type}
    )
