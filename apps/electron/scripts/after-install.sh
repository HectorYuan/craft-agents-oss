#!/bin/bash
set -e

# ============================================================
# postinst — merged from electron-builder default + AppStream
# ============================================================

if type update-alternatives 2>/dev/null >&1; then
    # Remove previous link if it doesn't use update-alternatives
    if [ -L '/usr/bin/zenskill' -a -e '/usr/bin/zenskill' -a "`readlink '/usr/bin/zenskill'`" != '/etc/alternatives/zenskill' ]; then
        rm -f '/usr/bin/zenskill'
    fi
    update-alternatives --install '/usr/bin/zenskill' 'zenskill' '/opt/ZenSkill/zenskill' 100 || ln -sf '/opt/ZenSkill/zenskill' '/usr/bin/zenskill'
else
    ln -sf '/opt/ZenSkill/zenskill' '/usr/bin/zenskill'
fi

# Check if user namespaces are supported by the kernel
if ! { [[ -L /proc/self/ns/user ]] && unshare --user true; }; then
    chmod 4755 '/opt/ZenSkill/chrome-sandbox' || true
else
    chmod 0755 '/opt/ZenSkill/chrome-sandbox' || true
fi

if hash update-mime-database 2>/dev/null; then
    update-mime-database /usr/share/mime || true
fi

# Install AppStream metadata for GNOME Shell / Ubuntu App Grid discovery
APPDATA_SRC="/opt/ZenSkill/resources/app/resources/com.zenskill.desktop.appdata.xml"
APPDATA_DST="/usr/share/metainfo/com.zenskill.desktop.appdata.xml"
if [ -f "$APPDATA_SRC" ]; then
    cp -f "$APPDATA_SRC" "$APPDATA_DST" 2>/dev/null || true
fi

if hash update-desktop-database 2>/dev/null; then
    update-desktop-database /usr/share/applications || true
fi

# Fix .desktop file permissions — electron-builder packs files as 664 (group-writable).
DESKTOP_FILE="/usr/share/applications/zenskill.desktop"
if [ -f "$DESKTOP_FILE" ]; then
    chmod 644 "$DESKTOP_FILE" 2>/dev/null || true
fi

# Per-user .desktop fallback — the XDG-standard per-user install location.
# Empirically required: some GNOME 50 / GLib configurations refuse to enumerate
# certain dpkg-installed files in /usr/share/applications (root cause unclear:
# same content+name enumerates fine from ~/.local/share/applications), so we
# install a user-level copy for the invoking user. User-dir installs are also
# picked up by the running GNOME Shell live via GFileMonitor (no re-login).
if [ -n "$SUDO_USER" ] && [ "$SUDO_USER" != "root" ]; then
    USER_APP_DIR="$(getent passwd "$SUDO_USER" | cut -d: -f6)/.local/share/applications"
    if [ -d "$(dirname "$USER_APP_DIR")" ] || mkdir -p "$USER_APP_DIR" 2>/dev/null; then
        if [ -f "$DESKTOP_FILE" ]; then
            install -m 644 -o "$(id -u "$SUDO_USER")" -g "$(id -g "$SUDO_USER")" \
                "$DESKTOP_FILE" "$USER_APP_DIR/zenskill.desktop" 2>/dev/null || true
        fi
    fi
fi

# Ensure zenskill.desktop appears in GNOME Shell app grid.
# gsettings reset restores GNOME defaults (not auto-scan), so we must
# append our .desktop entry to the existing layout.
if hash gsettings 2>/dev/null && hash python3 2>/dev/null; then
    python3 -c "
import subprocess, json, re

# Read current layout (GVDB serialized format)
raw = subprocess.check_output(
    ['gsettings', 'get', 'org.gnome.shell', 'app-picker-layout'],
    text=True, stderr=subprocess.DEVNULL
).strip()

# Already present?
if 'zenskill.desktop' in raw:
    exit(0)

# Parse existing entries: {'name.desktop': {'position': N}}
entries = re.findall(r\"'([^']+)': <\{'position': <(\d+)>\}>\", raw)
pos = max((int(p) for _, p in entries), default=-1) + 1

# Insert zenskill before the closing bracket
new_entry = \"'zenskill.desktop': <{'position': <%d>}>\" % pos
new_raw = raw.rstrip(']') + ', ' + new_entry + ']' if raw.startswith('[') else raw

# Write back via dconf (gsettings set rejects GVDB syntax)
subprocess.run(['dconf', 'write', '/org/gnome/shell/app-picker-layout', new_raw],
               check=True, stderr=subprocess.DEVNULL)
" 2>/dev/null || true
fi

# Show desktop notification on install completion
# dpkg postinst runs as root without the user's D-Bus session, so we must
# detect the logged-in desktop user and forward the notification to their session.
if hash notify-send 2>/dev/null; then
    DESKTOP_USER=""
    # Try the SUDO_USER (the user who ran sudo dpkg -i)
    if [ -n "$SUDO_USER" ]; then
        DESKTOP_USER="$SUDO_USER"
    fi
    # Fallback: find any logged-in user with a graphical session
    if [ -z "$DESKTOP_USER" ] && hash loginctl 2>/dev/null; then
        DESKTOP_USER=$(loginctl list-sessions --no-legend 2>/dev/null | awk '$4 == "user" {print $3; exit}')
    fi
    if [ -n "$DESKTOP_USER" ]; then
        DESKTOP_UID=$(id -u "$DESKTOP_USER" 2>/dev/null)
        if [ -n "$DESKTOP_UID" ]; then
            DBUS_ADDR="unix:path=/run/user/${DESKTOP_UID}/bus"
            sudo -u "$DESKTOP_USER" env DISPLAY=:0 DBUS_SESSION_BUS_ADDRESS="$DBUS_ADDR" \
                notify-send -i zenskill "ZenSkill" "安装完成！可以从应用菜单启动 ZenSkill。" 2>/dev/null || true
        fi
    fi
fi

# Install apparmor profile (Ubuntu 24+)
if apparmor_status --enabled > /dev/null 2>&1; then
  APPARMOR_PROFILE_SOURCE='/opt/ZenSkill/resources/apparmor-profile'
  APPARMOR_PROFILE_TARGET='/etc/apparmor.d/zenskill'
  if apparmor_parser --skip-kernel-load --debug "$APPARMOR_PROFILE_SOURCE" > /dev/null 2>&1; then
    cp -f "$APPARMOR_PROFILE_SOURCE" "$APPARMOR_PROFILE_TARGET"
    if ! { [ -x '/usr/bin/ischroot' ] && /usr/bin/ischroot; } && hash apparmor_parser 2>/dev/null; then
      apparmor_parser --replace --write-cache --skip-read-cache "$APPARMOR_PROFILE_TARGET"
    fi
  else
    echo "Skipping the installation of the AppArmor profile as this version of AppArmor does not seem to support the bundled profile"
  fi
fi
