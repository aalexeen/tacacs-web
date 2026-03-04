# Repository Guidelines

## Project Structure & Module Organization
Core application code lives at the repository root:
- `web.py`: FastAPI entrypoint and top-level auth/profile routes.
- `auth.py`: session cookie auth, role checks, and `users.json` persistence.
- `routes/`: feature routers (`config.py`, `daemon.py`, `logs.py`, `backups.py`, `users.py`).
- `templates/`: Jinja2 pages and HTMX partials (`_*.html`).
- `static/`: static assets (currently `static/js/`).
- `manage_users.py`: CLI for user lifecycle tasks.
- `install.sh`: production-style setup (venv, sudoers, systemd).

## Build, Test, and Development Commands
- `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`: create local env and install deps.
- `cp .env.example .env`: create local config (set `SESSION_SECRET` before real use).
- `.venv/bin/uvicorn web:app --host 127.0.0.1 --port 8080`: run locally.
- `python manage_users.py add <username> <role>`: bootstrap users (`admin|operator|viewer`).
- `sudo bash install.sh`: full host install with systemd/sudoers.
- `sudo bash install.sh --uninstall`: remove installed service artifacts.

## Coding Style & Naming Conventions
- Follow PEP 8 with 4-space indentation and type hints (`dict | None`, `list[dict]`).
- Use `snake_case` for functions/variables/modules, `UPPER_SNAKE_CASE` for constants.
- Keep route handlers minimal; move reusable auth/user logic into `auth.py`.
- Keep templates descriptive and aligned with route purpose (e.g., `users.html`, `_daemon_status.html`).

## Testing Guidelines
There is no automated test suite yet. For changes, run focused manual checks:
- login/logout flow,
- config validation/apply,
- daemon actions by role,
- backup create/restore/delete,
- user CRUD and password reset.
If you add tests, use `pytest` with files under `tests/` named `test_<feature>.py`.

## Commit & Pull Request Guidelines
Git history is currently minimal (`Initial commit`), so use clear, imperative commit subjects, e.g.:
- `Add role guard for daemon stop action`
- `Fix backup diff rendering for empty files`

PRs should include:
- short problem/solution summary,
- linked issue (if any),
- manual verification steps,
- screenshots for template/UI changes.

## Security & Configuration Tips
- Never commit `.env`, real secrets, or production `users.json`.
- Keep `SESSION_SECRET` unique per deployment.
- Validate sudoers changes with `visudo -c` and keep command scope minimal.
