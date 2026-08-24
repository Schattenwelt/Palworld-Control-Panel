#!/usr/bin/env python3
"""Repariert eine durch den alten Split-Bug beschädigte PalWorldSettings.ini:
- stellt einen verstümmelten CrossplayPlatforms-Listenwert wieder her
- stellt sicher, dass RCONEnabled=True, RCONPort gesetzt, AdminPassword vorhanden ist
- schreibt garantiert EINE gültige OptionSettings-Zeile zurück
Gibt das ggf. erzeugte AdminPassword auf stdout aus (leer, wenn schon vorhanden).
Bricht ohne Schreiben ab (Exit 2), wenn die Zeile danach nicht sauber balanciert wäre.
"""
import os
import re
import secrets
import sys

INI = os.environ["INI"]
PORT = os.environ.get("RCON_PORT", "25575")

raw = open(INI, encoding="utf-8", errors="replace").read()

# --- 1) Beschädigten CrossplayPlatforms erkennen & reparieren -----------------
m = re.search(r"CrossplayPlatforms=\(([^()]*)\)", raw)
crossplay_broken = (m is None) or ("=" in (m.group(1) if m else ""))
if crossplay_broken:
    # Der alte Bug ließ nur "CrossplayPlatforms=(Steam" übrig und verschluckte den Rest.
    raw = re.sub(r"CrossplayPlatforms=\(Steam,(?=[A-Za-z_]\w*=)",
                 "CrossplayPlatforms=(Steam,Xbox,PS5,Mac),", raw, count=1)

# --- Parser (klammer- und anführungszeichenbewusst) ---------------------------
def extract(raw):
    marker = "OptionSettings=("
    i = raw.find(marker)
    if i == -1:
        return None, None, None
    start = i + len(marker); depth = 1; inq = False; j = start
    while j < len(raw):
        c = raw[j]
        if c == '"':
            inq = not inq
        elif not inq:
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    return raw[:i], raw[start:j], raw[j+1:]
        j += 1
    return raw[:i], raw[start:], ""


def split_opts(s):
    parts, buf, inq, depth = [], [], False, 0
    for c in s:
        if c == '"':
            inq = not inq; buf.append(c)
        elif c == "(" and not inq:
            depth += 1; buf.append(c)
        elif c == ")" and not inq:
            depth -= 1; buf.append(c)
        elif c == "," and not inq and depth == 0:
            parts.append("".join(buf)); buf = []
        else:
            buf.append(c)
    if buf:
        parts.append("".join(buf))
    return [p for p in parts if p.strip()]


pre, block, post = extract(raw)
pairs = []
if block is not None:
    for p in split_opts(block):
        if "=" in p:
            k, v = p.split("=", 1)
            pairs.append([k.strip(), v.strip()])
idx = {k: n for n, (k, v) in enumerate(pairs)}


def setkv(k, v):
    if k in idx:
        pairs[idx[k]][1] = v
    else:
        pairs.append([k, v]); idx[k] = len(pairs) - 1


# --- 2) RCON sicherstellen ----------------------------------------------------
genpw = ""
adm = pairs[idx["AdminPassword"]][1] if "AdminPassword" in idx else '""'
if adm.strip() in ('""', "", '"'):
    genpw = secrets.token_urlsafe(12)
    setkv("AdminPassword", '"%s"' % genpw)
setkv("RCONEnabled", "True")
if "RCONPort" not in idx or not pairs[idx["RCONPort"]][1].strip():
    setkv("RCONPort", PORT)

# --- 3) Einzeilig zusammenbauen ----------------------------------------------
line = "OptionSettings=(" + ",".join("%s=%s" % (k, v) for k, v in pairs) + ")"
line = line.replace("\r", "").replace("\n", "")

# --- 4) Sicherheitscheck: Klammern balanciert & CrossplayPlatforms sauber -----
def balanced(s):
    depth = 0; inq = False
    for c in s:
        if c == '"':
            inq = not inq
        elif not inq:
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth < 0:
                    return False
    return depth == 0

cp = re.search(r"CrossplayPlatforms=\(([^()]*)\)", line)
if not balanced(line) or (cp and "=" in cp.group(1)):
    sys.stderr.write("Reparatur würde keine saubere Zeile ergeben – nichts geschrieben.\n")
    sys.exit(2)

newraw = (pre + line + post) if block is not None \
    else "[/Script/Pal.PalGameWorldSettings]\n" + line + "\n"
open(INI, "w", encoding="utf-8").write(newraw)
print(genpw)
