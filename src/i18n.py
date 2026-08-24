#!/usr/bin/env python3
"""Leichtgewichtige DE/EN-Übersetzungen für das Palworld Control Panel."""

LANGS = ("de", "en")
DEFAULT_LANG = "de"

TRANSLATIONS = {
    # -- Navigation / allgemein --
    "nav_overview": {"de": "Übersicht", "en": "Overview"},
    "nav_config": {"de": "Konfiguration", "en": "Configuration"},
    "nav_users": {"de": "Benutzer", "en": "Users"},
    "nav_account": {"de": "Konto", "en": "Account"},
    "nav_logout": {"de": "Abmelden", "en": "Log out"},
    "save": {"de": "Speichern", "en": "Save"},

    # -- Login --
    "login_title": {"de": "Anmelden", "en": "Sign in"},
    "login_subtitle": {"de": "Melde dich an, um den Server zu verwalten.",
                       "en": "Sign in to manage the server."},
    "username": {"de": "Benutzername", "en": "Username"},
    "password": {"de": "Passwort", "en": "Password"},
    "login_btn": {"de": "Anmelden", "en": "Sign in"},
    "login_bad": {"de": "Benutzername oder Passwort ist falsch.",
                  "en": "Wrong username or password."},

    # -- Dashboard --
    "server_status": {"de": "Serverstatus", "en": "Server status"},
    "boot_on": {"de": "↻ startet nach einem Reboot automatisch",
                "en": "↻ starts automatically after a reboot"},
    "boot_off": {"de": "○ bleibt nach einem Reboot aus",
                 "en": "○ stays off after a reboot"},
    "btn_start": {"de": "Starten", "en": "Start"},
    "btn_restart": {"de": "Neu starten", "en": "Restart"},
    "btn_stop": {"de": "Stoppen", "en": "Stop"},
    "btn_update": {"de": "Aktualisieren", "en": "Update"},
    "confirm_update": {"de": "Update starten? Der Server wird dafür gestoppt.",
                       "en": "Start update? The server will be stopped for it."},
    "players_online": {"de": "Spieler online", "en": "Players online"},
    "server_log": {"de": "Server-Log", "en": "Server log"},
    "auto_refresh": {"de": "aktualisiert automatisch", "en": "auto-refreshing"},
    "update_running": {"de": "Update läuft", "en": "Update running"},
    "loading": {"de": "Lade …", "en": "Loading …"},
    "world_save": {"de": "Welt speichern", "en": "Save world"},
    "save_and_stop": {"de": "Speichern & Stoppen", "en": "Save & stop"},
    "confirm_save_stop": {"de": "Welt speichern und Server sauber herunterfahren?",
                          "en": "Save world and shut the server down cleanly?"},
    "msg_placeholder": {"de": "Nachricht an Spieler …", "en": "Message to players …"},
    "send": {"de": "Senden", "en": "Send"},
    "rcon_help": {
        "de": "RCON läuft server-intern über 127.0.0.1. „Speichern & Stoppen“ ist der "
              "saubere Weg zum Beenden – der normale Stopp speichert nicht zuverlässig.",
        "en": "RCON runs internally via 127.0.0.1. “Save & stop” is the clean way to shut "
              "down — a plain stop does not save reliably."},
    "rcon_setup_btn": {"de": "RCON einrichten", "en": "Set up RCON"},
    "rcon_setup_help": {
        "de": "Aktiviert RCON intern (localhost) und vergibt bei Bedarf ein Passwort. "
              "Danach den Server einmal neu starten.",
        "en": "Enables RCON internally (localhost) and sets a password if needed. "
              "Then restart the server once."},
    "nobody_online": {"de": "Niemand online.", "en": "Nobody online."},
    "rcon_unreachable": {"de": "RCON nicht erreichbar", "en": "RCON not reachable"},

    # -- Konfiguration --
    "cfg_notice": {
        "de": "Es existiert noch keine eigene PalWorldSettings.ini. Angezeigt werden die "
              "Standardwerte – beim ersten Speichern wird deine eigene Datei unter {path} angelegt.",
        "en": "No custom PalWorldSettings.ini exists yet. The default values are shown — "
              "your own file will be created at {path} on first save."},
    "tab_settings": {"de": "Einstellungen", "en": "Settings"},
    "tab_raw": {"de": "Rohdatei", "en": "Raw file"},
    "cfg_save_hint": {"de": "Änderungen greifen nach einem Neustart des Servers.",
                      "en": "Changes take effect after a server restart."},
    "cfg_save_raw_btn": {"de": "Rohdatei speichern", "en": "Save raw file"},
    "cfg_raw_warn": {"de": "Vorsicht: hier wird die Datei 1:1 überschrieben.",
                     "en": "Caution: this overwrites the file verbatim."},

    # -- Konto --
    "change_password": {"de": "Passwort ändern", "en": "Change password"},
    "logged_in_as": {"de": "angemeldet als", "en": "signed in as"},
    "current_password": {"de": "Aktuelles Passwort", "en": "Current password"},
    "new_password": {"de": "Neues Passwort", "en": "New password"},
    "repeat_new_password": {"de": "Neues Passwort wiederholen", "en": "Repeat new password"},

    # -- Benutzerverwaltung --
    "users_add_title": {"de": "Neuen Benutzer anlegen", "en": "Add new user"},
    "users_add_pw_ph": {"de": "Passwort (min. 6 Zeichen)", "en": "Password (min. 6 chars)"},
    "users_add_btn": {"de": "Anlegen", "en": "Add"},
    "users_equal_note": {
        "de": "Alle Konten sind gleichberechtigt und dürfen den Server steuern sowie "
              "Benutzer verwalten.",
        "en": "All accounts are equal and may control the server and manage users."},
    "users_you": {"de": "du", "en": "you"},
    "users_new_pw_ph": {"de": "neues Passwort", "en": "new password"},
    "users_reset_btn": {"de": "Zurücksetzen", "en": "Reset"},
    "users_delete_btn": {"de": "Löschen", "en": "Delete"},
    "users_delete_confirm": {"de": "Benutzer {name} wirklich löschen?",
                             "en": "Really delete user {name}?"},

    # -- Flash-Meldungen --
    "csrf_invalid": {"de": "Sicherheits-Token ungültig, bitte erneut versuchen.",
                     "en": "Security token invalid, please try again."},
    "srv_started": {"de": "Server gestartet.", "en": "Server started."},
    "srv_stopped": {"de": "Server gestoppt.", "en": "Server stopped."},
    "srv_restarted": {"de": "Server neu gestartet.", "en": "Server restarted."},
    "update_started": {
        "de": "Update gestartet – der Server wird dafür gestoppt. Fortschritt siehst du "
              "in den Update-Logs.",
        "en": "Update started — the server will be stopped. Progress shows in the update logs."},
    "update_failed": {"de": "Update-Start fehlgeschlagen: {out}",
                      "en": "Failed to start update: {out}"},
    "unknown_action": {"de": "Unbekannte Aktion.", "en": "Unknown action."},
    "world_saved": {"de": "Welt gespeichert: {res}", "en": "World saved: {res}"},
    "no_message": {"de": "Keine Nachricht eingegeben.", "en": "No message entered."},
    "broadcast_sent": {
        "de": "Nachricht gesendet. (Hinweis: Palworld zeigt bei Broadcasts oft nur das "
              "erste Wort vor einem Leerzeichen.)",
        "en": "Message sent. (Note: Palworld often shows only the first word before a "
              "space in broadcasts.)"},
    "save_shutdown_done": {
        "de": "Welt gespeichert, Server fährt in 15 Sekunden sauber herunter.",
        "en": "World saved, server will shut down cleanly in 15 seconds."},
    "unknown_rcon": {"de": "Unbekannte RCON-Aktion.", "en": "Unknown RCON action."},
    "rcon_failed": {"de": "RCON nicht möglich: {err}", "en": "RCON not possible: {err}"},
    "rcon_enabled_gen": {
        "de": "RCON aktiviert. Erzeugtes AdminPassword (= RCON- und In-Game-Admin-"
              "Passwort): {pw} — bitte notieren. Server neu starten, damit es greift.",
        "en": "RCON enabled. Generated AdminPassword (= RCON and in-game admin "
              "password): {pw} — please note it. Restart the server for it to take effect."},
    "rcon_enabled_existing": {
        "de": "RCON aktiviert (vorhandenes AdminPassword genutzt). Server neu starten, "
              "damit es greift.",
        "en": "RCON enabled (using existing AdminPassword). Restart the server for it to "
              "take effect."},
    "pw_wrong_current": {"de": "Aktuelles Passwort ist falsch.",
                         "en": "Current password is wrong."},
    "pw_too_short": {"de": "Neues Passwort muss mindestens {n} Zeichen haben.",
                     "en": "New password must be at least {n} characters."},
    "pw_mismatch": {"de": "Die neuen Passwörter stimmen nicht überein.",
                    "en": "The new passwords do not match."},
    "pw_changed": {"de": "Passwort geändert.", "en": "Password changed."},
    "user_invalid_name": {
        "de": "Ungültiger Benutzername (2–32 Zeichen: Buchstaben, Zahlen, . _ -).",
        "en": "Invalid username (2–32 chars: letters, digits, . _ -)."},
    "user_exists": {"de": "Diesen Benutzer gibt es schon.", "en": "This user already exists."},
    "user_pw_short": {"de": "Passwort muss mindestens {n} Zeichen haben.",
                      "en": "Password must be at least {n} characters."},
    "user_created": {"de": "Benutzer '{name}' angelegt.", "en": "User '{name}' created."},
    "user_not_found": {"de": "Benutzer nicht gefunden.", "en": "User not found."},
    "user_pw_reset": {"de": "Passwort für '{name}' neu gesetzt.",
                      "en": "Password for '{name}' reset."},
    "user_delete_self": {"de": "Du kannst dein eigenes Konto nicht löschen.",
                         "en": "You cannot delete your own account."},
    "user_delete_last": {"de": "Der letzte Benutzer kann nicht gelöscht werden.",
                         "en": "The last user cannot be deleted."},
    "user_deleted": {"de": "Benutzer '{name}' gelöscht.", "en": "User '{name}' deleted."},
    "config_saved": {"de": "Konfiguration gespeichert. Für die Übernahme den Server neu starten.",
                     "en": "Configuration saved. Restart the server to apply."},
    "raw_saved": {"de": "Rohdatei gespeichert. Für die Übernahme den Server neu starten.",
                  "en": "Raw file saved. Restart the server to apply."},
}


def translate(lang, key, **kw):
    if lang not in LANGS:
        lang = DEFAULT_LANG
    entry = TRANSLATIONS.get(key, {})
    text = entry.get(lang) or entry.get(DEFAULT_LANG) or key
    return text.format(**kw) if kw else text
