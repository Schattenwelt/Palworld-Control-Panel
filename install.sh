#!/usr/bin/env bash
###############################################################################
#  Palworld Control Panel – Installer
#
#  Installiert in einem Ubuntu-LXC-Container:
#    * Palworld-Dedicated-Server (SteamCMD, AppID 2394010) als systemd-Service
#    * Ein login-geschütztes Web-Panel (Start/Stop/Neustart, Update, Config)
#    * Update-Service + automatische Save-Backups
#
#  Ausführen IM Container als root:   bash install-palworld-panel.sh
###############################################################################
set -euo pipefail

# ------------------------- Einstellungen (anpassbar) ------------------------
PAL_USER="palworld"
PAL_HOME="/home/palworld"
INSTALL_DIR="/home/palworld/palserver"
PANEL_DIR="/opt/palworld-panel"
PANEL_PORT="${PANEL_PORT:-80}"         # Port des Web-Panels
APPID="2394010"
STEAMCMD="/usr/games/steamcmd"

# Panel-Zugangsdaten: aus Umgebungsvariablen oder interaktiv abfragen
PANEL_USER="${PANEL_USER:-}"
PANEL_PASS="${PANEL_PASS:-}"

msg()  { printf '\n\033[1;36m==>\033[0m \033[1m%s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[x] %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "Bitte als root ausführen (im LXC-Container)."
command -v apt-get >/dev/null || die "Dieser Installer ist für Debian/Ubuntu-LXC gedacht."

# RAM-Hinweis (Palworld braucht ordentlich Speicher)
MEM_GB=$(( $(grep MemTotal /proc/meminfo | awk '{print $2}') / 1024 / 1024 ))
if [ "$MEM_GB" -lt 8 ]; then
    warn "Nur ${MEM_GB} GB RAM erkannt. Palworld empfiehlt 16 GB (min. 8 GB)."
fi

# Zugangsdaten abfragen, falls nicht gesetzt
if [ -z "$PANEL_USER" ]; then
    read -rp "Panel-Benutzername [admin]: " PANEL_USER
    PANEL_USER="${PANEL_USER:-admin}"
fi
if [ -z "$PANEL_PASS" ]; then
    while :; do
        read -rsp "Panel-Passwort: " PANEL_PASS; echo
        [ -n "$PANEL_PASS" ] || { warn "Passwort darf nicht leer sein."; continue; }
        read -rsp "Passwort wiederholen: " P2; echo
        [ "$PANEL_PASS" = "$P2" ] && break || warn "Passwörter stimmen nicht überein."
    done
fi

# ------------------------- Pakete installieren ------------------------------
msg "Aktualisiere Paketquellen und installiere Abhängigkeiten ..."
export DEBIAN_FRONTEND=noninteractive
dpkg --add-architecture i386
apt-get update -y
apt-get install -y --no-install-recommends software-properties-common ca-certificates
add-apt-repository -y multiverse
add-apt-repository -y universe
apt-get update -y

# SteamCMD-Lizenz vorab akzeptieren (sonst interaktiver Dialog)
echo steam steam/question select "I AGREE" | debconf-set-selections
echo steam steam/license note '' | debconf-set-selections

apt-get install -y --no-install-recommends \
    steamcmd lib32gcc-s1 \
    python3 python3-venv python3-pip \
    sudo curl tar xz-utils locales procps

# Locale für SteamCMD/Server
locale-gen en_US.UTF-8 >/dev/null 2>&1 || true

# ------------------------- Benutzer anlegen ---------------------------------
msg "Lege Benutzer '$PAL_USER' an ..."
if ! id "$PAL_USER" >/dev/null 2>&1; then
    useradd -m -d "$PAL_HOME" -s /bin/bash "$PAL_USER"
fi
# Logs lesen dürfen
usermod -aG systemd-journal "$PAL_USER" || true

# ------------------------- Palworld-Server installieren ---------------------
msg "Installiere Palworld-Server via SteamCMD (kann einige Minuten dauern) ..."
sudo -u "$PAL_USER" -H bash -c "\
    '$STEAMCMD' +force_install_dir '$INSTALL_DIR' \
    +login anonymous +app_update '$APPID' validate +quit"

# steamclient.so für das SDK verlinken
msg "Richte steamclient.so ein ..."
sudo -u "$PAL_USER" -H bash -c "\
    SC=\$(find \"\$HOME/.steam\" \"\$HOME/Steam\" '$INSTALL_DIR' -name steamclient.so 2>/dev/null | head -n1 || true); \
    if [ -n \"\$SC\" ]; then mkdir -p \"\$HOME/.steam/sdk64\"; ln -sf \"\$SC\" \"\$HOME/.steam/sdk64/steamclient.so\"; fi"

# Standard-Config als Basis bereitstellen und RCON server-intern aktivieren
msg "Bereite PalWorldSettings.ini vor (RCON intern aktiviert) ..."
RCON_PW="$(python3 -c 'import secrets;print(secrets.token_urlsafe(12))')"
sudo -u "$PAL_USER" -H INSTALL_DIR="$INSTALL_DIR" RCON_PW="$RCON_PW" python3 - <<'PY'
import os, shutil
d = os.environ["INSTALL_DIR"]
cfgdir = os.path.join(d, "Pal/Saved/Config/LinuxServer")
os.makedirs(cfgdir, exist_ok=True)
active = os.path.join(cfgdir, "PalWorldSettings.ini")
default = os.path.join(d, "DefaultPalWorldSettings.ini")
if not os.path.exists(active) and os.path.exists(default):
    shutil.copyfile(default, active)
if os.path.exists(active):
    raw = open(active, encoding="utf-8", errors="replace").read()
    raw = raw.replace("RCONEnabled=False", "RCONEnabled=True")
    if 'AdminPassword=""' in raw:
        raw = raw.replace('AdminPassword=""', 'AdminPassword="%s"' % os.environ["RCON_PW"], 1)
    open(active, "w", encoding="utf-8").write(raw)
PY

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
[ -d "$REPO_DIR/src" ] || die "src/ nicht gefunden – bitte install.sh aus dem Repo-Wurzelverzeichnis ausführen."

msg "Kopiere Panel-Dateien nach $PANEL_DIR ..."
mkdir -p "$PANEL_DIR"
cp -r "$REPO_DIR/src/app.py" "$REPO_DIR/src/rcon.py" "$REPO_DIR/src/i18n.py" \
      "$REPO_DIR/src/repair_ini.py" "$REPO_DIR/src/templates" "$REPO_DIR/src/static" "$PANEL_DIR/"
install -m 0755 "$REPO_DIR/src/palworld-update.sh" /home/palworld/palworld-update.sh
chown -R "$PAL_USER":"$PAL_USER" /home/palworld/palworld-update.sh


# ------------------------- systemd-Units ------------------------------------
msg "Erstelle systemd-Services ..."

cat > /etc/systemd/system/palworld.service <<'UNIT'
[Unit]
Description=Palworld Dedicated Server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=palworld
Group=palworld
WorkingDirectory=/home/palworld/palserver
ExecStart=/home/palworld/palserver/PalServer.sh -useperfthreads -NoAsyncLoadingThread -UseMultithreadForDS
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/systemd/system/palworld-update.service <<'UNIT'
[Unit]
Description=Palworld Server Update (SteamCMD)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=palworld
Group=palworld
WorkingDirectory=/home/palworld/palserver
Environment=INSTALL_DIR=/home/palworld/palserver
# Server vor dem Update stoppen (mit Root-Rechten, daher '+')
ExecStartPre=+/usr/bin/systemctl stop palworld.service
ExecStart=/home/palworld/palworld-update.sh
TimeoutStartSec=3600
UNIT

cat > /etc/systemd/system/palworld-panel.service <<'UNIT'
[Unit]
Description=Palworld Control Panel (Web UI)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=palworld
Group=palworld
# Erlaubt dem unprivilegierten Dienst, privilegierte Ports (<1024, z. B. 80) zu binden
AmbientCapabilities=CAP_NET_BIND_SERVICE
WorkingDirectory=/opt/palworld-panel
Environment=PANEL_CONFIG=/opt/palworld-panel/panel.json
ExecStart=/opt/palworld-panel/venv/bin/waitress-serve --listen=0.0.0.0:__PANEL_PORT__ app:app
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
sed -i "s/__PANEL_PORT__/${PANEL_PORT}/" /etc/systemd/system/palworld-panel.service

# ------------------------- Python-venv + Flask ------------------------------
msg "Richte Python-Umgebung für das Panel ein ..."
python3 -m venv "$PANEL_DIR/venv"
"$PANEL_DIR/venv/bin/pip" install --upgrade pip >/dev/null
"$PANEL_DIR/venv/bin/pip" install flask waitress >/dev/null

# ------------------------- panel.json + users.json --------------------------
msg "Erzeuge Panel-Konfiguration und ersten Benutzer ..."
PANEL_USER="$PANEL_USER" PANEL_PASS="$PANEL_PASS" \
"$PANEL_DIR/venv/bin/python" - <<'PY'
import json, os, secrets
from werkzeug.security import generate_password_hash

conf = {
    "secret_key": secrets.token_hex(32),
    "palserver_dir": "/home/palworld/palserver",
    "service": "palworld.service",
    "update_service": "palworld-update.service",
    "users_path": "/opt/palworld-panel/users.json",
    "rcon_host": "127.0.0.1",
}
with open("/opt/palworld-panel/panel.json", "w") as fh:
    json.dump(conf, fh, indent=2)

users = {"users": {
    os.environ["PANEL_USER"]: {"password_hash": generate_password_hash(os.environ["PANEL_PASS"])}
}}
with open("/opt/palworld-panel/users.json", "w") as fh:
    json.dump(users, fh, indent=2)
PY

# ------------------------- Rechte ------------------------------------------
chown -R "$PAL_USER":"$PAL_USER" "$PANEL_DIR"
chmod 600 "$PANEL_DIR/panel.json" "$PANEL_DIR/users.json"

# ------------------------- sudoers-Regel ------------------------------------
msg "Setze eingeschränkte sudo-Rechte für das Panel ..."
SUDO_FILE=/etc/sudoers.d/palworld-panel
cat > "$SUDO_FILE" <<'SUDO'
palworld ALL=(root) NOPASSWD: /usr/bin/systemctl enable --now palworld.service, /usr/bin/systemctl disable --now palworld.service, /usr/bin/systemctl enable palworld.service, /usr/bin/systemctl disable palworld.service, /usr/bin/systemctl restart palworld.service, /usr/bin/systemctl start palworld-update.service
SUDO
chmod 440 "$SUDO_FILE"
visudo -cf "$SUDO_FILE" >/dev/null || die "sudoers-Regel ungültig."

# ------------------------- Services aktivieren ------------------------------
msg "Aktiviere Services ..."
systemctl daemon-reload
# palworld.service wird bewusst NICHT fest aktiviert: ob es nach einem Reboot startet,
# richtet sich nach der letzten Aktion im Panel (Start = Autostart an, Stopp = aus).
systemctl disable palworld.service >/dev/null 2>&1 || true
systemctl enable --now palworld-panel.service

# ------------------------- Zusammenfassung ----------------------------------
IP=$(hostname -I 2>/dev/null | awk '{print $1}')
cat <<DONE

$(printf '\033[1;32m')============================================================$(printf '\033[0m')
  Fertig! Das Palworld Control Panel ist eingerichtet.

  Web-Panel:   http://${IP:-<container-ip>}:${PANEL_PORT}
  Login:       Benutzer '${PANEL_USER}' + dein gewähltes Passwort

  Server-Port: 8211/UDP  (in der Firewall/OPNsense freigeben)

  RCON:        server-intern aktiviert (nur localhost, kein Port nach außen).
               AdminPassword (= RCON-/In-Game-Admin-Passwort): ${RCON_PW}
               -> bitte notieren (nur gesetzt, falls vorher keins vorhanden war).

  Autostart:   Der Server startet nach einem Reboot nur, wenn er zuletzt lief.
               Start im Panel = Autostart an, Stopp = Autostart aus.
               Der LXC selbst startet über Proxmox (Container-Option onboot=1).

  Der Spielserver ist noch NICHT gestartet – erst im Panel unter
  "Konfiguration" die Einstellungen prüfen, dann "Starten" klicken.

  Nützliche Befehle:
    systemctl status palworld.service
    journalctl -u palworld.service -f
    systemctl status palworld-panel.service
$(printf '\033[1;32m')============================================================$(printf '\033[0m')
DONE
