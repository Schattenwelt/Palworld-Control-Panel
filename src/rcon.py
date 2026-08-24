#!/usr/bin/env python3
"""
Minimaler Source-RCON-Client für Palworld – ohne externe Abhängigkeiten.
Palworld nutzt das Source-RCON-Protokoll; RCON-Passwort ist das AdminPassword,
Port kommt aus RCONPort (Standard 25575).
"""
import socket
import struct

SERVERDATA_AUTH = 3
SERVERDATA_AUTH_RESPONSE = 2
SERVERDATA_EXECCOMMAND = 2
SERVERDATA_RESPONSE_VALUE = 0


class RCONError(Exception):
    pass


class PalworldRCON:
    def __init__(self, host, port, password, timeout=3):
        self.host = host
        self.port = int(port)
        self.password = password
        self.timeout = timeout
        self.sock = None
        self._id = 0

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            finally:
                self.sock = None

    def _recvn(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise RCONError("Verbindung vom Server geschlossen.")
            buf += chunk
        return buf

    def _send(self, ptype, body):
        self._id += 1
        payload = struct.pack("<ii", self._id, ptype) + body.encode("utf-8") + b"\x00\x00"
        self.sock.sendall(struct.pack("<i", len(payload)) + payload)
        return self._id

    def _recv(self):
        (length,) = struct.unpack("<i", self._recvn(4))
        data = self._recvn(length)
        pid, ptype = struct.unpack("<ii", data[:8])
        body = data[8:-2] if len(data) >= 10 else b""
        return pid, ptype, body.decode("utf-8", errors="replace")

    def connect(self):
        self.sock = socket.create_connection((self.host, self.port), self.timeout)
        self.sock.settimeout(self.timeout)
        auth_id = self._send(SERVERDATA_AUTH, self.password)
        pid, ptype, _ = self._recv()
        # Manche Server senden zuerst einen leeren RESPONSE_VALUE
        if ptype == SERVERDATA_RESPONSE_VALUE:
            pid, ptype, _ = self._recv()
        if pid == -1 or pid != auth_id:
            raise RCONError("RCON-Authentifizierung fehlgeschlagen (AdminPassword prüfen).")

    def command(self, cmd):
        self._send(SERVERDATA_EXECCOMMAND, cmd)
        _, _, body = self._recv()
        return body.strip()

    # -- bequeme Wrapper --------------------------------------------------
    def info(self):
        return self.command("Info")

    def players(self):
        """Liste aus dicts: {name, playeruid, steamid}. Header wird übersprungen."""
        raw = self.command("ShowPlayers")
        rows = []
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.lower().startswith("name,"):
                continue
            fields = line.split(",")
            if len(fields) >= 3:
                rows.append({
                    "name": fields[0],
                    "playeruid": fields[1],
                    "steamid": fields[-1],
                })
            elif fields and fields[0]:
                rows.append({"name": fields[0], "playeruid": "", "steamid": ""})
        return rows

    def save(self):
        return self.command("Save")

    def broadcast(self, message):
        return self.command("Broadcast " + message)

    def kick(self, steamid):
        return self.command("KickPlayer " + str(steamid))

    def ban(self, steamid):
        return self.command("BanPlayer " + str(steamid))

    def shutdown(self, seconds=15, message="Server_wird_gestoppt"):
        # Palworld: Shutdown <sekunden> <nachricht ohne Leerzeichen>
        return self.command(f"Shutdown {int(seconds)} {message}")
