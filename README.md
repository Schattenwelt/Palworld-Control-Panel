# Palworld Control Panel

A lightweight, self-hosted web panel to install, configure, and control a
**Palworld dedicated server** running inside a Proxmox LXC container — with a
login-protected UI, live status, one-click updates, an in-browser config editor,
and RCON (player list, save, graceful shutdown, broadcasts).

The interface is available in **German and English** (switchable in the top bar).

> Unofficial community project. Not affiliated with or endorsed by Pocketpair.
> "Palworld" is a trademark of its respective owner.

## Features

- Server lifecycle: **start / restart / stop** and **update** (SteamCMD) from the browser
- **Reboot-aware**: the server only comes back up after a reboot if it was running before
  (start = autostart on, stop = off); the LXC itself starts via Proxmox `onboot`
- **Config editor** for `PalWorldSettings.ini` — structured fields *and* a raw editor,
  robust against Palworld's single-line/reset quirks
- **RCON, server-internal**: enabled automatically (localhost only, no exposed port) —
  live player list with per-player **kick / ban**, save, "save & stop", and broadcasts
- **Multiple user accounts**: add / reset / delete users in the UI; each user can change
  their own password. All accounts are equal.
- Runs as a non-root system user with a narrow `sudo` allow-list

## Requirements

- A **Proxmox LXC container** (Ubuntu 24.04, unprivileged is fine), **16 GB RAM recommended**
  (8 GB minimum — Palworld is memory-hungry)
- Root access inside the container

## Installation

On the Proxmox host, create the container (example):

```bash
pct create 200 local:vztmpl/ubuntu-24.04-standard_24.04-2_amd64.tar.zst \
  --hostname palworld --cores 4 --memory 16384 --swap 4096 \
  --rootfs local-lvm:32 --net0 name=eth0,bridge=vmbr0,ip=dhcp \
  --unprivileged 1 --features nesting=1 --onboot 1
pct start 200 && pct enter 200
```

Inside the container:

```bash
git clone https://github.com/Schattenwelt/palworld-control-panel.git
cd palworld-control-panel
bash install.sh
```

The installer asks for a panel username and password (or pass them non-interactively
via `PANEL_USER=... PANEL_PASS=... bash install.sh`). The panel defaults to **port 80**;
override with `PANEL_PORT=8080 bash install.sh`.

Open `http://<container-ip>`, review the settings under **Configuration**, then click
**Start**. The game port **8211/UDP** must be reachable through your firewall.

## Updating

Pull the latest code and refresh only the panel (your accounts and config are untouched):

```bash
git pull
sudo bash scripts/update.sh
```

## Repairing config / RCON

If Palworld reset your `PalWorldSettings.ini` (RCON off, or a broken
`CrossplayPlatforms` value), run:

```bash
sudo bash scripts/repair.sh
```

It stops the server, restores a valid single-line config with RCON enabled, restarts,
and checks the RCON port.

## Project layout

```
install.sh            Full installer (run once in a fresh container)
scripts/update.sh     Refresh panel code from the repo, restart the panel
scripts/repair.sh     Repair PalWorldSettings.ini + ensure RCON
src/                  Panel source (Flask app, RCON client, i18n, templates, CSS)
```

## Security notes

Passwords are hashed (Werkzeug); all state-changing actions are CSRF-protected. The
panel serves plain HTTP — for access beyond your LAN, put it behind a reverse proxy
with TLS. The `panel.json` and `users.json` files hold hashed credentials and are
created at install time (git-ignored).

## License

MIT — see [LICENSE](LICENSE).
