#!/usr/bin/env python3
"""
SMA250-Monitor für MSCI World ETF (GB00BJDQQQ59 / iShares Core MSCI World UCITS ETF)
Prüft den aktuellen Kurs gegen die 250-Tage-Linie und sendet bei Statuswechsel
eine Benachrichtigung über ntfy.

Author: Kpzdme
"""

import base64
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
import yfinance as yf

# ============================================================
# KONFIGURATION
# ============================================================
# Ticker: ^990100-USD-STRD (https://finance.yahoo.com/quote/%5E990100-USD-STRD/) MSCI World Punkteindex
# Alternativ: EUNL.DE (Xetra, EUR) – empfohlen für deutschen Markt
TICKER = "^990100-USD-STRD"

# ntfy-Konfiguration
# Bei self-hosted ntfy: eigene URL eintragen, z.B. "https://ntfy.dein-domain.de"
NTFY_SERVER = "https://ntfy.sh"
NTFY_TOPIC = "DEIN_SECRET"  # Hier eine Zufällige Zeichenkette (z.B. via openssl rand -hex 16) erfassen. Diese brauchst du dann auch in der App
NTFY_TOKEN = ""  # nur bei Auth nötig, sonst leer lassen

# SMA-Parameter
SMA_PERIOD = 250 # Tage
HYSTERESIS_PCT = 1.0  # Pufferzone: ±1 % um SMA250 → kein Trigger (gegen Whipsaws)

# State-Datei (persistiert den letzten bekannten Zustand)
STATE_FILE = Path("/var/lib/sma250-monitor/state.json")

# Logging
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


# ============================================================
# STATE-HANDLING
# ============================================================
def load_state() -> dict:
    """Lädt den letzten bekannten Status aus der State-Datei."""
    if not STATE_FILE.exists():
        return {"last_status": "UNKNOWN", "last_check": None, "last_price": None, "last_sma": None}
    try:
        with STATE_FILE.open("r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.warning(f"State-Datei konnte nicht gelesen werden: {e}. Starte mit UNKNOWN.")
        return {"last_status": "UNKNOWN", "last_check": None, "last_price": None, "last_sma": None}
 
 
def save_state(state: dict) -> None:
    """Speichert den aktuellen Status persistent."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with STATE_FILE.open("w") as f:
        json.dump(state, f, indent=2)
 
 
# ============================================================
# DATENABRUF & BERECHNUNG
# ============================================================
def fetch_price_data(ticker: str, period_days: int = 300) -> tuple[float, float]:
    """
    Ruft historische Kursdaten von Yahoo Finance ab und berechnet:
    - aktueller Schlusskurs
    - SMA250 (Simple Moving Average über die letzten 250 Handelstage)
 
    Returns: (current_price, sma250)
    """
    log.info(f"Rufe Kursdaten für {ticker} ab...")
    data = yf.Ticker(ticker).history(period=f"{period_days}d", interval="1d")
 
    if data.empty:
        raise RuntimeError(f"Keine Daten für Ticker {ticker} erhalten.")
 
    closes = data["Close"].dropna()
    if len(closes) < SMA_PERIOD:
        raise RuntimeError(
            f"Zu wenig Handelstage für SMA{SMA_PERIOD}: nur {len(closes)} verfügbar."
        )
 
    current_price = float(closes.iloc[-1])
    sma250 = float(closes.tail(SMA_PERIOD).mean())
 
    log.info(f"Aktueller Kurs: {current_price:.2f} | SMA{SMA_PERIOD}: {sma250:.2f}")
    return current_price, sma250
 
 
def determine_status(price: float, sma: float, hysteresis_pct: float) -> str:
    """
    Ermittelt den Status unter Berücksichtigung einer Hysteresezone.
    Returns: "ABOVE", "BELOW" oder "NEUTRAL" (innerhalb der Pufferzone)
    """
    upper_bound = sma * (1 + hysteresis_pct / 100)
    lower_bound = sma * (1 - hysteresis_pct / 100)
 
    if price > upper_bound:
        return "ABOVE"
    elif price < lower_bound:
        return "BELOW"
    else:
        return "NEUTRAL"
 
 
# ============================================================
# BENACHRICHTIGUNG
# ============================================================
def send_ntfy_notification(title: str, message: str, priority: str = "default", tags: str = "") -> None:
    """Sendet eine Push-Notification über ntfy."""
    url = f"{NTFY_SERVER}/{NTFY_TOPIC}"
 
    # HTTP-Header müssen latin-1-kompatibel sein. Für Unicode-Titel (z.B. Emojis)
    # nutzt ntfy RFC 2047 Encoded-Word-Syntax: =?UTF-8?B?<base64>?=
    title_b64 = base64.b64encode(title.encode("utf-8")).decode("ascii")
    encoded_title = f"=?UTF-8?B?{title_b64}?="
 
    headers = {
        "Title": encoded_title,
        "Priority": priority,
        "Tags": tags,
    }
    if NTFY_TOKEN:
        headers["Authorization"] = f"Bearer {NTFY_TOKEN}"
 
    try:
        response = requests.post(url, data=message.encode("utf-8"), headers=headers, timeout=10)
        response.raise_for_status()
        log.info(f"ntfy-Benachrichtigung gesendet: {title}")
    except requests.RequestException as e:
        log.error(f"ntfy-Benachrichtigung fehlgeschlagen: {e}")
 
 
# ============================================================
# HAUPTLOGIK
# ============================================================
def main() -> int:
    try:
        price, sma = fetch_price_data(TICKER)
    except Exception as e:
        log.error(f"Datenabruf fehlgeschlagen: {e}")
        send_ntfy_notification(
            title="⚠️ SMA250-Monitor: Fehler",
            message=f"Datenabruf für {TICKER} fehlgeschlagen:\n{e}",
            priority="high",
            tags="warning",
        )
        return 1
 
    current_status = determine_status(price, sma, HYSTERESIS_PCT)
    deviation_pct = (price - sma) / sma * 100
 
    state = load_state()
    last_status = state.get("last_status", "UNKNOWN")
 
    log.info(f"Status: aktuell={current_status} | vorher={last_status} | Abweichung={deviation_pct:+.2f}%")
 
    # Statuswechsel-Logik:
    # Trigger nur bei Wechsel ABOVE <-> BELOW
    # NEUTRAL wird als Zwischenzustand ignoriert (keine Benachrichtigung, kein State-Update)
    status_changed = False
    if current_status in ("ABOVE", "BELOW") and last_status in ("ABOVE", "BELOW", "UNKNOWN"):
        if current_status != last_status:
            status_changed = True
 
    if status_changed:
        if current_status == "ABOVE":
            title = "📈 MSCI World: SMA250 ÜBERSCHRITTEN"
            message = (
                f"Der MSCI World ETF hat die 250-Tage-Linie überschritten.\n\n"
                f"Kurs: {price:.2f}\n"
                f"SMA250: {sma:.2f}\n"
                f"Abweichung: {deviation_pct:+.2f} %\n\n"
                f"→ Signal: Einstieg in Leverage-ETF erwägen."
            )
            tags = "chart_with_upwards_trend,green_circle"
        else:  # BELOW
            title = "📉 MSCI World: SMA250 UNTERSCHRITTEN"
            message = (
                f"Der MSCI World ETF hat die 250-Tage-Linie unterschritten.\n\n"
                f"Kurs: {price:.2f}\n"
                f"SMA250: {sma:.2f}\n"
                f"Abweichung: {deviation_pct:+.2f} %\n\n"
                f"→ Signal: Ausstieg aus Leverage-ETF erwägen."
            )
            tags = "chart_with_downwards_trend,red_circle"
 
        send_ntfy_notification(title=title, message=message, priority="high", tags=tags)
 
    # State aktualisieren (nur bei klaren Zuständen, NEUTRAL ignorieren)
    if current_status in ("ABOVE", "BELOW"):
        save_state({
            "last_status": current_status,
            "last_check": datetime.now(timezone.utc).isoformat(),
            "last_price": round(price, 2),
            "last_sma": round(sma, 2),
            "last_deviation_pct": round(deviation_pct, 2),
        })
 
    return 0
 
 
if __name__ == "__main__":
    sys.exit(main())
 
