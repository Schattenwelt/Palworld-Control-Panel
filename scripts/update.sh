#!/usr/bin/env bash
# Aktualisiert nur den Panel-Code (app.py, rcon.py, i18n.py, Templates, CSS) aus dem
# ausgecheckten Repo und startet das Panel neu. Nutzerdaten bleiben unangetastet.
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PANEL_DIR="/opt/palworld-panel"; PAL_USER="palworld"
[ "$(id -u)" -eq 0 ] || { echo "Bitte als root ausführen." >&2; exit 1; }
[ -d "$PANEL_DIR" ] || { echo "$PANEL_DIR fehlt – zuerst install.sh ausführen." >&2; exit 1; }
cp -r "$REPO_DIR/src/app.py" "$REPO_DIR/src/rcon.py" "$REPO_DIR/src/i18n.py" \
      "$REPO_DIR/src/repair_ini.py" "$REPO_DIR/src/templates" "$REPO_DIR/src/static" "$PANEL_DIR/"
install -m 0755 "$REPO_DIR/src/palworld-update.sh" /home/palworld/palworld-update.sh
chown -R "$PAL_USER":"$PAL_USER" "$PANEL_DIR" /home/palworld/palworld-update.sh
chmod 600 "$PANEL_DIR/panel.json" "$PANEL_DIR/users.json" 2>/dev/null || true
systemctl restart palworld-panel.service
echo "Panel aktualisiert und neu gestartet."
