# ILIAS-Check mit Telegram installieren und konfigurieren

[English](INSTALL.md) | [Português do Brasil](INSTALL.pt-BR.md) | **Deutsch**

Diese Anleitung beschreibt eine vollständige Installation unter Linux: Python
vorbereiten, ILIAS-Zugang konfigurieren, einen Bot anlegen, Zugangsdaten eintragen,
testen und Worker sowie Monitor dauerhaft betreiben.

**Die Beispiele enthalten keine echten Zugangsdaten.** Ersetzen Sie vor dem Start
alle angegebenen Werte. Das Erstellen dieser Anleitung startet keine Dienste, ändert
kein Cron und versendet keine Nachrichten. Die Aktivierungsschritte unten führen Sie
aus, wenn Sie die beschriebenen Zugriffe und Sendungen freigeben möchten.

## 1. Die beiden Prozesse verstehen

| Prozess | Aufgabe | Laufzeit |
| --- | --- | --- |
| `ilias-check bot` | Empfängt Befehle im privaten Chat und fragt gespeicherte Beobachtungen ab. Eine Materialanfrage kann eine neue ILIAS-Prüfung auslösen. | Dauerhaft als Worker. |
| `ilias-check monitor` | Prüft ILIAS, aktualisiert den Zustand und versendet aktivierte Benachrichtigungen. | Einmal pro Aufruf; Cron kann ihn alle 12 Stunden starten. |

**Nur den Worker zu starten erzeugt keinen Sammelplan.** Beide Prozesse müssen
dasselbe Linux-Konto, dieselbe Konfigurationsdatei und dieselben Zustands-/Cache-
Verzeichnisse verwenden. Starten Sie nicht zwei Worker für denselben Bot.

Voraussetzungen:

- Linux mit Python **3.11 oder neuer**, `venv`, `pip` und Git.
- HTTPS-Zugang zu ILIAS und zu `api.telegram.org`; kein öffentlicher Port und kein
  Webhook erforderlich.
- Ein autorisiertes ILIAS-Konto, das mit dem implementierten Benutzername/Passwort-
  Login kompatibel ist. Die anfängliche Kompatibilität gilt für ILIAS 9.23; SSO/MFA
  und andere Layouts können Anpassungen erfordern.
- Ein persönliches Telegram-Konto. Diese Software arbeitet mit einem **privaten Chat**
  und einem einzigen autorisierten Benutzer, nicht mit Gruppen oder Kanälen.
- Für den Dauerbetrieb ein Rechner, der eingeschaltet bleibt. Der optionale Dienst in
  dieser Anleitung nutzt systemd auf Benutzerebene; die Zeitsteuerung nutzt Cron.

Die Installation verwendet diese Struktur:

```text
/opt/ilias/
├── venv/   # Python-virtualenv und ausführbare Dateien
├── check/  # Checkout der Software (Branch main)
└── data/   # private Konfiguration und Laufzeitdaten
    ├── ilias.env
    ├── inventory.json
    ├── monitor/     # SQLite-Zustand
    ├── support/     # heruntergeladene Dokumente und Manifest
    └── monitor.log
```

Die Datendateien entstehen in den jeweiligen Schritten. `data` liegt außerhalb des
Checkouts `check`. Verwenden Sie während Installation und Betrieb dasselbe normale
Linux-Konto; `sudo` ist nur zum Vorbereiten von `/opt/ilias` nötig (und optional für
*linger*).

## 2. Software herunterladen und installieren

Python prüfen:

```sh
python3 --version
```

Das Ergebnis muss 3.11 oder neuer sein. Installieren Sie unter Debian/Ubuntu bei Bedarf
`git`, `python3`, `python3-venv` und `python3-pip`; prüfen Sie die Version Ihrer
Distribution.

Bereiten Sie für eine **Neuinstallation** das Verzeichnis für den aktuellen Benutzer
vor. Führen Sie dies in einer Sitzung dieses normalen Benutzers aus, nicht in einer
Root-Shell:

```sh
sudo install -d -m 755 -o "$(id -un)" -g "$(id -gn)" /opt/ilias
git clone --branch main \
  https://github.com/richmont/ILIAS-Check.git /opt/ilias/check
python3 -m venv /opt/ilias/venv
cd /opt/ilias/check
/opt/ilias/venv/bin/python -m pip install -e '.[test]'
/opt/ilias/venv/bin/ilias-check --help
/opt/ilias/venv/bin/pytest -q
```

Die Implementierung ist bereits in `main` integriert. Wenn Sie schon eine Installation
haben, behalten Sie Ihre Dateien und nutzen Sie den Aktualisierungsabschnitt; klonen
Sie nicht über einen vorhandenen Checkout und ändern Sie nicht den Eigentümer einer
Installation eines anderen Benutzers.

Die Hilfe muss `collect`, `classify`, `monitor` und `bot` auflisten. Die Tests laufen
offline und benötigen keine echten Zugangsdaten. Sie müssen die venv nicht in der
Shell aktivieren: Die Beispiele rufen die Programme in `/opt/ilias/venv` direkt auf.

## 3. Private Dateien vorbereiten

Weiterhin im Projektverzeichnis:

```sh
umask 077
install -d -m 700 "/opt/ilias/data"
install -d -m 700 "/opt/ilias/data/monitor"
install -d -m 700 "/opt/ilias/data/support"
```

Kopieren Sie für eine **Erstinstallation** die Vorlage:

```sh
install -m 600 examples/config/ilias-local.env.example \
  /opt/ilias/data/ilias.env
```

Der letzte Befehl überschreibt eine vorhandene Datei. Wenn Sie bereits eine
Konfiguration haben, bearbeiten Sie diese und vergleichen Sie die Vorlagen; kopieren
Sie nicht darüber. Öffnen Sie die Datei in Ihrem bevorzugten Editor, zum Beispiel:

```sh
nano /opt/ilias/data/ilias.env
```

Im Repository liegen zwei vollständige Vorlagen:

- [ilias-local.env.example](examples/config/ilias-local.env.example): Vorbereitung und
  erste Sammlung, mit deaktiviertem Telegram.
- [ilias-telegram.env.example](examples/config/ilias-telegram.env.example): Referenz
  für den Telegram-Aktivierungsschritt, noch ohne automatische Anhänge.

Verwenden Sie **eine einzige private Datei** `ilias.env` für den normalen Betrieb. Die
Vorlagen sind vollständige Alternativen, keine nacheinander zu ladenden Dateien.
`--env-file` akzeptiert nur eine Datei und sucht nicht automatisch nach weiteren
`.env`-Dateien. Bereits in der Prozessumgebung gesetzte Variablen haben Vorrang vor
der Datei. Verwenden Sie nicht `source ilias.env`; das Programm liest das
dotenv-Format direkt.

## 4. ILIAS vor dem Start konfigurieren

Füllen Sie diesen Teil der privaten Datei aus:

```dotenv
# Beispiel: URL und alle REPLACE-Werte ersetzen.
ILIAS_BASE_URL=https://ilias.example.edu
ILIAS_CLIENT_ID=REPLACE_CLIENT_ID
ILIAS_USER='REPLACE_ILIAS_USERNAME'
ILIAS_PASS='REPLACE_ILIAS_PASSWORD'
ILIAS_PENDING_ROOTS=1001,1002
ILIAS_TIMEZONE=Europe/Berlin

ILIAS_TIMEOUT_SECONDS=20
ILIAS_PENDING_MAX_DEPTH=12
ILIAS_PENDING_MAX_REQUESTS=500
ILIAS_PENDING_EXCLUDE_EXERCISES=
ILIAS_PENDING_ALTERNATIVE_SETS={}
ILIAS_PENDING_INCLUDE_CONTEXTUAL=false

ILIAS_PENDING_DOWNLOAD_SUPPORT=false
ILIAS_PENDING_OUTPUT_DIR=/opt/ilias/data/support
ILIAS_SUPPORT_MAX_FILE_BYTES=20971520
ILIAS_SUPPORT_MAX_RUN_BYTES=104857600
ILIAS_SUPPORT_REVALIDATE_HOURS=12
ILIAS_SUPPORT_CACHE_MAX_BYTES=200000000
ILIAS_SUPPORT_NO_DEADLINE_TTL_HOURS=168
ILIAS_SUPPORT_RETENTION_MAX_HOURS=

ILIAS_TELEGRAM_ENABLED=false
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_ALLOWED_USER_ID=
TELEGRAM_ALLOWED_USER_IDS=
ILIAS_TELEGRAM_SEND_DOCUMENTS=false
ILIAS_TELEGRAM_MAX_DOCUMENT_BYTES=20971520
ILIAS_TELEGRAM_MAX_MESSAGE_CHARS=4000
ILIAS_MONITOR_STATE_DIR=/opt/ilias/data/monitor
ILIAS_PENDING_REMINDER_HOURS=0
```

| Einstellung | So ausfüllen |
| --- | --- |
| `ILIAS_BASE_URL` | HTTPS-URL der Installation, einschließlich Unterverzeichnis falls vorhanden, ohne `login.php`, Query-String oder Sitzungstoken. Beispiel: `https://ilias.example.edu/ilias`. |
| `ILIAS_CLIENT_ID` | Kennung der Installation; sie kann als `client_id` in der Login-URL erscheinen. Es ist nicht Ihr Benutzername. Erfinden Sie sie nicht, wenn sie fehlt: Bestätigen Sie sie mit der Installation. |
| `ILIAS_USER`, `ILIAS_PASS` | Autorisierter ILIAS-Benutzername und Passwort. Anführungszeichen helfen, Leerzeichen und `#` zu erhalten; beachten Sie die dotenv-Syntax bei Anführungszeichen im Wert. |
| `ILIAS_PENDING_ROOTS` | Echte IDs der zu prüfenden Ordner/Kurse. In `goto.php?target=fold_1001` ist die Referenz `1001`; in einer URL mit `ref_id=1002` ist es `1002`. Die Zahlen oben sind fiktiv. |
| `ILIAS_TIMEZONE` | Zeitzone der Installation. Für Bonn/Deutschland `Europe/Berlin`, einschließlich Sommerzeitregeln. Sie hängt nicht von der Zeitzone Ihres Rechners ab. |

Halten Sie Zustands- und Cache-Verzeichnisse außerhalb jedes Git-Checkouts, ohne
symbolische Bestandteile, mit korrektem Eigentümer und privaten Rechten. Die
Standard-Cache-Quote beträgt **200 MB dezimal**; der Bot kann sie nicht ändern.

Kleben Sie keine Passwörter/Tokens in Befehle, Issues oder Screenshots. Die
Zugangsdatei bleibt auf dem Host, nicht in Git. Prüfen Sie die Rechte, ohne den Inhalt
anzuzeigen:

```sh
chmod 600 /opt/ilias/data/ilias.env
stat -c '%a %n' /opt/ilias/data/ilias.env
```

Das Ergebnis muss mit `600` beginnen.

## 5. Telegram-Bot anlegen und Token speichern

1. Öffnen Sie den offiziellen [BotFather](https://t.me/BotFather) in Telegram.
2. Senden Sie `/newbot`, wählen Sie einen Namen und einen freien Benutzernamen mit
   Endung `bot`.
3. Kopieren Sie den von BotFather gelieferten Token in `TELEGRAM_BOT_TOKEN` Ihrer
   privaten Datei. Lassen Sie `ILIAS_TELEGRAM_ENABLED=false`.
4. Öffnen Sie den privaten Chat des neuen Bots und senden Sie `/start`. Es gibt noch
   keine Antwort: Der Worker wurde nicht gestartet.

Beispiel der Felder in diesem Schritt:

```dotenv
ILIAS_TELEGRAM_ENABLED=false
TELEGRAM_BOT_TOKEN='REPLACE_WITH_REAL_BOTFATHER_TOKEN'
TELEGRAM_CHAT_ID=
TELEGRAM_ALLOWED_USER_ID=
TELEGRAM_ALLOWED_USER_IDS=
ILIAS_TELEGRAM_SEND_DOCUMENTS=false
```

Das Verfahren zum Anlegen und Verwalten steht in der
[offiziellen BotFather-Dokumentation](https://core.telegram.org/bots/features#botfather).
Der Token ist ein Zugangsdatum, nicht der öffentliche Benutzername des Bots. Wenn er
offengelegt wurde, widerrufen Sie ihn im BotFather, ersetzen Sie den lokalen Wert und
starten Sie die beteiligten Prozesse neu.

## 6. IDs ermitteln, ohne den Worker zu starten

Sie benötigen zwei numerische IDs: den privaten Zielchat und den erlaubten Benutzer.
Nutzen Sie die API Ihres eigenen Bots; Sie müssen Ihre Daten keinem fremden Bot geben.

Senden Sie bei **gestopptem** Worker erneut `/start` im privaten Chat des Bots. Führen
Sie dieses Skript im Projektverzeichnis aus. Es liest den Token aus der privaten Datei,
hält ihn aus der Shell-Historie heraus und gibt keine Nachrichteninhalte aus:

```sh
/opt/ilias/venv/bin/python - <<'PY'
from pathlib import Path
import requests
from ilias_check.config import load_environment

values = load_environment(Path('/opt/ilias/data/ilias.env'))
token = (values.get('TELEGRAM_BOT_TOKEN') or '').strip()
if not token or 'REPLACE' in token:
    raise SystemExit('Bitte zuerst TELEGRAM_BOT_TOKEN in der privaten Datei eintragen.')

def api(method, payload):
    try:
        with requests.post(
            f'https://api.telegram.org/bot{token}/{method}',
            json=payload, timeout=(10, 35), allow_redirects=False,
        ) as response:
            status = response.status_code
            result = response.json()
    except Exception:
        raise SystemExit('Telegram-Abfrage fehlgeschlagen; Token und Antwort wurden ausgelassen.') from None
    if status != 200 or not isinstance(result, dict) or not result.get('ok'):
        raise SystemExit(f'Telegram hat die Abfrage abgelehnt (HTTP {status}). Token, Webhook und andere Worker prüfen.')
    return result['result']

if api('getWebhookInfo', {}).get('url'):
    raise SystemExit('Ein Webhook ist aktiv. Nutzen Sie einen eigenen Bot oder deaktivieren Sie die frühere Integration.')
updates = api('getUpdates', {'timeout': 0, 'limit': 100, 'allowed_updates': ['message']})
seen = set()
for update in updates:
    message = update.get('message', {})
    chat = message.get('chat', {})
    sender = message.get('from', {})
    if chat.get('type') != 'private' or sender.get('is_bot'):
        continue
    pair = (chat.get('id'), sender.get('id'))
    if None in pair or pair in seen:
        continue
    seen.add(pair)
    print(f'TELEGRAM_CHAT_ID={pair[0]}')
    print(f'TELEGRAM_ALLOWED_USER_ID={pair[1]}')
if not seen:
    print('Keine private Nachricht gefunden. Senden Sie /start an den Bot und versuchen Sie es erneut.')
PY
```

Kopieren Sie das Paar, das zu **Ihrem eigenen Gespräch** gehört, in die private Datei.
Verwenden Sie keine Gruppen-/Kanal-IDs oder die ID des Bots selbst. Wenn mehrere Paare
erscheinen, bestätigen Sie vor dem Konfigurieren des erlaubten Benutzers, welches Ihres
ist.

Das Skript versendet keine Nachrichten und erhöht den Empfangs-`offset` nicht. Führen
Sie diese Abfrage nicht aus, während ein anderer Verbraucher `getUpdates` nutzt.
Webhooks und Long Polling sind Alternativen; migrieren Sie bei einem wiederverwendeten
Bot die frühere Integration bewusst, bevor Sie diesen Worker nutzen. Referenzen:
[getUpdates](https://core.telegram.org/bots/api#getupdates) und
[getWebhookInfo](https://core.telegram.org/bots/api#getwebhookinfo).

## 7. Sammlung testen und erste Beobachtung speichern, ohne Telegram

Bestätigen Sie, dass `ILIAS_TELEGRAM_ENABLED=false` ist und die ILIAS-Felder korrekt
sind. Die Befehle dieses Schritts greifen auf ILIAS zu; keiner davon darf
Telegram-Nachrichten senden.

Speichern Sie zunächst ein privates Inventar:

```sh
cd /opt/ilias/check
umask 077
/opt/ilias/venv/bin/ilias-check collect \
  --env-file /opt/ilias/data/ilias.env \
  --progress \
  > "/opt/ilias/data/inventory.json"
```

`--progress` (auch von `monitor` akzeptiert) zeigt gedrosselte Zähler für Anfragen und
Objekte, den aktuellen Root und die verstrichene Zeit auf stderr. Das JSON auf stdout
bleibt sauber; die Fortschrittszeilen enthalten nie Titel, URLs oder Zugangsdaten.

Prüfen Sie dann unklare Fälle lokal:

```sh
/opt/ilias/venv/bin/ilias-check classify \
  --env-file /opt/ilias/data/ilias.env \
  --input "/opt/ilias/data/inventory.json" \
  --select needs-verification
```

Exit-Code `2` bedeutet ein Teilergebnis und kann bei nicht aufgelösten Seiten erwartet
werden. Er bedeutet nicht zwingend einen Login-Fehler. Beheben Sie fatale Fehler vor
dem Fortfahren; belassen Sie Unsicherheiten als Unsicherheiten.

Führen Sie nun den Monitor **mit weiterhin deaktiviertem Telegram** aus, um
Beobachtungen im mit dem Worker geteilten SQLite-Zustand zu speichern:

```sh
/opt/ilias/venv/bin/ilias-check monitor \
  --env-file /opt/ilias/data/ilias.env
```

Dies kann Warnungen in die Warteschlange legen, versendet sie aber nicht, solange
Telegram deaktiviert ist. **`collect` allein speist nicht die Historie des Bots, und
`monitor --dry-run` zeichnet diese Beobachtungen nicht auf.** Überspringen Sie den
ersten normalen Monitor-Lauf nicht.

## 8. Telegram aktivieren und Konfiguration vor dem Start prüfen

Ersetzen Sie in der **gleichen privaten Datei** die vorhandenen Felder; fügen Sie keine
doppelten Zeilen hinzu und überschreiben Sie Ihre ILIAS-Zugangsdaten nicht mit
Platzhaltern:

```dotenv
ILIAS_TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN='REPLACE_WITH_REAL_BOTFATHER_TOKEN'
TELEGRAM_CHAT_ID=REPLACE_NUMERIC_CHAT_ID
TELEGRAM_ALLOWED_USER_ID=REPLACE_NUMERIC_USER_ID
TELEGRAM_ALLOWED_USER_IDS=
ILIAS_TELEGRAM_SEND_DOCUMENTS=false
```

Die [Aktivierungsvorlage](examples/config/ilias-telegram.env.example) zeigt die
vollständige Datei. Die IDs müssen positive Ganzzahlen ohne `@`, Benutzername oder
Gruppenpräfix sein. Mit `ILIAS_TELEGRAM_SEND_DOCUMENTS=false` beginnen Sie nur mit
Text und Links.

Weitere Telegram-Konten können dieselben Beobachtungen abfragen: tragen Sie ihre
numerischen IDs komma-getrennt in `TELEGRAM_ALLOWED_USER_IDS` ein. Jedes Konto muss
den Bot aus einem eigenen privaten Chat anschreiben; Befehle im Hauptchat werden
weiterhin nur von `TELEGRAM_ALLOWED_USER_ID` akzeptiert. Benachrichtigungen gehen
weiterhin ausschließlich an `TELEGRAM_CHAT_ID`, und alle sehen dieselben ILIAS-Daten,
Historie und Aufbewahrungseinstellungen.

Prüfen Sie die Konfiguration **ohne Netzwerk und ohne den Worker zu starten**:

```sh
/opt/ilias/venv/bin/python - <<'PY'
from pathlib import Path
from ilias_check.config import CollectorConfig, ConfigurationError, load_environment
from ilias_check.cache_config import CacheError, boolean
from ilias_check.telegram import TelegramConfig

path = Path('/opt/ilias/data/ilias.env')
try:
    values = load_environment(path)
    required = ('ILIAS_BASE_URL', 'ILIAS_CLIENT_ID', 'ILIAS_USER', 'ILIAS_PASS',
                'ILIAS_PENDING_ROOTS')
    if any('REPLACE' in str(values.get(key, '')) for key in required):
        raise ConfigurationError('Die Konfiguration enthält noch REPLACE-Felder.')
    CollectorConfig.from_mapping(values)
    enabled = boolean(values, 'ILIAS_TELEGRAM_ENABLED')
    if enabled:
        telegram = ('TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID', 'TELEGRAM_ALLOWED_USER_ID',
                    'TELEGRAM_ALLOWED_USER_IDS')
        if any('REPLACE' in str(values.get(key, '')) for key in telegram):
            raise ConfigurationError('Die Telegram-Einstellungen enthalten noch REPLACE-Felder.')
        TelegramConfig.from_mapping(values, worker=True)
except (ConfigurationError, CacheError) as exc:
    raise SystemExit(f'Ungültige Konfiguration: {exc}') from None
print(f"Konfiguration gültig (Telegram {'aktiv' if enabled else 'deaktiviert'}). Es wurde keine Verbindung hergestellt.")
PY
```

Diese Prüfung kontrolliert das Format, nicht die Zugangsdaten, und belegt nicht, dass
die IDs Ihnen gehören. Bestätigen Sie diese Identität vor dem echten Test. Solange
`ILIAS_TELEGRAM_ENABLED=false` gilt, prüft sie nur die ILIAS-/Collector-Einstellungen;
die Worker-Prüfungen laufen erst nach dem Aktivieren von Telegram, sodass derselbe
Block auch vor diesem Schritt funktioniert.

Sie können den Monitor auch simulieren:

```sh
/opt/ilias/venv/bin/ilias-check monitor \
  --env-file /opt/ilias/data/ilias.env \
  --dry-run
```

Er kann je nach Konfiguration auf ILIAS zugreifen und den lokalen Cache pflegen, ruft
aber Telegram nicht auf und bestätigt Benachrichtigungen nicht als zugestellt.

## 9. Ersten echten Bot-Lauf durchführen

**Dieser Schritt aktiviert echte Kommunikation mit Telegram.** Starten Sie mit
geprüften Daten den Worker im Vordergrund:

```sh
/opt/ilias/venv/bin/ilias-check bot \
  --env-file /opt/ilias/data/ilias.env
```

Lassen Sie dieses Terminal offen. Senden Sie im privaten Chat des Bots `/start` und
`/pendentes`. Er sollte auf Portugiesisch antworten, mit Originaltiteln/-anweisungen
aus ILIAS und Beobachtungszeiten. `/verificar` muss unklare Fälle erhalten. Deuten Sie
eine leere Liste nicht als Abschluss aller Aufgaben.

Erste Befehle:

| Befehl | Erwartetes Ergebnis |
| --- | --- |
| `/ajuda` | Hilfe und Navigation. |
| `/pendentes` | Bestätigte ausstehende Uploads. |
| `/entregues` | Abgabehistorie; keine Freigabe impliziert. |
| `/encerradas` | Ohne Abgabe geschlossen. |
| `/futuras` | Zeitraum noch nicht geöffnet. |
| `/verificar` | Unklare Fälle, Quelle und Feedback-Einladung. |
| `/resumo` | Zählung je Situation und Abdeckungswarnungen. |
| `/configuracoes` | Aufbewahrung und Cache-Nutzung/Quote. |
| `/materiais` | Auswählbare Materialien; Antippen autorisiert das Senden dieser Kopie über Telegram. |
| `/relatar` | Prüfbarer Bericht über die Software; es wird kein Issue automatisch geöffnet. |

Auch bei deaktivierten **automatischen** Anhängen kann eine ausdrückliche Anfrage in
`/materiais` das gewählte Material herunterladen und senden. Tippen Sie diese Aktion
nicht an, wenn Sie noch keine Dokumente übertragen möchten. Der Bot lädt keine Dateien
herunter, die Sie als Antwort senden.

Um Benachrichtigungen zu testen, führen Sie in **einem anderen Terminal** aus:

```sh
cd /opt/ilias/check
/opt/ilias/venv/bin/ilias-check monitor \
  --env-file /opt/ilias/data/ilias.env
```

Dieser Lauf kann anstehende Warnungen aus der Warteschlange senden — nicht
zwangsläufig eine einzelne Nachricht. Prüfen Sie Empfänger, Links und
Abdeckungsqualifizierungen. Normale Wiederholungen ohne Änderungen dürfen dieselben
Warnungen nicht erneut senden; ein unklarer Timeout kann bei einem späteren Versuch
Duplikate erzeugen.

Wenn Sie Befehlsvorschläge in Telegram möchten, nutzen Sie `/setcommands` im
BotFather, wählen Sie Ihren Bot und senden Sie zum Beispiel:

```text
start - Start
ajuda - Hilfe
pendentes - Ausstehende Aufgaben
entregues - Abgabehistorie
encerradas - Ohne Abgabe geschlossen
verificar - Unklare Fälle
materiais - Begleitmaterialien
configuracoes - Aufbewahrung und Speicher
relatar - Softwareproblem melden
cancelar - Dialog abbrechen
```

Das konfiguriert nur Vorschläge; die Software prüft die Autorisierung weiterhin.
Siehe [Telegram-Befehle](https://core.telegram.org/bots/features#commands).

Wenn Sie den Vordergrundtest beenden, drücken Sie **Strg+C**, um den Worker zu stoppen,
bevor Sie den Dienst im nächsten Schritt starten.

Dokument-Schaltflächen versuchen zuerst, eine gültige lokale Cache-Kopie zu
verwenden. Sind Aktivitätsdaten oder Dateiprüfung zu alt, fehlt die Kopie oder ist
sie ungültig, kündigt der Bot eine möglicherweise mehrere Minuten dauernde
ILIAS-Prüfung an, bevor er das Material von der Quelle abruft.

## 10. Worker mit systemd auf Benutzerebene betreiben

Dieser Schritt ist für Tests optional, aber nützlich auf einem dauerhaft laufenden
Host. Führen Sie ihn als dasselbe Linux-Konto aus, das für Konfiguration und Sammlung
verwendet wurde. Betreiben Sie den manuellen Worker und den Dienst nicht gleichzeitig.

Erstellen Sie `~/.config/systemd/user/ilias-check-bot.service`:

```sh
mkdir -p "$HOME/.config/systemd/user"
nano "$HOME/.config/systemd/user/ilias-check-bot.service"
```

Vollständiger Inhalt:

```ini
[Unit]
Description=ILIAS-Check private Telegram worker
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
WorkingDirectory=/opt/ilias/check
ExecStart=/opt/ilias/venv/bin/ilias-check bot --env-file /opt/ilias/data/ilias.env
UMask=0077
Restart=on-failure
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
```

Die absoluten Pfade folgen der Struktur `/opt/ilias`. Wenn Sie an einem anderen Ort
installieren, passen Sie `WorkingDirectory` und `ExecStart` an. Das Programm liest die
`.env` über `--env-file`; eine zusätzliche `EnvironmentFile` ist nicht nötig. Referenz:
[systemd-Units und Spezifizierer](https://www.freedesktop.org/software/systemd/man/latest/systemd.unit.html#Specifiers).

Aktivieren und prüfen:

```sh
systemctl --user daemon-reload
systemctl --user enable --now ilias-check-bot.service
systemctl --user status ilias-check-bot.service
journalctl --user -u ilias-check-bot.service -n 50 --no-pager
```

Der Dienst sollte `active (running)` zeigen. Prüfen Sie zusätzlich eine echte Antwort
auf `/ajuda`; der Prozesszustand allein belegt nicht, dass der Chat funktioniert. Bei
künftigen `.env`-Änderungen starten Sie den Worker neu:

```sh
systemctl --user restart ilias-check-bot.service
```

Damit der Benutzermanager nach dem Logout weiterläuft und beim Boot startet, kann ein
Administrator *linger* für Ihr Konto aktivieren:

```sh
sudo loginctl enable-linger IHR_LINUX_BENUTZER
```

Ersetzen Sie den Platzhalter durch den echten Host-Benutzer, nicht durch den
Telegram-Benutzernamen. Diese Option ändert das Startverhalten des Kontos; nutzen Sie
sie nur, wenn Sie diesen Dauerdienst möchten. Siehe
[loginctl](https://www.freedesktop.org/software/systemd/man/latest/loginctl.html).
Ohne systemd auf Benutzerebene halten Sie den Worker im Vordergrund oder nutzen den
Supervisor Ihrer Umgebung mit demselben Programm, Benutzer und derselben
Konfigurationsdatei.

## 11. Prüfungen alle 12 Stunden planen

Der Dienst oben empfängt Befehle; die periodische Aktualisierung ist Aufgabe des
Monitors. Cron muss auf dem Host verfügbar und aktiv sein. Legen Sie ein privates Log an:

```sh
touch "/opt/ilias/data/monitor.log"
chmod 600 "/opt/ilias/data/monitor.log"
crontab -e
```

Fügen Sie diese Zeile zur Crontab desselben Benutzers hinzu, der den Worker ausführt:

```cron
0 */12 * * * /opt/ilias/venv/bin/ilias-check monitor --env-file /opt/ilias/data/ilias.env >> /opt/ilias/data/monitor.log 2>&1
```

Prüfen Sie mit:

```sh
crontab -l
```

Das Beispiel läuft um 00:00 und 12:00 in der Zeitzone des Schedulers/Hosts.
`ILIAS_TIMEZONE=Europe/Berlin` steuert die Interpretation der ILIAS-Fristen, ändert
aber nicht die Cron-Zeitzone. Sie benötigen keine Shell mit aktivierter venv: Die
Zeile nutzt das absolute Programm.

Der Monitor verhindert Überschneidungen für dasselbe Konto/denselben Zustand. Ein
Aufruf, der den vorherigen Lauf noch aktiv findet, kann mit Code `3` enden; starten Sie
keine neuen Worker, um die Sperre zu umgehen. Prüfen Sie das Log und warten Sie auf den
nächsten Lauf.

`ILIAS_PENDING_REMINDER_HOURS=0` deaktiviert wiederholte Erinnerungen: Eine Sammlung
alle 12 Stunden bedeutet keine Nachricht alle 12 Stunden. Für optionale tägliche
Erinnerungen setzen Sie `ILIAS_PENDING_REMINDER_HOURS=24`; relevante Änderungen können
weiterhin Warnungen erzeugen.

## 12. Materialien nur bei Bedarf aktivieren

Es gibt drei verschiedene Steuerungen:

| Ziel | Einstellung/Aktion |
| --- | --- |
| Text- und Link-Benachrichtigungen | `ILIAS_TELEGRAM_ENABLED=true`, `ILIAS_TELEGRAM_SEND_DOCUMENTS=false`. |
| Automatischer lokaler Cache geeigneter Begleitmaterialien | `ILIAS_PENDING_DOWNLOAD_SUPPORT=true`. Das allein autorisiert kein Senden über Telegram. |
| Automatische Anhänge in Benachrichtigungen | `ILIAS_PENDING_DOWNLOAD_SUPPORT=true` und `ILIAS_TELEGRAM_SEND_DOCUMENTS=true`, nach Einwilligung in die Dokumentübertragung. |
| Senden eines gewählten Materials | Ausdrückliche Download-Aktion in `/materiais`, ohne künftige automatische Anhänge zu aktivieren. |

Für einen lokalen Cache bearbeiten Sie die vorhandenen Felder:

```dotenv
ILIAS_PENDING_DOWNLOAD_SUPPORT=true
ILIAS_PENDING_OUTPUT_DIR=/opt/ilias/data/support
ILIAS_TELEGRAM_SEND_DOCUMENTS=false
```

Nur wenn Sie zusätzlich automatische Anhänge möchten:

```dotenv
ILIAS_TELEGRAM_SEND_DOCUMENTS=true
```

Starten Sie den Worker nach dem Bearbeiten neu und führen Sie eine manuelle Prüfung
aus, bevor Sie dem Zeitplan vertrauen. Eine bereits abgeschlossene Benachrichtigung
wird nicht zwangsläufig erneut gesendet, nur weil sich die Anhangseinstellung geändert
hat.

Die Standardgrenzen sind 20 MiB pro Datei, 100 MiB pro Lauf und 200 MB dezimal im
Cache. Fristen/bestätigte Abgaben beenden Zuordnungen; ohne Frist beträgt die
Standardaufbewahrung 168 Stunden. Der Bot erlaubt Aufbewahrungsänderungen in
`/configuracoes`, ändert aber nicht die Quote und bietet keine manuelle Bereinigung.
Bereits von Telegram empfangene Kopien können durch lokale Bereinigung nicht
widerrufen werden. Siehe [den Cache-Lebenszyklus](docs/support-cache.md).

## 13. Stoppen, aktualisieren oder sichern

Um den Worker zu stoppen und den automatischen Start zu verhindern:

```sh
systemctl --user disable --now ilias-check-bot.service
```

Entfernen/kommentieren Sie außerdem die Monitor-Zeile in `crontab -e`, wenn Sie die
geplanten Prüfungen beenden möchten. `ILIAS_TELEGRAM_ENABLED=false` betrifft neue
Aufrufe; ein bereits laufender Worker behält die geladene Konfiguration, bis er
gestoppt/neu gestartet wird. Keine dieser Aktionen gibt Antworten ab oder ändert
Aktivitäten in ILIAS.

Pausieren Sie vor dem Aktualisieren des Codes oder dem Kopieren der SQLite-Datenbank für
eine Sicherung Worker und Zeitplan und warten Sie, bis eine laufende Sammlung beendet
ist. Bewahren Sie die `.env`, das Zustandsverzeichnis und deren private Rechte. Das
Löschen des Zustands verliert Historie/Deduplizierung und kann erneut erste Warnungen
erzeugen. Der Cache ist entbehrlich, keine offizielle Quelle.

Aktualisieren Sie bei gestoppten Prozessen `main`. Wenn der Checkout noch auf dem alten
Entwicklungsbranch liegt, wählt der `switch`-Befehl unten den integrierten Branch:

```sh
cd /opt/ilias/check
git fetch origin
git switch main
git pull --ff-only origin main
/opt/ilias/venv/bin/python -m pip install -e '.[test]'
/opt/ilias/venv/bin/pytest -q
```

Wenn lokale Änderungen oder Migrationshinweise in der neuen Version vorliegen, klären
Sie diese vor dem Fortfahren. Prüfen Sie nach der Konfigurationskontrolle die
Konfiguration, aktivieren Sie den Worker erneut und stellen Sie den pausierten Zeitplan
wieder her.

## Schnelle Fehlersuche

| Symptom | Was prüfen |
| --- | --- |
| Der Bot antwortet nicht | Dienst/Terminal aktiv, `ILIAS_TELEGRAM_ENABLED=true`, Token, IDs und privater Chat. Senden Sie nach dem Neustart einen neuen Befehl. |
| Leere ID-Abfrage | Senden Sie `/start` an den richtigen Bot; stoppen Sie andere Verbraucher vor der Wiederholung. |
| Telegram HTTP 401 | Falscher oder widerrufener Token; ersetzen Sie ihn durch den aktuellen BotFather-Token. |
| Telegram HTTP 409/Konflikt | Ein anderer Worker/`getUpdates`-Verbraucher oder eine Webhook-Konfiguration. Führen Sie die ID-Abfrage nicht parallel zum Worker aus. |
| Telegram HTTP 403 | Bot vom Empfänger blockiert oder Chat ohne Zugriff; prüfen Sie den privaten Chat und beginnen Sie das Gespräch. |
| Keine Daten nach der Installation | Führen Sie `monitor` einmal mit derselben `.env` und demselben Zustand aus; `collect` und `monitor --dry-run` speisen die persistenten Abfragen nicht. |
| Code `2` / unklar | Prüfen Sie Abdeckung und `/verificar`; fehlende Daten belegen weder Abgabe noch Abwesenheit von Aufgaben. |
| ILIAS-Authentifizierungsfehler | Basis-URL, Client-ID, Benutzername/Passwort und Formularkompatibilität; veröffentlichen Sie zur Diagnose kein HTML und keine Zugangsdaten. |
| Fehler beim privaten Verzeichnis | Eigentümer, Modus `0700`, Pfad außerhalb von Git und keine Symlinks; verwaltete Dateien nutzen `0600`. |
| `.env`-Wert scheint ignoriert | Im Prozess exportierte Variablen haben Vorrang; der Worker muss nach der Bearbeitung neu gestartet werden. Geben Sie zur Untersuchung nicht die gesamte Umgebung aus. |
| Material nicht gesendet | Einwilligung, aktuelle Klassifizierung, Zuordnung, Frist/TTL, Integrität, Typ, Größe und Quote; nutzen Sie den Originallink, wenn nicht verfügbar. |
| `systemctl --user` ohne Bus | Benutzersitzung/-manager in dieser Umgebung nicht verfügbar; prüfen Sie die Linux-Sitzung oder nutzen Sie einen geeigneten Supervisor. |

Eine abgeschlossene Installation bedeutet: Zugangsdaten eingetragen und privat, lokale
Sammlung geprüft, korrekter Eigentümer/Chat, echte Befehlsantwort, Monitor-Lauf mit
Erfolg oder verstandener Unvollständigkeit, und Worker/Zeitplan nur bei Bedarf aktiviert.
Siehe auch [Telegram-Betrieb](docs/telegram.md) und
[die Bereitstellungs-Checkliste](docs/deployment-checklist.md).
