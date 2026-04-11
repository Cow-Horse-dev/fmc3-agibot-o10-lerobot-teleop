#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="$SCRIPT_DIR/HDService"
LOCAL_PROTOBUF_DIR="$SERVICE_DIR/.local_deps/usr/lib/x86_64-linux-gnu"
PORT="${HD_WS_PORT:-7789}"
UDP_TARGET="${HD_UDP_TARGET:-127.0.0.1:7777}"
DATA_STREAM_FILE="$SERVICE_DIR/log/data_stream.bin"

if [ ! -x "$SERVICE_DIR/HDService" ]; then
  chmod +x "$SERVICE_DIR/HDService"
fi

if [ ! -e "$LOCAL_PROTOBUF_DIR/libprotobuf.so.23" ]; then
  echo "Missing local protobuf dependency in: $LOCAL_PROTOBUF_DIR" >&2
  echo "Expected file: $LOCAL_PROTOBUF_DIR/libprotobuf.so.23" >&2
  exit 1
fi

export LD_LIBRARY_PATH="$LOCAL_PROTOBUF_DIR:${LD_LIBRARY_PATH:-}"

python3 - "$DATA_STREAM_FILE" "$UDP_TARGET" <<'PY'
from pathlib import Path
import struct
import sys

path = Path(sys.argv[1])
target = sys.argv[2].encode("utf-8")
default_prefix = bytes.fromhex("080118ffffffffffffffffff012878")

prefix = default_prefix
if path.exists():
    data = path.read_bytes()
    if len(data) >= 4:
        payload = data[4:]
        for idx in range(len(payload) - 1):
            if payload[idx] != 0x32:
                continue
            field_len = payload[idx + 1]
            if idx + 2 + field_len == len(payload):
                prefix = payload[:idx]
                break

payload = prefix + b"\x32" + bytes([len(target)]) + target
path.parent.mkdir(parents=True, exist_ok=True)
path.write_bytes(struct.pack("<I", len(payload)) + payload)
print(f"HDService UDP target set to {target.decode('utf-8')}")
PY

if ss -ltnp 2>/dev/null | grep -q ":$PORT "; then
  echo "HDService appears to be already running on port $PORT."
  echo "If you want to restart it, run ./stop_hdservice.sh first."
  exit 0
fi

cd "$SERVICE_DIR"
exec ./HDService
