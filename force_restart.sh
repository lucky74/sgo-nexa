#!/bin/bash
echo "=== Kill semua proses python/uvicorn ==="
pkill -f "python main.py" 2>/dev/null
pkill -f "uvicorn main" 2>/dev/null
pkill -f "cloudflared" 2>/dev/null
sleep 2

echo "=== Cek port 8000 ==="
ss -tlnp | grep 8000 && echo "Port masih dipakai!" || echo "Port 8000 bebas ✅"

echo ""
echo "=== Mulai ulang server ==="
cd /mnt/c/Users/user/Desktop/SGO_Nexa
source ~/venv_sgo/bin/activate
bash start.sh
