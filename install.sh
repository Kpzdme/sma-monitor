#!/bin/bash
#
# Installations-Script für SMA-Monitor
# Ausführen als root in einem frischen Debian/Ubuntu LXC-Container
#
set -euo pipefail

INSTALL_DIR="/opt/sma250-monitor"
STATE_DIR="/var/lib/sma250-monitor"
SERVICE_USER="sma250"

echo "==> Paket-Installation..."
apt-get update
apt-get install -y python3 python3-venv python3-pip

echo "==> Service-User anlegen..."
if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
    useradd --system --home-dir "$INSTALL_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
fi

echo "==> Verzeichnisse erstellen..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$STATE_DIR"

echo "==> Dateien kopieren (aus aktuellem Verzeichnis)..."
cp sma250_monitor.py "$INSTALL_DIR/"
cp requirements.txt "$INSTALL_DIR/"

echo "==> Python venv aufsetzen..."
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

echo "==> Rechte setzen..."
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
chown -R "$SERVICE_USER:$SERVICE_USER" "$STATE_DIR"
chmod 755 "$INSTALL_DIR/sma250_monitor.py"

echo "==> systemd-Units installieren..."
cp sma250-monitor.service /etc/systemd/system/
cp sma250-monitor.timer /etc/systemd/system/
systemctl daemon-reload

echo "==> Timer aktivieren..."
systemctl enable --now sma250-monitor.timer

echo ""
echo "========================================================"
echo "Installation abgeschlossen."
echo ""
echo "WICHTIG: Passe vor dem ersten Lauf NTFY_TOPIC in der Datei an:"
echo "  $INSTALL_DIR/sma250_monitor.py"
echo ""
echo "Testlauf:     sudo -u $SERVICE_USER $INSTALL_DIR/venv/bin/python $INSTALL_DIR/sma250_monitor.py"
echo "Timer-Status: systemctl status sma250-monitor.timer"
echo "Nächster Lauf: systemctl list-timers sma250-monitor.timer"
echo "Logs:         journalctl -u sma250-monitor.service -f"
echo "========================================================"
