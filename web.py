"""TACACS+ Web UI — FastAPI application."""

from __future__ import annotations

import os

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from auth import (
    COOKIE_NAME,
    SESSION_MAX_AGE,
    create_session_token,
    get_current_user,
    verify_password,
)
from routes.config import router as config_router
from routes.daemon import router as daemon_router
from routes.logs import router as logs_router
from routes.backups import router as backups_router
from routes.users import router as users_router

# ------------------------------------------------------------------
# App
# ------------------------------------------------------------------

app = FastAPI(title="TACACS+ Web UI", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

app.include_router(config_router)
app.include_router(daemon_router)
app.include_router(logs_router)
app.include_router(backups_router)
app.include_router(users_router)


# ------------------------------------------------------------------
# Exception handlers
# ------------------------------------------------------------------

from fastapi import HTTPException
from fastapi.responses import Response

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 401:
        if request.headers.get("HX-Request") == "true":
            return Response(status_code=200, headers={"HX-Redirect": "/login"})
        return RedirectResponse("/login", status_code=302)
    return HTMLResponse(
        content=f"<h1>{exc.status_code}</h1><p>{exc.detail}</p>",
        status_code=exc.status_code,
    )


# ------------------------------------------------------------------
# Auth routes
# ------------------------------------------------------------------

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(
        request, "login.html", {"error": None}
    )


@app.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    from auth import get_user_by_username
    user = get_user_by_username(username)
    if user is None or not user.get("enabled", True) or \
       not verify_password(password, user["password_hash"]):
        return templates.TemplateResponse(
            request, "login.html",
            {"error": "Invalid username or password."},
            status_code=401,
        )
    token = create_session_token(user["id"])
    response = RedirectResponse("/", status_code=302)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=SESSION_MAX_AGE,
        secure=False,
    )
    return response


@app.post("/logout")
async def logout(request: Request, user: dict = Depends(get_current_user)):
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    return response


# ------------------------------------------------------------------
# Profile (change own password)
# ------------------------------------------------------------------

@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, user: dict = Depends(get_current_user)):
    return templates.TemplateResponse(
        request, "profile.html",
        {"user": user, "error": None, "success": None}
    )


@app.post("/profile", response_class=HTMLResponse)
async def profile_change_password(
    request: Request,
    user: dict = Depends(get_current_user),
):
    from auth import update_user_password, verify_password, get_user_by_id
    form = await request.form()
    current_password = form.get("current_password", "")
    new_password = form.get("new_password", "")
    confirm_password = form.get("confirm_password", "")

    full_user = get_user_by_id(user["id"])

    def _err(msg):
        return templates.TemplateResponse(
            request, "profile.html",
            {"user": user, "error": msg, "success": None}, status_code=400
        )

    if not verify_password(current_password, full_user["password_hash"]):
        return _err("Current password is incorrect.")
    if new_password != confirm_password:
        return _err("New passwords do not match.")
    if len(new_password) < 8:
        return _err("Password must be at least 8 characters.")

    update_user_password(user["id"], new_password)
    return templates.TemplateResponse(
        request, "profile.html",
        {"user": user, "error": None, "success": "Password changed successfully."}
    )
