#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# ///
"""Install or update the status line for Claude Code.

Downloads statusline.py into <config>/statusline/ and points the statusLine
setting in <config>/settings.json at it. Running it again updates in place.

    uv run https://raw.githubusercontent.com/SteffenSimonsen/statusline/main/install.py
    curl -fsSL https://raw.githubusercontent.com/SteffenSimonsen/statusline/main/install.py | python3 -
"""
import argparse
import json
import os
import shutil
import sys
import urllib.request
from pathlib import Path

REPO = "SteffenSimonsen/statusline"
REFRESH_INTERVAL = 60


def config_dir():
    # Claude Code reads its settings from CLAUDE_CONFIG_DIR when it is set.
    path = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    return path.expanduser().resolve()


def download(ref):
    url = f"https://raw.githubusercontent.com/{REPO}/{ref}/statusline.py"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            source = response.read().decode("utf-8")
    except OSError as e:
        sys.exit(f"Could not download {url}: {e}")
    # Refuse to install an error page or a truncated file.
    compile(source, "statusline.py", "exec")
    return source


def python_command():
    """A Python 3 interpreter that stays on PATH.

    Not sys.executable: under `uv run` that is a throwaway environment.
    """
    for name, args in (("python3", ""), ("python", ""), ("py", " -3")):
        path = shutil.which(name)
        # The WindowsApps python stubs open the Microsoft Store instead of running.
        if path and "WindowsApps" not in path:
            return name + args
    sys.exit("No Python 3 interpreter found on PATH.")


def write_atomic(path, text):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def load_settings(path):
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text) if text.strip() else {}
    except json.JSONDecodeError as e:
        sys.exit(f"{path} is not valid JSON ({e}); fix it and run again.")


def update_settings(path, settings, command):
    status_line = {"type": "command", "command": command, "refreshInterval": REFRESH_INTERVAL}
    old = settings.get("statusLine")
    if old == status_line:
        return False
    if old:
        print(f"Replacing existing statusLine: {json.dumps(old)}")
    if path.exists():
        shutil.copy2(path, path.with_name(path.name + ".bak"))
    settings["statusLine"] = status_line
    write_atomic(path, json.dumps(settings, indent=2, ensure_ascii=False) + "\n")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--ref", default="main", help="branch, tag or commit to install (default: main)")
    args = parser.parse_args()

    config = config_dir()
    settings_path = config / "settings.json"
    script = config / "statusline" / "statusline.py"
    # Every check that can fail runs before anything is written.
    settings = load_settings(settings_path)
    command = f'{python_command()} -S -E "{script.as_posix()}"'
    source = download(args.ref)

    script.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(script, source)
    print(f"Installed {script} ({args.ref})")
    if update_settings(settings_path, settings, command):
        print(f"Updated {settings_path} (backup: {settings_path.name}.bak)")
    else:
        print(f"{settings_path} already up to date")
    print("The status line appears after your next message in Claude Code.")


if __name__ == "__main__":
    main()
