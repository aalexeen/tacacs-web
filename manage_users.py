#!/usr/bin/env python3
"""CLI tool for managing tacacs-web users (bootstrap and maintenance).

Usage:
    python manage_users.py add   <username> <role>    # prompts for password
    python manage_users.py list
    python manage_users.py delete <username>
    python manage_users.py passwd <username>           # prompts for new password
    python manage_users.py enable  <username>
    python manage_users.py disable <username>

Roles: admin, operator, viewer
"""

from __future__ import annotations

import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import getpass
from auth import (
    ROLES,
    create_user,
    delete_user,
    get_user_by_username,
    list_users,
    set_user_enabled,
    update_user_password,
)


def cmd_add(args: list[str]) -> None:
    if len(args) != 2:
        print("Usage: manage_users.py add <username> <role>")
        sys.exit(1)
    username, role = args
    if role not in ROLES:
        print(f"Invalid role '{role}'. Choose from: {', '.join(ROLES)}")
        sys.exit(1)
    password = getpass.getpass(f"Password for '{username}': ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords do not match.")
        sys.exit(1)
    if len(password) < 8:
        print("Password must be at least 8 characters.")
        sys.exit(1)
    try:
        create_user(username, password, role)
        print(f"User '{username}' created with role '{role}'.")
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)


def cmd_list(_args: list[str]) -> None:
    users = list_users()
    if not users:
        print("No users found.")
        return
    fmt = "{:<20} {:<10} {}"
    print(fmt.format("USERNAME", "ROLE", "STATUS"))
    print("-" * 42)
    for u in users:
        status = "enabled" if u.get("enabled", True) else "disabled"
        print(fmt.format(u["username"], u["role"], status))


def cmd_delete(args: list[str]) -> None:
    if len(args) != 1:
        print("Usage: manage_users.py delete <username>")
        sys.exit(1)
    username = args[0]
    u = get_user_by_username(username)
    if u is None:
        print(f"User '{username}' not found.")
        sys.exit(1)
    confirm = input(f"Delete user '{username}'? [y/N] ")
    if confirm.lower() != "y":
        print("Aborted.")
        return
    delete_user(u["id"])
    print(f"User '{username}' deleted.")


def cmd_passwd(args: list[str]) -> None:
    if len(args) != 1:
        print("Usage: manage_users.py passwd <username>")
        sys.exit(1)
    username = args[0]
    u = get_user_by_username(username)
    if u is None:
        print(f"User '{username}' not found.")
        sys.exit(1)
    password = getpass.getpass(f"New password for '{username}': ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords do not match.")
        sys.exit(1)
    if len(password) < 8:
        print("Password must be at least 8 characters.")
        sys.exit(1)
    update_user_password(u["id"], password)
    print(f"Password updated for '{username}'.")


def cmd_enable(args: list[str]) -> None:
    _toggle(args, True)


def cmd_disable(args: list[str]) -> None:
    _toggle(args, False)


def _toggle(args: list[str], enabled: bool) -> None:
    action = "enable" if enabled else "disable"
    if len(args) != 1:
        print(f"Usage: manage_users.py {action} <username>")
        sys.exit(1)
    username = args[0]
    u = get_user_by_username(username)
    if u is None:
        print(f"User '{username}' not found.")
        sys.exit(1)
    set_user_enabled(u["id"], enabled)
    print(f"User '{username}' {'enabled' if enabled else 'disabled'}.")


COMMANDS = {
    "add": cmd_add,
    "list": cmd_list,
    "delete": cmd_delete,
    "passwd": cmd_passwd,
    "enable": cmd_enable,
    "disable": cmd_disable,
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(0 if len(sys.argv) < 2 else 1)
    COMMANDS[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    main()
