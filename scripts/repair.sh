#!/usr/bin/env bash
# Repariert eine beschädigte CrossplayPlatforms-Zeile und stellt RCON einzeilig sicher.
# Stoppt dafür kurz den Server, startet ihn danach wieder und prüft den RCON-Port.
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
INI="/home/palworld/palserver/Pal/Saved/Config/LinuxServer/PalWorldSettings.ini"
SERVICE="palworld.service"; RCON_PORT="25575"; WAIT_SECONDS=170
[ "$(id -u)" -eq 0 ] || { echo "Bitte als root ausführen." >&2; exit 1; }
[ -f "$INI" ] || { echo "INI nicht gefunden: $INI" >&2; exit 1; }
cp -a "$INI" "${INI}.bak.$(date +%s)" 2>/dev/null || true
systemctl stop "$SERVICE" || true; sleep 2
GEN_PW="$(INI="$INI" RCON_PORT="$RCON_PORT" python3 "$REPO_DIR/src/repair_ini.py")" \
    || { echo "Reparatur nicht sicher möglich – Datei unverändert." >&2; exit 2; }
chown palworld:palworld "$INI" 2>/dev/null || true
[ -n "$GEN_PW" ] && echo "Neues AdminPassword: $GEN_PW  (bitte notieren)"
systemctl start "$SERVICE"
echo "Warte auf RCON-Port $RCON_PORT (Server-Start dauert ~2 Min) ..."
waited=0
while [ "$waited" -lt "$WAIT_SECONDS" ]; do
  ss -tlnH 2>/dev/null | grep -q ":${RCON_PORT}\b" && { echo "RCON lauscht auf $RCON_PORT."; exit 0; }
  sleep 4; waited=$((waited+4))
done
echo "RCON nicht erreichbar – Logs prüfen: journalctl -u $SERVICE -n 30"
