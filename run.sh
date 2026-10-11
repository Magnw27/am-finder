#!/usr/bin/env bash
# Kelola layanan am-finder di perangkat ini (localhost / LAN).
#   ./run.sh start     -> jalankan di background (port 8000)
#   ./run.sh stop      -> hentikan
#   ./run.sh restart   -> mulai ulang
#   ./run.sh status    -> cek status
#   ./run.sh logs      -> ikuti log
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
PIDFILE="$DIR/.amfinder.pid"
LOGFILE="$DIR/.amfinder.log"

is_running() {
  [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null
}

start() {
  if is_running; then
    echo "am-finder sudah berjalan (PID $(cat "$PIDFILE"))."
    return 0
  fi
  cd "$DIR"
  nohup python3 -u -m amfinder.server --host "$HOST" --port "$PORT" \
    >"$LOGFILE" 2>&1 &
  echo $! >"$PIDFILE"
  sleep 1.5
  if is_running; then
    echo "am-finder berjalan (PID $(cat "$PIDFILE"))."
    echo "  Local : http://127.0.0.1:$PORT"
    echo "  LAN   : http://$(hostname -I 2>/dev/null | awk '{print $1}'):$PORT"
    echo "  Log   : $LOGFILE"
  else
    echo "Gagal menjalankan. Lihat log: $LOGFILE"
    tail -n 20 "$LOGFILE" || true
    return 1
  fi
}

stop() {
  if is_running; then
    kill "$(cat "$PIDFILE")" 2>/dev/null || true
    rm -f "$PIDFILE"
    echo "am-finder dihentikan."
  else
    echo "am-finder tidak sedang berjalan."
  fi
}

status() {
  if is_running; then
    echo "am-finder BERJALAN (PID $(cat "$PIDFILE")) di http://$HOST:$PORT"
  else
    echo "am-finder TIDAK berjalan."
    return 1
  fi
}

case "${1:-start}" in
  start) start ;;
  stop) stop ;;
  restart) stop; sleep 1; start ;;
  status) status ;;
  logs) tail -f "$LOGFILE" ;;
  *) echo "Gunakan: $0 {start|stop|restart|status|logs}"; exit 1 ;;
esac