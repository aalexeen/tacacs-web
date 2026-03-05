#!/usr/bin/env bash
# install.sh — install and run tacacs-web via systemd
#
# Usage:
#   sudo bash install.sh              # full install
#   sudo bash install.sh --uninstall  # remove

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults — change INSTALL_DIR if needed
# ---------------------------------------------------------------------------

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${INSTALL_DIR:-/opt/tacacs-web}"  # app files go here
APP_USER="tacacs-web"
CFG_GROUP="tacacs-cfg"   # dedicated group for tac_plus-ng config access
SERVICE_NAME="tacacs-web"
VENV_DIR="$INSTALL_DIR/.venv"
PYTHON="${PYTHON:-python3}"

# Paths written to .env
TACACS_CONFIG="/etc/tac_plus-ng/tac_plus-ng.cfg"
TACACS_CFG_DIR="/etc/tac_plus-ng"
TACACS_BIN="/usr/local/sbin/tac_plus-ng"
TACACS_LOG_DIR="/var/log/tac_plus-ng"
BACKUP_DIR="/var/backups/tac_plus-ng"
TACACS_SERVICE="tac_plus-ng"

# ---------------------------------------------------------------------------

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

info()    { echo -e "${GREEN}[+]${NC} $*"; }
warn()    { echo -e "${YELLOW}[!]${NC} $*"; }
error()   { echo -e "${RED}[x]${NC} $*" >&2; }
die()     { error "$*"; exit 1; }
header()  { echo -e "\n${CYAN}--- $* ---${NC}"; }
confirm() { read -rp "$1 [y/N] " _r; [[ "${_r,,}" == "y" ]]; }

ask_port() {
    local prompt="$1" default="$2" val
    while true; do
        read -rp "  $prompt [$default]: " val
        val="${val:-$default}"
        if [[ "$val" =~ ^[0-9]+$ ]] && (( val >= 1 && val <= 65535 )); then
            echo "$val"
            return
        fi
        echo "  Invalid port. Enter a number between 1 and 65535."
    done
}

ask_ip() {
    # ask_ip <prompt> <varname>  ->  sets named variable to validated IP
    # Uses a named variable to avoid command-substitution stdin issues
    local prompt="$1" _retvar="$2" val
    local sys_ips
    sys_ips=$(ip -4 addr show | awk '/inet / {split($2,a,"/"); print a[1]}')
    echo "  Available IP addresses on this host:"
    while IFS= read -r ip; do
        echo "    $ip"
    done <<< "$sys_ips"
    echo ""
    while true; do
        read -rp "  $prompt: " val
        if [[ ! "$val" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
            echo "  Invalid IPv4 address format."
            continue
        fi
        if echo "$sys_ips" | grep -qx "$val"; then
            printf -v "$_retvar" '%s' "$val"
            return
        fi
        echo "  Address $val is not assigned to any interface on this host. Try again."
    done
}

# ---------------------------------------------------------------------------
# Require root
# ---------------------------------------------------------------------------
[[ $EUID -eq 0 ]] || die "Run as root: sudo bash install.sh"

# ---------------------------------------------------------------------------
# Uninstall
# ---------------------------------------------------------------------------
if [[ "${1:-}" == "--uninstall" ]]; then
    info "Removing $SERVICE_NAME..."
    systemctl stop    "$SERVICE_NAME" 2>/dev/null || true
    systemctl disable "$SERVICE_NAME" 2>/dev/null || true
    rm -f "/etc/systemd/system/$SERVICE_NAME.service"
    rm -f "/etc/sudoers.d/$SERVICE_NAME"
    if [[ -L "/etc/nginx/sites-enabled/$SERVICE_NAME" ]]; then
        rm -f "/etc/nginx/sites-enabled/$SERVICE_NAME"
        rm -f "/etc/nginx/sites-available/$SERVICE_NAME"
        nginx -t 2>/dev/null && systemctl reload nginx 2>/dev/null || true
        info "Nginx config removed"
    fi
    systemctl daemon-reload
    if id "$APP_USER" &>/dev/null; then
        userdel "$APP_USER" && info "User $APP_USER removed"
    fi
    if getent group "$CFG_GROUP" &>/dev/null; then
        # Only delete the group if no other members remain
        if [[ -z "$(getent group "$CFG_GROUP" | cut -d: -f4)" ]]; then
            groupdel "$CFG_GROUP" && info "Group $CFG_GROUP removed"
        else
            warn "Group $CFG_GROUP still has members — not removed"
        fi
    fi
    if [[ -d "$INSTALL_DIR" ]]; then
        if confirm "Remove $INSTALL_DIR (app files, venv, users.json)?"; then
            rm -rf "$INSTALL_DIR"
            info "Removed $INSTALL_DIR"
        else
            info "$INSTALL_DIR kept"
        fi
    fi
    info "Done."
    exit 0
fi

# ---------------------------------------------------------------------------
# Port and nginx dialog
# ---------------------------------------------------------------------------
header "Port configuration"

echo ""
echo "  tacacs-web will listen on 127.0.0.1 (loopback only)."
APP_PORT=$(ask_port "Application port (uvicorn)" "8080")

USE_NGINX=false
NGINX_PORT=""
NGINX_IP=""
if command -v nginx &>/dev/null; then
    echo ""
    if confirm "Set up nginx reverse proxy?"; then
        USE_NGINX=true
        NGINX_PORT=$(ask_port "Nginx external port" "8443")
        echo ""
        ask_ip "IP address nginx will listen on" NGINX_IP
    fi
else
    warn "nginx not found — skipping proxy setup"
fi

APP_HOST="127.0.0.1"

echo ""
info "Install dir: $INSTALL_DIR"
info "App:         http://$APP_HOST:$APP_PORT  (internal)"
$USE_NGINX && info "Nginx:       http://$NGINX_IP:$NGINX_PORT  -> http://$APP_HOST:$APP_PORT" || true

# ---------------------------------------------------------------------------
# Step 1: system user and dedicated config group
# ---------------------------------------------------------------------------
header "Step 1/7: system user and config group"

if id "$APP_USER" &>/dev/null; then
    warn "User $APP_USER already exists — skipping"
else
    useradd --system --no-create-home --shell /usr/sbin/nologin "$APP_USER"
    info "Created user $APP_USER"
fi

# Create dedicated group for tac_plus-ng config access (no root group needed)
if getent group "$CFG_GROUP" &>/dev/null; then
    warn "Group $CFG_GROUP already exists — skipping"
else
    groupadd --system "$CFG_GROUP"
    info "Created group $CFG_GROUP"
fi

usermod -aG "$CFG_GROUP" "$APP_USER"
info "Added $APP_USER to group $CFG_GROUP"

# Set config dir/file group ownership and permissions
if [[ -d "$TACACS_CFG_DIR" ]]; then
    chgrp "$CFG_GROUP" "$TACACS_CFG_DIR"
    chmod 750 "$TACACS_CFG_DIR"
    info "Config dir:  $TACACS_CFG_DIR  (root:$CFG_GROUP 750)"
fi
if [[ -f "$TACACS_CONFIG" ]]; then
    chgrp "$CFG_GROUP" "$TACACS_CONFIG"
    chmod 660 "$TACACS_CONFIG"
    info "Config file: $TACACS_CONFIG  (root:$CFG_GROUP 660)"
fi

# ---------------------------------------------------------------------------
# Step 2: copy app files to INSTALL_DIR
# ---------------------------------------------------------------------------
header "Step 2/7: install app to $INSTALL_DIR"

mkdir -p "$INSTALL_DIR"

# rsync app files; skip venv, secrets, and runtime data
rsync -a --delete \
    --exclude='.venv/' \
    --exclude='.env' \
    --exclude='users.json' \
    --exclude='*.pyc' \
    --exclude='__pycache__/' \
    "$SOURCE_DIR/" "$INSTALL_DIR/"

chown -R "$APP_USER:$APP_USER" "$INSTALL_DIR"
chmod 750 "$INSTALL_DIR"
info "Files copied to $INSTALL_DIR"

# ---------------------------------------------------------------------------
# Step 3: Python venv inside INSTALL_DIR
# ---------------------------------------------------------------------------
header "Step 3/7: Python venv"
$PYTHON --version >/dev/null 2>&1 || die "Python3 not found. Install: apt install python3"

if [[ ! -d "$VENV_DIR" ]]; then
    $PYTHON -m venv "$VENV_DIR"
    chown -R "$APP_USER:$APP_USER" "$VENV_DIR"
    info "Created venv: $VENV_DIR"
else
    warn "venv already exists — skipping creation"
fi

"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"
chown -R "$APP_USER:$APP_USER" "$VENV_DIR"
info "Dependencies installed"

UVICORN="$VENV_DIR/bin/uvicorn"
PYTHON_VENV="$VENV_DIR/bin/python"

# ---------------------------------------------------------------------------
# Step 4: .env
# ---------------------------------------------------------------------------
header "Step 4/7: environment (.env)"

ENV_FILE="$INSTALL_DIR/.env"

if [[ -f "$ENV_FILE" ]]; then
    warn ".env already exists — not overwriting"
else
    SESSION_SECRET=$($PYTHON_VENV -c "import secrets; print(secrets.token_hex(32))")

    cat > "$ENV_FILE" <<EOF
SESSION_SECRET=$SESSION_SECRET
TACACS_CONFIG=$TACACS_CONFIG
TACACS_BIN=$TACACS_BIN
TACACS_LOG_DIR=$TACACS_LOG_DIR
BACKUP_DIR=$BACKUP_DIR
USERS_FILE=$INSTALL_DIR/users.json
TACACS_SERVICE=$TACACS_SERVICE
EOF
    chown "$APP_USER:$APP_USER" "$ENV_FILE"
    chmod 640 "$ENV_FILE"
    info ".env created at $ENV_FILE"
fi

# ---------------------------------------------------------------------------
# Step 5: backup directory
# ---------------------------------------------------------------------------
header "Step 5/7: directories"

mkdir -p "$BACKUP_DIR"
chown "$APP_USER:$APP_USER" "$BACKUP_DIR"
info "Backup directory: $BACKUP_DIR"

# ---------------------------------------------------------------------------
# Step 6: sudoers
# ---------------------------------------------------------------------------
header "Step 6/7: sudoers"

SYSTEMCTL=$(command -v systemctl)

cat > "/etc/sudoers.d/$SERVICE_NAME" <<EOF
# tacacs-web: sudo permissions for tac_plus-ng daemon control
# Generated by install.sh

Cmnd_Alias TACACS_WEB = \\
    $TACACS_BIN -P *, \\
    $SYSTEMCTL start $TACACS_SERVICE, \\
    $SYSTEMCTL stop $TACACS_SERVICE, \\
    $SYSTEMCTL restart $TACACS_SERVICE, \\
    $SYSTEMCTL reload $TACACS_SERVICE, \\
    $SYSTEMCTL is-active $TACACS_SERVICE, \\
    $SYSTEMCTL status $TACACS_SERVICE *

$APP_USER ALL=(root) NOPASSWD: TACACS_WEB
EOF

chmod 440 "/etc/sudoers.d/$SERVICE_NAME"

if visudo -c -f "/etc/sudoers.d/$SERVICE_NAME" &>/dev/null; then
    info "Sudoers written and validated: /etc/sudoers.d/$SERVICE_NAME"
else
    error "Sudoers syntax error — check the file manually."
    rm -f "/etc/sudoers.d/$SERVICE_NAME"
    die "Installation aborted"
fi

# ---------------------------------------------------------------------------
# Step 6b: systemd unit
# ---------------------------------------------------------------------------
header "Step 6b/7: systemd unit"

cat > "/etc/systemd/system/$SERVICE_NAME.service" <<EOF
[Unit]
Description=TACACS+ Web UI
After=network.target ${TACACS_SERVICE}.service
Wants=${TACACS_SERVICE}.service

[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$UVICORN web:app --host $APP_HOST --port $APP_PORT
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=$SERVICE_NAME

PrivateTmp=yes

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
info "Systemd unit installed: /etc/systemd/system/$SERVICE_NAME.service"

# ---------------------------------------------------------------------------
# Step 6c: nginx
# ---------------------------------------------------------------------------
if $USE_NGINX; then
    header "Step 6c: nginx"

    NGINX_CONF="/etc/nginx/sites-available/$SERVICE_NAME"
    NGINX_LINK="/etc/nginx/sites-enabled/$SERVICE_NAME"

    cat > "$NGINX_CONF" <<EOF
server {
    listen $NGINX_IP:$NGINX_PORT;
    server_name _;

    proxy_set_header X-Forwarded-For   \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto \$scheme;
    proxy_set_header Host              \$http_host;

    location / {
        proxy_pass http://$APP_HOST:$APP_PORT;

        proxy_http_version 1.1;
        proxy_set_header Connection "";

        proxy_connect_timeout 10s;
        proxy_read_timeout    60s;
        proxy_send_timeout    60s;

        proxy_no_cache 1;
        proxy_cache_bypass 1;
        add_header Cache-Control "no-store, no-cache, must-revalidate" always;
        add_header Pragma "no-cache" always;
    }
}
EOF

    if [[ ! -L "$NGINX_LINK" ]]; then
        ln -s "$NGINX_CONF" "$NGINX_LINK"
        info "Symlink created: $NGINX_LINK"
    else
        warn "Symlink $NGINX_LINK already exists — config overwritten"
    fi

    if nginx -t 2>/dev/null; then
        systemctl reload nginx
        info "Nginx reloaded. Config: $NGINX_CONF"
    else
        error "Nginx config error — fix manually: $NGINX_CONF"
        error "Check with: nginx -t"
    fi
fi

# ---------------------------------------------------------------------------
# Step 7: first admin user
# ---------------------------------------------------------------------------
header "Step 7/7: first user"

USERS_FILE="$INSTALL_DIR/users.json"

if [[ -f "$USERS_FILE" ]] && [[ $(wc -c < "$USERS_FILE") -gt 5 ]]; then
    warn "users.json already exists — skipping user creation"
else
    echo ""
    echo "  Create the first admin user. (Password min 8 characters)"
    echo ""
    read -rp "  Username [admin]: " ADMIN_USER
    ADMIN_USER="${ADMIN_USER:-admin}"

    # Run as APP_USER — works because INSTALL_DIR is owned by APP_USER
    sudo -u "$APP_USER" "$PYTHON_VENV" "$INSTALL_DIR/manage_users.py" add "$ADMIN_USER" admin || \
        die "Failed to create user"

    chown "$APP_USER:$APP_USER" "$USERS_FILE" 2>/dev/null || true
fi

# ---------------------------------------------------------------------------
# Start service
# ---------------------------------------------------------------------------
echo ""
if confirm "Start $SERVICE_NAME now?"; then
    systemctl enable "$SERVICE_NAME"
    systemctl start  "$SERVICE_NAME"
    sleep 1
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        info "Service is running"
    else
        error "Service failed to start. Check: journalctl -u $SERVICE_NAME -n 30"
    fi
else
    info "To start manually:"
    echo "  sudo systemctl enable --now $SERVICE_NAME"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN} tacacs-web installed successfully${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
if $USE_NGINX; then
    echo "  URL (nginx):  http://<host>:$NGINX_PORT"
    echo "  URL (direct): http://$APP_HOST:$APP_PORT"
else
    echo "  URL:          http://$APP_HOST:$APP_PORT"
fi
echo ""
echo "  Service:    systemctl status $SERVICE_NAME"
echo "  Logs:       journalctl -u $SERVICE_NAME -f"
echo "  App dir:    $INSTALL_DIR"
echo "  .env:       $INSTALL_DIR/.env"
echo "  Users:      $INSTALL_DIR/users.json"
$USE_NGINX && echo "  Nginx:      $NGINX_CONF  ($NGINX_IP:$NGINX_PORT)" || true
echo ""
echo "  User management:"
echo "    sudo -u $APP_USER $PYTHON_VENV $INSTALL_DIR/manage_users.py list"
echo ""
echo "  Config group (read/write access to tac_plus-ng config):"
echo "    group: $CFG_GROUP  ->  $TACACS_CONFIG  (660)"
echo ""
