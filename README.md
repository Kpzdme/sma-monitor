# SMA Monitor

Ein leichtgewichtiger Python-Monitor, der den Schlusskurs eines Index oder ETFs gegen seine 250-Tage-Linie (Simple Moving Average, SMA250) prüft und bei einem Trendwechsel eine Push-Benachrichtigung via [ntfy](https://ntfy.sh) versendet.

Entwickelt für SMA250-basierte Anlagestrategien (z.B. in Kombination mit Leverage-ETFs), bei denen ein systematisches Signal beim Über- bzw. Unterschreiten der 250-Tage-Linie als Ein- bzw. Ausstiegsindikator dient.

## Features

- **Kostenlose Datenquelle:** Yahoo Finance via [`yfinance`](https://github.com/ranaroussi/yfinance), kein API-Key erforderlich
- **Frei konfigurierbarer Ticker:** Standardmäßig MSCI World Index (`^990100-USD-STRD`), beliebig anpassbar
- **Zweimal tägliche Prüfung:** Mo–Fr um 09:00 und 17:00 Uhr (lokale Zeit) via systemd-Timer
- **Hysterese-Logik:** Konfigurierbarer Pufferzone um die SMA250 zur Vermeidung von Whipsaw-Signalen
- **State-Persistenz:** Benachrichtigung erfolgt ausschließlich beim tatsächlichen Statuswechsel, nicht bei jedem Check
- **Fehler-Notifications:** Auch Datenabruf-Fehler lösen eine ntfy-Warnung aus
- **Hardened systemd-Service:** Restriktive Sandbox-Konfiguration (`ProtectSystem`, `NoNewPrivileges` etc.)

## Funktionsweise

1. Der Timer triggert das Script um 09:00 und 17:00 Uhr (Mo–Fr).
2. Das Script lädt die letzten ~300 Handelstage des konfigurierten Tickers via Yahoo Finance.
3. Aus den letzten 250 Schlusskursen wird die SMA250 berechnet.
4. Der aktuelle Kurs wird gegen die SMA250 verglichen, unter Berücksichtigung einer Hysteresezone.
5. Bei einem Statuswechsel (z.B. von "unter SMA250" zu "über SMA250") wird eine Push-Notification gesendet.
6. Der neue Status wird in einer JSON-Datei persistiert, sodass keine Doppelbenachrichtigungen entstehen.

## Voraussetzungen

- Linux-System mit systemd (z.B. Debian 12, Ubuntu 22.04/24.04 – auch in einem LXC-Container)
- Python ≥ 3.10
- Netzwerkzugriff auf `query1.finance.yahoo.com`, `fc.yahoo.com` sowie den ntfy-Server
- Ein ntfy-Topic (entweder auf [ntfy.sh](https://ntfy.sh) oder selbst gehostet)
- ntfy-App auf dem Smartphone ([Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy) / [iOS](https://apps.apple.com/us/app/ntfy/id1625396347) / [F-Droid](https://f-droid.org/packages/io.heckel.ntfy/))

## Installation

### 1. Repository klonen

```bash
git clone https://github.com/kpzdme/sma-monitor.git
cd sma-monitor
```

### 2. ntfy-Topic konfigurieren

In `sma250_monitor.py` die folgenden Werte anpassen:

```python
NTFY_SERVER = "https://ntfy.sh"  # oder https://ntfy.deine-domain.de bei self-hosted
NTFY_TOPIC = "DEIN_SECRET"  # unbedingt ändern!
```

> **Sicherheitshinweis:** Auf dem öffentlichen ntfy.sh ist der Topic-Name das einzige Geheimnis. Verwende einen langen, zufälligen String, z.B. via `openssl rand -hex 16`. Wer das Topic kennt, kann mitlesen und Nachrichten senden.

### 3. Installation ausführen

```bash
sudo ./install.sh
```

Das Script führt folgende Schritte aus:
- Installation von Python und `python3-venv`
- Anlegen eines unprivilegierten Service-Users `sma250`
- Anlegen des Installationsverzeichnisses unter `/opt/sma250-monitor/`
- Anlegen des State-Verzeichnisses unter `/var/lib/sma250-monitor/`
- Einrichtung eines Python-venvs und Installation der Abhängigkeiten
- Installation und Aktivierung der systemd-Units

### 4. ntfy-App einrichten

ntfy-App auf dem Smartphone installieren und das Topic abonnieren (gleicher Name wie in der Config).

### 5. Testlauf

```bash
sudo -u sma250 /opt/sma250-monitor/venv/bin/python /opt/sma250-monitor/sma250_monitor.py
```

Beim ersten Lauf wird der Status (`ABOVE` oder `BELOW`) ermittelt und es erfolgt eine initiale Benachrichtigung. Danach erfolgen weitere Benachrichtigungen ausschließlich bei Statuswechseln.

## Konfiguration

Alle Parameter befinden sich im Konfigurationsblock am Anfang von `sma250_monitor.py`.

### Ticker

Der Ticker bestimmt, welches Wertpapier oder welcher Index überwacht wird.

```python
TICKER = "^990100-USD-STRD"
```

Empfohlene Ticker:

| Ticker | Beschreibung | Notiert in | Bemerkung |
|---|---|---|---|
| `^990100-USD-STRD` | MSCI World Index (Standard) | USD | **Empfohlen** – reiner Index ohne ETF-Wrapper, kein FX-Rauschen |
| `^GSPC` | S&P 500 Index | USD | Beispiel für andere Indizes |
| `^NDX` | NASDAQ 100 Index | USD | Beispiel für andere Indizes |

> **Hinweis zu EUR-notierten ETFs:** Für die SMA250-Signalgenerierung sollte ein USD-notierter Ticker gewählt werden, auch wenn am Ende ein EUR-ETF gehandelt wird. Andernfalls verfälscht der EUR/USD-Wechselkurs das Signal – in Extremphasen (z.B. EUR/USD-Bewegungen 2022) können dadurch falsche Signale entstehen.

### Hysterese (Schwankungspuffer)

Die Hysterese definiert eine prozentuale Pufferzone um die SMA250, innerhalb derer kein Signal ausgelöst wird. Sie reduziert Whipsaw-Signale, wenn der Kurs nahe der SMA250 oszilliert.

```python
HYSTERESIS_PCT = 1.0  # ±1 % um SMA250
```

Beispiele, es ist jedoch theoretisch jeder Wert möglich:

| Wert | Verhalten |
|---|---|
| `0.0` | Kein Puffer – jede Kreuzung löst ein Signal aus (Whipsaw-Risiko hoch) |
| `0.5` | Geringer Puffer – schnelle Reaktion, gelegentliche Fehlsignale |
| `1.0` | Standard – guter Kompromiss zwischen Reaktionsschnelligkeit und Robustheit |
| `2.0` | Konservativ – sehr robust gegen Rauschen, dafür spätere Trigger |


Die Pufferzone ist symmetrisch: Bei einem Wert von `1.0` wird ein `ABOVE`-Signal nur ausgelöst, wenn der Kurs > SMA250 × 1.01 ist, ein `BELOW`-Signal nur bei Kurs < SMA250 × 0.99. Dazwischen liegt der Status `NEUTRAL` und es erfolgt keine Statusänderung.

### SMA-Periode

Die Anzahl der Handelstage, über die der Durchschnitt gebildet wird.

```python
SMA_PERIOD = 250
```

Gängige Werte:

| Periode | Verwendung |
|---|---|
| 50 | Kurzfristiger Trend, sehr reaktiv |
| 100 | Mittelfristiger Trend |
| 150 | Quartalstrend |
| **250** | **Langfristiger Trend (Standard)** – etabliertes Marktbreite-Signal |
| 250 | Jahres-SMA |

### Zeitraum für den Datenabruf

Wie viele Handelstage Yahoo Finance abrufen soll. Muss mindestens `SMA_PERIOD` betragen, ein Puffer von ~50 Tagen gegen Datenausfälle ist empfohlen.

```python
def fetch_price_data(ticker: str, period_days: int = 300) -> tuple[float, float]:
```

Bei Anpassung der `SMA_PERIOD` sollte auch `period_days` mitskalieren (Faustregel: `SMA_PERIOD + 50`).

### Prüfzeitpunkte

Die Cron-ähnlichen Trigger-Zeiten sind in `sma250-monitor.timer` definiert:

```ini
OnCalendar=Mon..Fri 09:00
OnCalendar=Mon..Fri 17:00
```

Beispiele für andere Zeiten:

```ini
# Nur einmal täglich nach Börsenschluss (Xetra schließt 17:30)
OnCalendar=Mon..Fri 18:00

# Stündlich während der Handelszeit
OnCalendar=Mon..Fri 09..17:00

# Auch am Wochenende (sinnloser für Aktien, aber z.B. für Kryptowährungen)
OnCalendar=*-*-* 09,17:00
```

Das `Mon..Fri` schränkt auf Werktage ein – an Wochenenden wäre die Prüfung sinnlos, da die Börsen geschlossen sind.

Nach Änderung des Timers:
```bash
sudo systemctl daemon-reload
sudo systemctl restart sma250-monitor.timer
```

### ntfy-Authentifizierung (optional)

Bei einem self-hosted ntfy-Server mit Authentifizierung:

```python
NTFY_TOKEN = "tk_xxxxxxxxxxxx"  # Bearer-Token aus ntfy-Konfig
```

Andernfalls leer lassen.

## Bedienung

```bash
# Manueller Testlauf (als Service-User)
sudo -u sma250 /opt/sma250-monitor/venv/bin/python /opt/sma250-monitor/sma250_monitor.py

# Service einmalig manuell triggern
sudo systemctl start sma250-monitor.service

# Timer-Status und nächste Ausführung anzeigen
systemctl status sma250-monitor.timer
systemctl list-timers sma250-monitor.timer

# Logs in Echtzeit verfolgen
journalctl -u sma250-monitor.service -f

# Aktuellen State anzeigen
cat /var/lib/sma250-monitor/state.json

# State zurücksetzen (z.B. nach Ticker-Wechsel)
sudo rm /var/lib/sma250-monitor/state.json
```

## Datenquelle

`yfinance` greift auf öffentliche Yahoo-Finance-Endpunkte zu. Die Bibliothek ist nicht offiziell von Yahoo supportet, aber in der Praxis stabil. Bei API-Änderungen seitens Yahoo kann ein Update nötig werden:

```bash
sudo /opt/sma250-monitor/venv/bin/pip install --upgrade yfinance
```


## Sicherheit

Der systemd-Service läuft als unprivilegierter User `sma250` mit restriktiver Sandbox:

- `NoNewPrivileges=true` – kein Privilege Escalation möglich
- `ProtectSystem=strict` – Dateisystem nahezu vollständig read-only
- `ProtectHome=true` – kein Zugriff auf Home-Verzeichnisse
- `ReadWritePaths=/var/lib/sma250-monitor` – schreibender Zugriff nur auf das State-Verzeichnis
- `RestrictAddressFamilies=AF_INET AF_INET6` – nur IPv4/IPv6, keine Unix-Sockets etc.
- `MemoryDenyWriteExecute=true` – keine W^X-Verletzungen möglich

## Troubleshooting

### Verbindungsfehler "Failed to connect to fc.yahoo.com"

Häufige Ursachen:
- DNS im Container nicht konfiguriert: `cat /etc/resolv.conf` prüfen
- Default-Gateway fehlt: `ip route` prüfen
- IPv6-only-Auflösung ohne IPv6-Konnektivität – ggf. IPv4 erzwingen

### "Zu wenig Handelstage für SMA250"

Der Ticker hat noch keine 250 Tage Historie oder Yahoo liefert lückenhafte Daten. Andere Ticker-Variante versuchen oder `period_days` erhöhen.

### Keine Benachrichtigung trotz Kreuzung

- State-Datei prüfen: `cat /var/lib/sma250-monitor/state.json`
- Liegt der Kurs in der Hysteresezone (Status `NEUTRAL`)? Dann ist das Verhalten korrekt.
- ntfy-Topic in App und Script identisch?

## Disclaimer

Dieses Tool dient ausschließlich der technischen Signalgenerierung und stellt **keine Anlageberatung** dar. Trendfolge-Strategien wie SMA250 sind keine Garantie für positive Renditen und können in Seitwärtsphasen schlechter abschneiden als Buy-and-Hold. Die Nutzung erfolgt auf eigenes Risiko.

## Lizenz

MIT License – siehe [LICENSE](LICENSE).

## Beiträge

Pull Requests sind willkommen. Für größere Änderungen bitte vorher ein Issue eröffnen, um die Idee zu diskutieren.
