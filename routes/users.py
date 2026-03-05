"""Users management routes (admin only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from auth import (
    ROLES,
    create_user,
    delete_user,
    list_users,
    require_admin,
    set_user_enabled,
    update_user_password,
    update_user_role,
)

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/users", response_class=HTMLResponse)
async def users_page(request: Request, user: dict = Depends(require_admin)):
    users = list_users()
    return templates.TemplateResponse(
        request, "users.html",
        {"user": user, "users": users, "roles": ROLES, "error": None, "success": None}
    )


@router.post("/users", response_class=HTMLResponse)
async def add_user(request: Request, user: dict = Depends(require_admin)):
    form = await request.form()
    username = form.get("username", "").strip()
    password = form.get("password", "")
    role = form.get("role", "viewer")

    error = None
    if not username:
        error = "Username is required."
    elif len(password) < 8:
        error = "Password must be at least 8 characters."
    else:
        try:
            create_user(username, password, role)
        except ValueError as e:
            error = str(e)

    users = list_users()
    if error:
        return templates.TemplateResponse(
            request, "users.html",
            {"user": user, "users": users, "roles": ROLES, "error": error, "success": None},
            status_code=400,
        )
    return templates.TemplateResponse(
        request, "users.html",
        {"user": user, "users": users, "roles": ROLES, "error": None,
         "success": f"User '{username}' created."}
    )


@router.post("/users/{user_id}/delete", response_class=HTMLResponse)
async def remove_user(user_id: str, request: Request, user: dict = Depends(require_admin)):
    if user_id == user["id"]:
        users = list_users()
        return templates.TemplateResponse(
            request, "users.html",
            {"user": user, "users": users, "roles": ROLES,
             "error": "Cannot delete your own account.", "success": None},
            status_code=400,
        )
    delete_user(user_id)
    users = list_users()
    return templates.TemplateResponse(
        request, "users.html",
        {"user": user, "users": users, "roles": ROLES, "error": None, "success": "User deleted."}
    )


@router.post("/users/{user_id}/set-password", response_class=HTMLResponse)
async def change_password(user_id: str, request: Request, user: dict = Depends(require_admin)):
    form = await request.form()
    new_password = form.get("password", "")
    error = None
    if len(new_password) < 8:
        error = "Password must be at least 8 characters."
    else:
        update_user_password(user_id, new_password)

    users = list_users()
    return templates.TemplateResponse(
        request, "users.html",
        {"user": user, "users": users, "roles": ROLES,
         "error": error, "success": None if error else "Password updated."}
    )


@router.post("/users/{user_id}/set-role", response_class=HTMLResponse)
async def change_role(user_id: str, request: Request, user: dict = Depends(require_admin)):
    if user_id == user["id"]:
        users = list_users()
        return templates.TemplateResponse(
            request, "users.html",
            {"user": user, "users": users, "roles": ROLES,
             "error": "Cannot change your own role.", "success": None},
            status_code=400,
        )
    form = await request.form()
    new_role = form.get("role", "")
    error = None
    try:
        update_user_role(user_id, new_role)
    except ValueError as e:
        error = str(e)
    users = list_users()
    return templates.TemplateResponse(
        request, "users.html",
        {"user": user, "users": users, "roles": ROLES,
         "error": error, "success": None if error else "Role updated."}
    )


@router.post("/users/{user_id}/toggle", response_class=HTMLResponse)
async def toggle_user(user_id: str, request: Request, user: dict = Depends(require_admin)):
    if user_id == user["id"]:
        users = list_users()
        return templates.TemplateResponse(
            request, "users.html",
            {"user": user, "users": users, "roles": ROLES,
             "error": "Cannot disable your own account.", "success": None},
            status_code=400,
        )
    target = next((u for u in list_users() if u["id"] == user_id), None)
    if target:
        set_user_enabled(user_id, not target.get("enabled", True))
    users = list_users()
    return templates.TemplateResponse(
        request, "users.html",
        {"user": user, "users": users, "roles": ROLES, "error": None, "success": "Updated."}
    )
