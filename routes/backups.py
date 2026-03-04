"""Backups routes: list, create, restore, delete, diff."""

from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from auth import require_operator, get_current_user

CONFIG_PATH = Path(os.environ.get("TACACS_CONFIG", "/etc/tac_plus-ng/tac_plus-ng.cfg"))
BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", "/var/backups/tac_plus-ng"))

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _ensure_backup_dir() -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def _list_backups() -> list[dict]:
    _ensure_backup_dir()
    backups = []
    for f in sorted(BACKUP_DIR.glob("tac_plus-ng.cfg.*"), reverse=True):
        stat = f.stat()
        backups.append({
            "name": f.name,
            "path": str(f),
            "size": stat.st_size,
            "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        })
    return backups


def _create_backup(label: str = "") -> dict:
    _ensure_backup_dir()
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    suffix = f".{ts}" + (f".{label}" if label else "")
    dest = BACKUP_DIR / f"tac_plus-ng.cfg{suffix}"
    shutil.copy2(CONFIG_PATH, dest)
    return {
        "name": dest.name,
        "path": str(dest),
        "mtime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _diff_backup(backup_name: str) -> str:
    """Return unified diff between backup and current config."""
    import difflib
    backup_path = BACKUP_DIR / backup_name
    if not backup_path.exists():
        return "Backup not found"
    current = CONFIG_PATH.read_text(errors="replace").splitlines(keepends=True)
    backup = backup_path.read_text(errors="replace").splitlines(keepends=True)
    diff = difflib.unified_diff(
        backup, current,
        fromfile=f"backup/{backup_name}",
        tofile="current",
        lineterm=""
    )
    result = "".join(diff)
    return result if result else "No differences"


# ------------------------------------------------------------------
# Pages
# ------------------------------------------------------------------

@router.get("/backups", response_class=HTMLResponse)
async def backups_page(request: Request, user: dict = Depends(get_current_user)):
    backups = _list_backups()
    return templates.TemplateResponse(
        request, "backups.html",
        {"user": user, "backups": backups}
    )


# ------------------------------------------------------------------
# HTMX actions
# ------------------------------------------------------------------

@router.post("/backups/create", response_class=HTMLResponse)
async def create_backup(request: Request, user: dict = Depends(require_operator)):
    form = await request.form()
    label = form.get("label", "").strip()
    # sanitize label
    label = "".join(c for c in label if c.isalnum() or c in "-_")[:32]
    try:
        _create_backup(label)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    backups = _list_backups()
    return templates.TemplateResponse(
        request, "_backup_list.html",
        {"user": user, "backups": backups, "message": "Backup created."}
    )


@router.post("/backups/{name}/restore", response_class=HTMLResponse)
async def restore_backup(name: str, request: Request, user: dict = Depends(require_operator)):
    backup_path = BACKUP_DIR / name
    if not backup_path.exists():
        raise HTTPException(status_code=404, detail="Backup not found")
    # Auto-backup current before restoring
    _create_backup("pre-restore")
    shutil.copy2(backup_path, CONFIG_PATH)
    backups = _list_backups()
    return templates.TemplateResponse(
        request, "_backup_list.html",
        {"user": user, "backups": backups, "message": f"Restored from {name}."}
    )


@router.delete("/backups/{name}", response_class=HTMLResponse)
async def delete_backup(name: str, request: Request, user: dict = Depends(require_operator)):
    backup_path = BACKUP_DIR / name
    if not backup_path.exists():
        raise HTTPException(status_code=404, detail="Backup not found")
    backup_path.unlink()
    backups = _list_backups()
    return templates.TemplateResponse(
        request, "_backup_list.html",
        {"user": user, "backups": backups, "message": f"Deleted {name}."}
    )


@router.get("/backups/{name}/diff", response_class=HTMLResponse)
async def diff_backup(name: str, request: Request, user: dict = Depends(get_current_user)):
    diff = _diff_backup(name)
    return templates.TemplateResponse(
        request, "_backup_diff.html",
        {"name": name, "diff": diff}
    )
