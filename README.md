# tacacs-web

Python web UI for managing a [tac_plus-ng](https://github.com/MarcJHuber/event-driven-servers) TACACS+ server.

**Features:**
- Config editor in browser (CodeMirror 6, one-dark theme)
- Syntax check (`tac_plus-ng -P`) before save
- Apply config without restart (SIGHUP)
- Daemon control: start / stop / restart / live status
- Log viewer: access / authentication / authorization / accounting
- Config backups: create, restore, delete, unified diff
- Role-based access: admin / operator / viewer
- File-based user store (no database)

---

## Requirements

- Python 3.10+
- `tac_plus-ng` installed and managed by systemd
- Web process must be able to run certain commands via `sudo` (see [Sudoers](#sudoers))

---

## Installation

```bash
# 1. Clone or copy this directory
cd /home/alex_jd/AI/tacacs-web

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
$EDITOR .env        # set SESSION_SECRET and adjust paths

# 4. Create first admin user
python manage_users.py add admin admin

# 5. Start the server
uvicorn web:app --host 127.0.0.1 --port 8080
```

Open http://127.0.0.1:8080 and log in.

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `SESSION_SECRET` | `change-me-in-production` | Secret for signing cookies. **Must be changed.** |
| `TACACS_CONFIG` | `/etc/tac_plus-ng/tac_plus-ng.cfg` | Path to the main config file |
| `TACACS_BIN` | `/usr/local/sbin/tac_plus-ng` | Path to the binary (used for `-P` check) |
| `TACACS_LOG_DIR` | `/var/log/tac_plus-ng` | Log directory |
| `BACKUP_DIR` | `/var/backups/tac_plus-ng` | Directory for config backups |
| `USERS_FILE` | `users.json` | Path to user store |
| `TACACS_SERVICE` | `tac_plus-ng` | systemd service name |

Generate a session secret:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## Roles

| Action | admin | operator | viewer |
|---|:---:|:---:|:---:|
| View config | ✓ | ✓ | ✓ |
| Edit / save / apply config | ✓ | ✓ | |
| Check config (`-P`) | ✓ | ✓ | |
| View logs | ✓ | ✓ | ✓ |
| Daemon status | ✓ | ✓ | ✓ |
| Daemon restart | ✓ | ✓ | |
| Daemon start / stop | ✓ | | |
| View backups | ✓ | ✓ | ✓ |
| Create / restore / delete backups | ✓ | ✓ | |
| User management | ✓ | | |

---

## Sudoers

The web process needs `sudo` access for config check, SIGHUP, and systemctl. Create `/etc/sudoers.d/tacacs-web`:

```
# Replace 'www' with the user running the web process
Cmnd_Alias TACACS_WEB = \
    /usr/local/sbin/tac_plus-ng -P *, \
    /bin/systemctl start tac_plus-ng, \
    /bin/systemctl stop tac_plus-ng, \
    /bin/systemctl restart tac_plus-ng, \
    /bin/systemctl kill -s HUP tac_plus-ng, \
    /bin/systemctl is-active tac_plus-ng, \
    /bin/systemctl status tac_plus-ng *

www ALL=(root) NOPASSWD: TACACS_WEB
```

Validate with `sudo visudo -c`.

---

## User management CLI

```bash
# Add user
python manage_users.py add <username> <role>

# List all users
python manage_users.py list

# Change password
python manage_users.py passwd <username>

# Enable / disable
python manage_users.py enable <username>
python manage_users.py disable <username>

# Delete
python manage_users.py delete <username>
```

Roles: `admin`, `operator`, `viewer`.

---

## Systemd unit (optional)

`/etc/systemd/system/tacacs-web.service`:

```ini
[Unit]
Description=TACACS+ Web UI
After=network.target tac_plus-ng.service

[Service]
Type=simple
User=www
WorkingDirectory=/home/alex_jd/AI/tacacs-web
EnvironmentFile=/home/alex_jd/AI/tacacs-web/.env
ExecStart=/usr/bin/uvicorn web:app --host 127.0.0.1 --port 8080
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now tacacs-web
```

---

## Backup file naming

Backups are stored in `BACKUP_DIR` as:

```
tac_plus-ng.cfg.YYYY-MM-DD_HH-MM-SS
tac_plus-ng.cfg.YYYY-MM-DD_HH-MM-SS.label
tac_plus-ng.cfg.YYYY-MM-DD_HH-MM-SS.pre-restore   ← auto-created before restore
```

---

## Project structure

```
tacacs-web/
├── web.py                  # FastAPI app, login/logout/profile routes
├── auth.py                 # bcrypt + signed cookies + users.json store
├── manage_users.py         # CLI bootstrap tool
├── requirements.txt
├── .env.example
├── users.json              # created on first user add
├── routes/
│   ├── config.py           # GET / POST /config/*
│   ├── daemon.py           # GET/POST /daemon/*
│   ├── logs.py             # GET /logs*
│   ├── backups.py          # GET/POST/DELETE /backups/*
│   └── users.py            # GET/POST /users/*
└── templates/
    ├── base.html
    ├── login.html
    ├── editor.html         # config editor (CodeMirror 6)
    ├── logs.html
    ├── backups.html
    ├── users.html
    ├── profile.html
    ├── _check_result.html  # HTMX partial
    ├── _daemon_status.html # HTMX partial
    ├── _log_content.html   # HTMX partial
    ├── _backup_list.html   # HTMX partial
    └── _backup_diff.html   # HTMX partial
```
