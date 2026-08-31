#!/usr/bin/env bash
###############################################################################
#  Palworld Control Panel – Auto-Update einrichten
#
#  Richtet einen taeglichen systemd-Timer ein, der dein GitHub-Repo pullt und
#  den Panel-Code neu deployt (nur das Panel wird neu gestartet, NICHT der
#  Spielserver). Nutzerdaten (panel.json, users.json) bleiben unangetastet.
#
#  Als root im Container ausfuehren:
#      bash setup-panel-autoupdate.sh
#  Optional andere Werte:
#      PANEL_REPO_URL=https://github.com/DEINNAME/palworld-control-panel.git \
#      UPDATE_TIME=04:30 bash setup-panel-autoupdate.sh
#  Sofort einmal laufen lassen: mit  --run-now
###############################################################################
set -euo pipefail

REPO_URL="${PANEL_REPO_URL:-https://github.com/Schattenwelt/palworld-control-panel.git}"
BRANCH="${PANEL_REPO_BRANCH:-main}"
UPDATE_TIME="${UPDATE_TIME:-04:30}"
REPO_DIR="/opt/palworld-panel-src"
PANEL_DIR="/opt/palworld-panel"
PAL_USER="palworld"
BIN="/usr/local/bin/palworld-panel-update"

msg()  { printf '\n\033[1;36m==>\033[0m \033[1m%s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m[ok]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[x] %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "Bitte als root ausführen."
[ -d "$PANEL_DIR" ] || die "$PANEL_DIR nicht gefunden – ist das Panel installiert?"
[[ "$UPDATE_TIME" =~ ^[0-2][0-9]:[0-5][0-9]$ ]] || die "UPDATE_TIME muss HH:MM sein (z. B. 04:30)."

msg "Stelle sicher, dass git vorhanden ist ..."
command -v git >/dev/null || { apt-get update -qq && apt-get install -y -qq git; }
ok "git vorhanden."

msg "Hole das Repository nach $REPO_DIR ..."
if [ -d "$REPO_DIR/.git" ]; then
    git -C "$REPO_DIR" remote set-url origin "$REPO_URL"
    ok "Repo bereits vorhanden – Remote aktualisiert."
else
    rm -rf "$REPO_DIR"
    git clone --depth 1 -b "$BRANCH" "$REPO_URL" "$REPO_DIR" \
        || die "git clone fehlgeschlagen. Repo öffentlich? URL korrekt: $REPO_URL"
    ok "Repo geklont."
fi
[ -d "$REPO_DIR/src" ] || die "Im Repo fehlt src/ – falsche URL/Branch?"

msg "Schreibe Update-Programm nach $BIN ..."
cat > "$BIN" <<EOF
#!/usr/bin/env bash
# Von palworld-panel-update.timer aufgerufen: Repo pullen + Panel deployen.
set -euo pipefail
REPO_DIR="$REPO_DIR"
PANEL_DIR="$PANEL_DIR"
PAL_USER="$PAL_USER"
BRANCH="$BRANCH"
REPO_URL="$REPO_URL"

if [ ! -d "\$REPO_DIR/.git" ]; then
    rm -rf "\$REPO_DIR"
    git clone --depth 1 -b "\$BRANCH" "\$REPO_URL" "\$REPO_DIR"
fi
before="\$(git -C "\$REPO_DIR" rev-parse HEAD 2>/dev/null || echo none)"
git -C "\$REPO_DIR" fetch --depth 1 origin "\$BRANCH"
git -C "\$REPO_DIR" reset --hard "origin/\$BRANCH"
after="\$(git -C "\$REPO_DIR" rev-parse HEAD)"

if [ "\$before" = "\$after" ] && [ -f "\$PANEL_DIR/app.py" ]; then
    echo "Panel bereits aktuell (\$after)."
    exit 0
fi

cp -r "\$REPO_DIR/src/app.py" "\$REPO_DIR/src/rcon.py" "\$REPO_DIR/src/i18n.py" \\
      "\$REPO_DIR/src/repair_ini.py" "\$REPO_DIR/src/templates" "\$REPO_DIR/src/static" "\$PANEL_DIR/"
install -m 0755 "\$REPO_DIR/src/palworld-update.sh" /home/palworld/palworld-update.sh
chown -R "\$PAL_USER":"\$PAL_USER" "\$PANEL_DIR" /home/palworld/palworld-update.sh
chmod 600 "\$PANEL_DIR/panel.json" "\$PANEL_DIR/users.json" 2>/dev/null || true
systemctl restart palworld-panel.service
echo "Panel aktualisiert: \$before -> \$after"
EOF
chmod +x "$BIN"
ok "Update-Programm geschrieben."

msg "Richte systemd-Service + täglichen Timer ein ($UPDATE_TIME Uhr) ..."
cat > /etc/systemd/system/palworld-panel-update.service <<EOF
[Unit]
Description=Palworld Panel Auto-Update (git pull + deploy)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=$BIN
EOF

cat > /etc/systemd/system/palworld-panel-update.timer <<EOF
[Unit]
Description=Taeglicher Palworld-Panel-Auto-Update

[Timer]
OnCalendar=*-*-* ${UPDATE_TIME}:00
RandomizedDelaySec=1800
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now palworld-panel-update.timer >/dev/null 2>&1 || systemctl enable palworld-panel-update.timer
ok "Timer aktiv."

if [ "${1:-}" = "--run-now" ]; then
    msg "Führe das Update jetzt einmal aus ..."
    systemctl start palworld-panel-update.service
    sleep 1
    journalctl -u palworld-panel-update.service -n 8 --no-pager -o cat | sed 's/^/    /'
fi

echo
ok "Auto-Update eingerichtet."
echo "    Nächste Läufe:   systemctl list-timers palworld-panel-update.timer"
echo "    Sofort updaten:  systemctl start palworld-panel-update.service"
echo "    Log ansehen:     journalctl -u palworld-panel-update.service"
echo "    Abschalten:      systemctl disable --now palworld-panel-update.timer"
