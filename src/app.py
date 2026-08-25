#!/usr/bin/env python3
"""
Palworld Control Panel
Ein schlankes, login-geschütztes Web-Panel zum Starten, Stoppen, Aktualisieren
und Konfigurieren eines Palworld-Dedicated-Servers, der als systemd-Service läuft.
"""
import json
import os
import re
import secrets
import socket
import subprocess
import threading
import time
import urllib.request
from functools import wraps

from flask import (Flask, Response, redirect, render_template, request,
                   session, url_for, flash, jsonify)
from werkzeug.security import check_password_hash, generate_password_hash

from rcon import PalworldRCON, RCONError
from i18n import translate, LANGS, DEFAULT_LANG

# ---------------------------------------------------------------------------
# Konfiguration laden
# ---------------------------------------------------------------------------
CONFIG_PATH = os.environ.get("PANEL_CONFIG", "/opt/palworld-panel/panel.json")

with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
    CONF = json.load(fh)

PALSERVER_DIR = CONF["palserver_dir"]
SERVICE = CONF.get("service", "palworld.service")
UPDATE_SERVICE = CONF.get("update_service", "palworld-update.service")
INI_PATH = os.path.join(
    PALSERVER_DIR, "Pal", "Saved", "Config", "LinuxServer", "PalWorldSettings.ini"
)
DEFAULT_INI = os.path.join(PALSERVER_DIR, "DefaultPalWorldSettings.ini")

app = Flask(__name__)
app.secret_key = CONF["secret_key"]

# ---------------------------------------------------------------------------
# Benutzer-Store (users.json) – alle Konten sind gleichberechtigt
# ---------------------------------------------------------------------------
USERS_PATH = CONF.get("users_path",
                      os.path.join(os.path.dirname(CONFIG_PATH), "users.json"))
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{2,32}$")
MIN_PW = 6
_users_lock = threading.Lock()


def load_users():
    """Lädt alle Benutzer. Fällt auf einen alten Einzel-User in panel.json zurück."""
    if os.path.exists(USERS_PATH):
        with open(USERS_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh).get("users", {})
    if "username" in CONF and "password_hash" in CONF:  # Kompatibilität alt -> neu
        return {CONF["username"]: {"password_hash": CONF["password_hash"]}}
    return {}


def save_users(users):
    tmp = USERS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"users": users}, fh, indent=2)
    os.chmod(tmp, 0o600)
    os.replace(tmp, USERS_PATH)


def current_user():
    """Aktueller Benutzer als dict {name} – live gegen den Store geprüft, oder None."""
    name = session.get("user")
    if not name or name not in load_users():
        return None
    return {"name": name}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            session.clear()
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def csrf_token():
    tok = session.get("csrf")
    if not tok:
        tok = secrets.token_hex(16)
        session["csrf"] = tok
    return tok


def check_csrf():
    return request.form.get("csrf") and request.form.get("csrf") == session.get("csrf")


app.jinja_env.globals["csrf_token"] = csrf_token


def current_lang():
    lang = request.cookies.get("lang", DEFAULT_LANG)
    return lang if lang in LANGS else DEFAULT_LANG


def t(key, **kw):
    return translate(current_lang(), key, **kw)


app.jinja_env.globals["t"] = t
app.jinja_env.globals["current_lang"] = current_lang
app.jinja_env.globals["LANGS"] = LANGS


@app.context_processor
def inject_me():
    return {"me": current_user()}


@app.route("/lang/<code>")
def set_lang(code):
    resp = redirect(request.referrer or url_for("dashboard"))
    if code in LANGS:
        resp.set_cookie("lang", code, max_age=31536000, samesite="Lax")
    return resp


# ---------------------------------------------------------------------------
# systemd-Steuerung
# ---------------------------------------------------------------------------
def run(cmd, timeout=30):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except subprocess.TimeoutExpired:
        return 1, "Zeitüberschreitung beim Ausführen des Befehls."


def service_active(name):
    rc, out = run(["systemctl", "is-active", name])
    return out  # active / inactive / activating / failed ...


def service_enabled(name):
    rc, out = run(["systemctl", "is-enabled", name])
    return out  # enabled / disabled / static ...


def svc(*args):
    """systemctl mit Root-Rechten (nur die in der sudoers-Regel erlaubten Aufrufe)."""
    return run(["sudo", "-n", "systemctl", *args])


def recent_logs(name, lines=60):
    rc, out = run(["journalctl", "-u", name, "-n", str(lines),
                   "--no-pager", "-o", "short-iso"])
    return out if rc == 0 else "Keine Logs verfügbar (Rechte prüfen)."


# ---------------------------------------------------------------------------
# Server-Adresse (öffentliche IP ermitteln, gecacht)
# ---------------------------------------------------------------------------
def local_ipv4():
    """Lokale IPv4 des Containers (ohne echten Traffic zu erzeugen)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


_PUBIP_SERVICES = [
    "https://api.ipify.org",
    "https://checkip.amazonaws.com",
    "https://ifconfig.me/ip",
]
_PUBIP_TTL = 600        # gültige IP 10 Minuten cachen
_PUBIP_FAIL_TTL = 120   # Fehlschlag 2 Minuten cachen
_IPV4_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
_pubip_cache = {"ip": None, "ts": 0.0, "ok": False}


def detect_public_ip(timeout=2.0):
    """Öffentliche IPv4 ermitteln (gecacht). Gibt die IP oder None zurück.
    Auch Fehlschläge werden kurz gecacht, damit das Dashboard ohne Internet-Egress
    nicht bei jedem Aufruf blockiert."""
    now = time.time()
    ttl = _PUBIP_TTL if _pubip_cache["ok"] else _PUBIP_FAIL_TTL
    if now - _pubip_cache["ts"] < ttl:
        return _pubip_cache["ip"]
    ip = None
    for url in _PUBIP_SERVICES:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "palworld-panel"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                candidate = resp.read().decode("utf-8", "ignore").strip()
            if _IPV4_RE.match(candidate):
                ip = candidate
                break
        except Exception:
            continue
    _pubip_cache.update(ip=ip, ts=now, ok=bool(ip))
    return ip


def connect_info():
    """Liefert (adresse, port, art) für die Verbinden-Box.
    Priorität: PublicIP aus der INI (manuell) -> automatische öffentliche IP -> lokal."""
    opts = ini_lookup()
    port = (opts.get("PublicPort") or "8211").strip() or "8211"
    manual = (opts.get("PublicIP") or "").strip()
    if manual:
        return manual, port, "manual"
    pub = detect_public_ip()
    if pub:
        return pub, port, "auto"
    return local_ipv4(), port, "local"


# ---------------------------------------------------------------------------
# Ressourcen (CPU / RAM / Disk) – containerbewusst über lxcfs
# ---------------------------------------------------------------------------
_cpu_prev = {"idle": None, "total": None}


def read_cpu_percent():
    try:
        with open("/proc/stat") as f:
            parts = f.readline().split()
        vals = [int(x) for x in parts[1:]]
        idle = vals[3] + (vals[4] if len(vals) > 4 else 0)  # idle + iowait
        total = sum(vals)
        prev_idle, prev_total = _cpu_prev["idle"], _cpu_prev["total"]
        _cpu_prev["idle"], _cpu_prev["total"] = idle, total
        if prev_total is None:
            return None
        d_total = total - prev_total
        if d_total <= 0:
            return None
        return round(100.0 * (1.0 - (idle - prev_idle) / d_total), 1)
    except Exception:
        return None


def read_mem():
    try:
        info = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, _, v = line.partition(":")
                if v:
                    info[k.strip()] = int(v.strip().split()[0])  # kB
        total = info.get("MemTotal", 0)
        avail = info.get("MemAvailable", info.get("MemFree", 0))
        used = total - avail
        return {"used_gb": round(used / 1048576, 1),
                "total_gb": round(total / 1048576, 1),
                "pct": round(100.0 * used / total, 1) if total else None}
    except Exception:
        return None


def read_disk():
    try:
        base = PALSERVER_DIR if os.path.exists(PALSERVER_DIR) else "/"
        st = os.statvfs(base)
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        used = total - free
        return {"used_gb": round(used / 1073741824, 1),
                "total_gb": round(total / 1073741824, 1),
                "pct": round(100.0 * used / total, 1) if total else None}
    except Exception:
        return None


def resources():
    return {"cpu": read_cpu_percent(), "mem": read_mem(), "disk": read_disk()}


# ---------------------------------------------------------------------------
# Version / Update-Check
# ---------------------------------------------------------------------------
def installed_build():
    path = os.path.join(PALSERVER_DIR, "steamapps", "appmanifest_2394010.acf")
    try:
        m = re.search(r'"buildid"\s*"(\d+)"', _read_text(path))
        return m.group(1) if m else None
    except Exception:
        return None


def installed_version():
    rc, out = run(["journalctl", "-u", SERVICE, "--no-pager", "-o", "cat",
                   "-g", "Game version is", "-n", "5"])
    if rc == 0 and out:
        found = re.findall(r"Game version is (v[\d.]+)", out)
        if found:
            return found[-1]
    return None


_latest_cache = {"build": None, "ts": 0.0}


def latest_build(timeout=4.0):
    now = time.time()
    if _latest_cache["build"] and now - _latest_cache["ts"] < 1800:
        return _latest_cache["build"]
    try:
        req = urllib.request.Request("https://api.steamcmd.net/v1/info/2394010",
                                     headers={"User-Agent": "palworld-panel"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", "ignore"))
        b = (data.get("data", {}).get("2394010", {}).get("depots", {})
                 .get("branches", {}).get("public", {}).get("buildid"))
        if b:
            _latest_cache.update(build=str(b), ts=now)
    except Exception:
        pass
    return _latest_cache["build"]


# ---------------------------------------------------------------------------
# Bannliste (Pal/Saved/SaveGames/banlist.txt)
# ---------------------------------------------------------------------------
def banlist_path():
    return os.path.join(PALSERVER_DIR, "Pal", "Saved", "SaveGames", "banlist.txt")


def read_banlist():
    path = banlist_path()
    entries = []
    if os.path.exists(path):
        try:
            for line in _read_text(path).splitlines():
                s = line.strip()
                if s:
                    sid = s[6:] if s.lower().startswith("steam_") else s
                    entries.append({"raw": s, "steamid": sid})
        except Exception:
            pass
    return entries


def remove_from_banlist(sid):
    path = banlist_path()
    if not os.path.exists(path):
        return False
    try:
        lines = [l for l in _read_text(path).splitlines() if l.strip()]
        drop = {sid, "steam_" + sid, "steam_" + sid.lower()}
        keep = [l for l in lines if l.strip() not in drop]
        if len(keep) != len(lines):
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(keep) + ("\n" if keep else ""))
            return True
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# PalWorldSettings.ini parsen / schreiben
# ---------------------------------------------------------------------------
def _split_options(inner):
    """Teilt den OptionSettings-Inhalt an Kommas – respektiert Anführungszeichen UND
    Klammern (z. B. CrossplayPlatforms=(Steam,Xbox,PS5,Mac) bleibt ein Stück)."""
    parts, buf, in_q, depth = [], [], False, 0
    for ch in inner:
        if ch == '"':
            in_q = not in_q
            buf.append(ch)
        elif ch == "(" and not in_q:
            depth += 1
            buf.append(ch)
        elif ch == ")" and not in_q:
            depth -= 1
            buf.append(ch)
        elif ch == "," and not in_q and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return [p for p in parts if p.strip()]


def _read_text(path):
    """Liest eine Datei tolerant gegenüber BOM/UTF-16/Latin-1 (Unreal schreibt uneinheitlich)."""
    with open(path, "rb") as fh:
        data = fh.read()
    for enc in ("utf-8-sig", "utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return data.decode("utf-8", errors="replace")


def _extract_option_block(raw):
    """Findet OptionSettings=( … ) und liefert den Inhalt zwischen den Klammern.
    Klammern- und anführungszeichenbewusst, funktioniert auch über Zeilenumbrüche.
    Gibt None zurück, wenn OptionSettings gar nicht vorkommt."""
    marker = "OptionSettings=("
    idx = raw.find(marker)
    if idx == -1:
        return None
    i = idx + len(marker)
    depth, in_q = 1, False
    start = i
    while i < len(raw):
        ch = raw[i]
        if ch == '"':
            in_q = not in_q
        elif not in_q:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return raw[start:i]
        i += 1
    return raw[start:]  # unbalanciert – nimm den Rest


def _parse_block(block):
    result = []
    for part in _split_options(block):
        if "=" in part:
            k, v = part.split("=", 1)
            k = k.strip()
            v = v.strip()  # evtl. Zeilenumbrüche/Spaces aus Multi-Line-Dateien entfernen
            quoted = len(v) >= 2 and v.startswith('"') and v.endswith('"')
            paren = (not quoted) and len(v) >= 2 and v.startswith("(") and v.endswith(")")
            if quoted or paren:
                display = v[1:-1]   # äußere " " bzw. ( ) für die Anzeige entfernen
            else:
                display = v
            result.append((k, display, quoted, paren))
    return result


def read_settings():
    """Liest die aktive INI und liefert (settings, raw, aktiver_pfad, using_default).
    Fällt für die Feldliste auf DefaultPalWorldSettings.ini zurück, wenn die aktive
    Datei (noch) keine brauchbaren OptionSettings enthält."""
    active = INI_PATH if os.path.exists(INI_PATH) else DEFAULT_INI
    raw = _read_text(active) if os.path.exists(active) else ""
    block = _extract_option_block(raw)
    settings = _parse_block(block) if block is not None else []
    using_default = (active == DEFAULT_INI)

    if not settings and active == INI_PATH and os.path.exists(DEFAULT_INI):
        dblock = _extract_option_block(_read_text(DEFAULT_INI))
        if dblock:
            settings = _parse_block(dblock)
            using_default = True
    return settings, raw, active, using_default


def _auto_quote(v):
    """Heuristik fürs Quoting neu hinzugefügter Werte: Bool/Zahl ohne, sonst mit."""
    if v in ("True", "False") or re.fullmatch(r"-?\d+(\.\d+)?", v or ""):
        return v
    return '"' + (v or "").replace('"', "") + '"'


def write_settings(new_values):
    """Schreibt neue Werte in die OptionSettings-Zeile, ohne den Rest der Datei zu verändern.
    Bereits vorhandene Keys werden aktualisiert, fehlende Keys aus new_values angehängt."""
    if os.path.exists(INI_PATH):
        raw = _read_text(INI_PATH)
    elif os.path.exists(DEFAULT_INI):
        raw = _read_text(DEFAULT_INI)
    else:
        raw = ""
    block = _extract_option_block(raw)
    if not block and os.path.exists(DEFAULT_INI):
        # Aktive Datei ohne brauchbare OptionSettings -> Default als Vorlage nehmen
        raw = _read_text(DEFAULT_INI)
        block = _extract_option_block(raw)

    current = _parse_block(block) if block else []
    current_keys = {k for k, _v, _q, _p in current}
    parts = []
    for k, old, quoted, paren in current:
        v = new_values.get(k, old)
        if quoted:
            v = '"' + v.replace('"', "") + '"'
        elif paren:
            v = "(" + v.strip("()") + ")"
        parts.append(f"{k}={v}")
    # Keys, die es noch nicht gibt, ergänzen (z. B. RCON-Optionen)
    for k, v in new_values.items():
        if k not in current_keys:
            parts.append(f"{k}={_auto_quote(v)}")
    new_line = "OptionSettings=(" + ",".join(parts) + ")"
    # WICHTIG: Palworld setzt die Datei auf Default zurück, wenn der OptionSettings-Block
    # nicht auf EINER Zeile steht. Daher jegliche Zeilenumbrüche entfernen.
    new_line = new_line.replace("\r", "").replace("\n", "")

    if block is not None:
        raw = raw.replace("OptionSettings=(" + block + ")", new_line, 1)
    else:
        header = "[/Script/Pal.PalGameWorldSettings]"
        if header in raw:
            raw = raw.replace(header, header + "\n" + new_line, 1)
        else:
            raw = (raw.rstrip() + "\n\n" if raw.strip() else "") + header + "\n" + new_line + "\n"

    os.makedirs(os.path.dirname(INI_PATH), exist_ok=True)
    with open(INI_PATH, "w", encoding="utf-8") as fh:
        fh.write(raw)


def write_raw(text):
    os.makedirs(os.path.dirname(INI_PATH), exist_ok=True)
    with open(INI_PATH, "w", encoding="utf-8") as fh:
        fh.write(text)


def ini_lookup():
    """Aktuelle Optionen als einfaches dict key->value (ohne Anführungszeichen)."""
    settings, _raw, _active, _ud = read_settings()
    return {k: v for k, v, _q, _p in settings}


def rcon_config():
    """Liest RCON-Einstellungen direkt aus der Rohdatei (robust gegen Format-Eigenheiten)."""
    raw = _read_text(INI_PATH) if os.path.exists(INI_PATH) else ""
    m = re.search(r"RCONEnabled\s*=\s*(True|False)", raw, re.IGNORECASE)
    enabled = bool(m) and m.group(1).lower() == "true"
    mp = re.search(r"RCONPort\s*=\s*(\d+)", raw)
    port = mp.group(1) if mp else "25575"
    ma = re.search(r'AdminPassword\s*=\s*"([^"]*)"', raw)
    password = ma.group(1) if ma else ""
    return enabled, port, password


def rcon_connect():
    enabled, port, password = rcon_config()
    if not enabled:
        raise RCONError("RCON ist in der Konfiguration deaktiviert (RCONEnabled=True setzen).")
    if not password:
        raise RCONError("Kein AdminPassword gesetzt – RCON braucht ein Passwort.")
    return PalworldRCON(CONF.get("rcon_host", "127.0.0.1"), port, password, timeout=3)


def ensure_rcon_configured():
    """Aktiviert RCON in der INI (localhost-intern). Erzeugt bei Bedarf ein AdminPassword.
    Gibt das erzeugte Passwort zurück (oder None, wenn schon eines vorhanden war)."""
    enabled, port, password = rcon_config()
    changes = {"RCONEnabled": "True"}
    if not port:
        changes["RCONPort"] = "25575"
    generated = None
    if not password:
        generated = secrets.token_urlsafe(12)
        changes["AdminPassword"] = generated
    write_settings(changes)
    return generated


# ---------------------------------------------------------------------------
# Routen
# ---------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = request.form.get("username", "")
        pw = request.form.get("password", "")
        info = load_users().get(user)
        if info and check_password_hash(info["password_hash"], pw):
            session["user"] = user
            session.permanent = False
            nxt = request.args.get("next") or url_for("dashboard")
            if not nxt.startswith("/"):
                nxt = url_for("dashboard")
            return redirect(nxt)
        flash(t("login_bad"))
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def dashboard():
    state = service_active(SERVICE)
    update_state = service_active(UPDATE_SERVICE)
    c_ip, c_port, c_kind = connect_info()
    return render_template(
        "dashboard.html",
        state=state,
        update_state=update_state,
        enabled=service_enabled(SERVICE),
        rcon_enabled=rcon_config()[0],
        logs=recent_logs(SERVICE),
        service=SERVICE,
        connect_ip=c_ip,
        connect_port=c_port,
        connect_kind=c_kind,
        version=installed_version(),
        build=installed_build(),
    )


@app.route("/status")
@login_required
def status():
    return jsonify(
        server=service_active(SERVICE),
        update=service_active(UPDATE_SERVICE),
        enabled=service_enabled(SERVICE),
        logs=recent_logs(SERVICE, 60),
        res=resources(),
    )


@app.route("/update-check", methods=["POST"])
@login_required
def update_check():
    if not check_csrf():
        return jsonify(ok=False, msg=t("csrf_invalid"))
    inst = installed_build()
    latest = latest_build()
    if inst and latest:
        status_key = "current" if inst == latest else "available"
    else:
        status_key = "unknown"
    return jsonify(ok=True, installed=inst, version=installed_version(),
                   latest=latest, status=status_key)


@app.route("/bans")
@login_required
def bans():
    return jsonify(entries=read_banlist())


@app.route("/bans/unban", methods=["POST"])
@login_required
def bans_unban():
    if not check_csrf():
        return jsonify(ok=False, msg=t("csrf_invalid"))
    sid = (request.form.get("steamid") or "").strip()
    if not sid:
        return jsonify(ok=False, msg=t("no_steamid"))
    rcon_ok = False
    try:
        with rcon_connect() as r:
            r.unban(sid)
        rcon_ok = True
    except (RCONError, OSError):
        pass
    removed = remove_from_banlist(sid)
    if rcon_ok:
        return jsonify(ok=True, msg=t("unban_done"), entries=read_banlist())
    if removed:
        return jsonify(ok=True, msg=t("unban_file_only"), entries=read_banlist())
    return jsonify(ok=False, msg=t("unban_failed"), entries=read_banlist())


@app.route("/action", methods=["POST"])
@login_required
def action():
    if not check_csrf():
        flash(t("csrf_invalid"))
        return redirect(url_for("dashboard"))
    act = request.form.get("act")
    if act == "start":
        # Start + Autostart aktivieren -> nach einem Reboot kommt der Server wieder hoch
        rc, out = svc("enable", "--now", SERVICE)
        flash(t("srv_started") if rc == 0 else out)
    elif act == "stop":
        # Stopp + Autostart deaktivieren -> nach einem Reboot bleibt der Server aus
        rc, out = svc("disable", "--now", SERVICE)
        flash(t("srv_stopped") if rc == 0 else out)
    elif act == "restart":
        svc("enable", SERVICE)  # sicherstellen, dass der Autostart aktiv bleibt
        rc, out = svc("restart", SERVICE)
        flash(t("srv_restarted") if rc == 0 else out)
    elif act == "update":
        rc, out = svc("start", UPDATE_SERVICE)
        flash(t("update_started")
              if rc == 0 else t("update_failed", out=out))
    else:
        flash(t("unknown_action"))
    return redirect(url_for("dashboard"))


@app.route("/update-logs")
@login_required
def update_logs():
    return jsonify(
        state=service_active(UPDATE_SERVICE),
        logs=recent_logs(UPDATE_SERVICE, 80),
    )


@app.route("/config", methods=["GET"])
@login_required
def config():
    settings, raw, active, using_default = read_settings()
    return render_template("config.html", settings=settings, raw=raw,
                           using_default=using_default, ini_path=INI_PATH)


@app.route("/config/save", methods=["POST"])
@login_required
def config_save():
    if not check_csrf():
        flash(t("csrf_invalid"))
        return redirect(url_for("config"))
    settings, _raw, _active, _ud = read_settings()
    new_values = {}
    for k, _old, _q, _p in settings:
        if ("opt_" + k) in request.form:
            new_values[k] = request.form.get("opt_" + k, "")
    write_settings(new_values)
    flash(t("config_saved"))
    return redirect(url_for("config"))


@app.route("/config/save-raw", methods=["POST"])
@login_required
def config_save_raw():
    if not check_csrf():
        flash(t("csrf_invalid"))
        return redirect(url_for("config"))
    write_raw(request.form.get("raw", ""))
    flash(t("raw_saved"))
    return redirect(url_for("config"))


@app.route("/players")
@login_required
def players():
    enabled, _port, _pw = rcon_config()
    if not enabled:
        return jsonify(enabled=False, reachable=False, players=[],
                       note="RCON in der Konfiguration aktivieren (RCONEnabled=True + AdminPassword).")
    if service_active(SERVICE) != "active":
        return jsonify(enabled=True, reachable=False, players=[],
                       note="Server läuft nicht.")
    try:
        with rcon_connect() as r:
            return jsonify(enabled=True, reachable=True, players=r.players())
    except (RCONError, OSError) as e:
        return jsonify(enabled=True, reachable=False, players=[], note=str(e))


@app.route("/rcon", methods=["POST"])
@login_required
def rcon_action():
    if not check_csrf():
        flash(t("csrf_invalid"))
        return redirect(url_for("dashboard"))
    act = request.form.get("act")
    try:
        with rcon_connect() as r:
            if act == "save":
                flash(t("world_saved", res=(r.save() or "OK")))
            elif act == "broadcast":
                msg = request.form.get("message", "").strip()
                if not msg:
                    flash(t("no_message"))
                else:
                    r.broadcast(msg)
                    flash(t("broadcast_sent"))
            elif act == "save_shutdown":
                r.save()
                r.shutdown(15, "Server_wird_gestoppt")
                # Autostart aus: nach einem Reboot bleibt der Server aus (letzter Status)
                svc("disable", SERVICE)
                flash(t("save_shutdown_done"))
            else:
                flash(t("unknown_rcon"))
    except (RCONError, OSError) as e:
        flash(t("rcon_failed", err=str(e)))
    return redirect(url_for("dashboard"))


@app.route("/rcon/player", methods=["POST"])
@login_required
def rcon_player():
    if not check_csrf():
        return jsonify(ok=False, msg=t("csrf_invalid"))
    act = request.form.get("act")
    steamid = (request.form.get("steamid") or "").strip()
    if not steamid:
        return jsonify(ok=False, msg=t("no_steamid"))
    if act not in ("kick", "ban"):
        return jsonify(ok=False, msg=t("unknown_rcon"))
    try:
        with rcon_connect() as r:
            if act == "kick":
                r.kick(steamid)
                return jsonify(ok=True, msg=t("player_kicked"))
            r.ban(steamid)
            return jsonify(ok=True, msg=t("player_banned"))
    except (RCONError, OSError) as e:
        return jsonify(ok=False, msg=t("rcon_failed", err=str(e)))


@app.route("/rcon/setup", methods=["POST"])
@login_required
def rcon_setup():
    if not check_csrf():
        flash(t("csrf_invalid"))
        return redirect(url_for("dashboard"))
    generated = ensure_rcon_configured()
    if generated:
        flash(t("rcon_enabled_gen", pw=generated))
    else:
        flash(t("rcon_enabled_existing"))
    return redirect(url_for("dashboard"))


@app.route("/account", methods=["GET", "POST"])
@login_required
def account():
    if request.method == "POST":
        if not check_csrf():
            flash(t("csrf_invalid"))
            return redirect(url_for("account"))
        me = session["user"]
        cur = request.form.get("current", "")
        new = request.form.get("new", "")
        conf = request.form.get("confirm", "")
        users = load_users()
        if not check_password_hash(users[me]["password_hash"], cur):
            flash(t("pw_wrong_current"))
        elif len(new) < MIN_PW:
            flash(t("pw_too_short", n=MIN_PW))
        elif new != conf:
            flash(t("pw_mismatch"))
        else:
            with _users_lock:
                users = load_users()
                users[me]["password_hash"] = generate_password_hash(new)
                save_users(users)
            flash(t("pw_changed"))
        return redirect(url_for("account"))
    return render_template("account.html")


@app.route("/users")
@login_required
def users_page():
    return render_template("users.html", users=load_users(), me=session["user"])


@app.route("/users/add", methods=["POST"])
@login_required
def users_add():
    if not check_csrf():
        flash(t("csrf_invalid"))
        return redirect(url_for("users_page"))
    name = request.form.get("username", "").strip()
    pw = request.form.get("password", "")
    users = load_users()
    if not USERNAME_RE.match(name):
        flash(t("user_invalid_name"))
    elif name in users:
        flash(t("user_exists"))
    elif len(pw) < MIN_PW:
        flash(t("user_pw_short", n=MIN_PW))
    else:
        with _users_lock:
            users = load_users()
            users[name] = {"password_hash": generate_password_hash(pw)}
            save_users(users)
        flash(t("user_created", name=name))
    return redirect(url_for("users_page"))


@app.route("/users/reset", methods=["POST"])
@login_required
def users_reset():
    if not check_csrf():
        flash(t("csrf_invalid"))
        return redirect(url_for("users_page"))
    name = request.form.get("username", "")
    pw = request.form.get("password", "")
    users = load_users()
    if name not in users:
        flash(t("user_not_found"))
    elif len(pw) < MIN_PW:
        flash(t("user_pw_short", n=MIN_PW))
    else:
        with _users_lock:
            users = load_users()
            users[name]["password_hash"] = generate_password_hash(pw)
            save_users(users)
        flash(t("user_pw_reset", name=name))
    return redirect(url_for("users_page"))


@app.route("/users/delete", methods=["POST"])
@login_required
def users_delete():
    if not check_csrf():
        flash(t("csrf_invalid"))
        return redirect(url_for("users_page"))
    name = request.form.get("username", "")
    me = session["user"]
    users = load_users()
    if name not in users:
        flash(t("user_not_found"))
    elif name == me:
        flash(t("user_delete_self"))
    elif len(users) <= 1:
        flash(t("user_delete_last"))
    else:
        with _users_lock:
            users = load_users()
            users.pop(name, None)
            save_users(users)
        flash(t("user_deleted", name=name))
    return redirect(url_for("users_page"))


if __name__ == "__main__":
    # Nur für lokale Tests; produktiv läuft die App über waitress (systemd).
    app.run(host="127.0.0.1", port=8080, debug=True)
