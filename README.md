# tacacs-web

Python web UI for managing a [tac_plus-ng](https://github.com/MarcJHuber/event-driven-servers) TACACS+ server.

**Features:**
- Config editor in browser (CodeMirror 6) with tac_plus-ng syntax highlighting
- Password hash generator: SHA-512 crypt (`$6$...`) via `openssl passwd -6`, with Copy / Random / Clear
- Syntax check (`tac_plus-ng -P`) before save
- Apply config without restart (SIGHUP via `systemctl reload`)
- Daemon control: start / stop / restart / live status
- Log viewer: access / authorization / accounting
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

### Automatic (recommended)

```bash
sudo bash install.sh
```

The script will:
1. Create a `tacacs-web` system user
2. Create a Python venv and install dependencies
3. Generate `.env` with a random `SESSION_SECRET`
4. Set file permissions and create the backup directory
5. Write `/etc/sudoers.d/tacacs-web`
6. Install `/etc/systemd/system/tacacs-web.service`
7. Interactively create the first admin user

The script will also ask whether to configure an nginx reverse proxy and which ports to use.

Uninstall:
```bash
sudo bash install.sh --uninstall
```

### Manual

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # set SESSION_SECRET
python manage_users.py add admin admin
.venv/bin/uvicorn web:app --host 127.0.0.1 --port 8080
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

The web process needs `sudo` access for config check, reload, and daemon control. `install.sh` writes this file automatically. For manual setup, create `/etc/sudoers.d/tacacs-web`:

```
# Replace 'tacacs-web' with the user running the web process
Cmnd_Alias TACACS_WEB = \
    /usr/local/sbin/tac_plus-ng -P *, \
    /usr/bin/systemctl start tac_plus-ng, \
    /usr/bin/systemctl stop tac_plus-ng, \
    /usr/bin/systemctl restart tac_plus-ng, \
    /usr/bin/systemctl reload tac_plus-ng, \
    /usr/bin/systemctl is-active tac_plus-ng, \
    /usr/bin/systemctl status tac_plus-ng *

tacacs-web ALL=(root) NOPASSWD: TACACS_WEB
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

## Systemd unit

`install.sh` writes the unit file automatically. The generated unit looks like:

```ini
[Unit]
Description=TACACS+ Web UI
After=network.target tac_plus-ng.service
Wants=tac_plus-ng.service

[Service]
Type=simple
User=tacacs-web
Group=tacacs-web
WorkingDirectory=/opt/tacacs-web
EnvironmentFile=/opt/tacacs-web/.env
ExecStart=/opt/tacacs-web/.venv/bin/uvicorn web:app --host 127.0.0.1 --port 8080
Restart=on-failure
RestartSec=5
PrivateTmp=yes

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
├── manage_users.py         # CLI user management tool
├── install.sh              # automated install: user, venv, sudoers, systemd, nginx
├── requirements.txt
├── .env.example
├── users.json              # created on first user add (not in repo)
├── routes/
│   ├── config.py           # GET / POST /config/* (editor, check, save, apply, passwd-hash)
│   ├── daemon.py           # GET/POST /daemon/* (status, start, stop, restart)
│   ├── logs.py             # GET /logs* (access, authorization, accounting)
│   ├── backups.py          # GET/POST/DELETE /backups/* (create, restore, delete, diff)
│   └── users.py            # GET/POST /users/* (add, delete, set-password, set-role, toggle)
└── templates/
    ├── base.html
    ├── login.html
    ├── editor.html         # config editor: CodeMirror 6 + syntax highlighting + passwd hash
    ├── logs.html
    ├── backups.html
    ├── users.html
    ├── profile.html
    ├── _check_result.html  # HTMX partial: config check / save / apply result
    ├── _daemon_status.html # HTMX partial: daemon status + control buttons
    ├── _passwd_hash.html   # HTMX partial: generated $6$ hash result
    ├── _log_content.html   # HTMX partial: log lines
    ├── _backup_list.html   # HTMX partial: backup table
    └── _backup_diff.html   # HTMX partial: unified diff view
```
