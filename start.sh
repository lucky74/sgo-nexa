#!/bin/bash
# Script start server SGO — otomatis update .env dan tampilkan URL

cd /mnt/c/Users/user/Desktop/SGO_Nexa
source ~/venv_sgo/bin/activate

# Kill proses lama jika ada
pkill -f "python main.py" 2>/dev/null
sleep 1

echo "🚀 Memulai Cloudflare Tunnel..."

# Jalankan cloudflared di background, simpan output ke file temp
TUNNEL_LOG=$(mktemp)
cloudflared tunnel --url http://localhost:8000 > "$TUNNEL_LOG" 2>&1 &
TUNNEL_PID=$!

# Tunggu URL muncul (max 15 detik)
echo "⏳ Menunggu URL tunnel..."
TUNNEL_URL=""
for i in $(seq 1 30); do
    TUNNEL_URL=$(grep -o 'https://[a-zA-Z0-9._-]*\.trycloudflare\.com' "$TUNNEL_LOG" | head -1)
    if [ -n "$TUNNEL_URL" ]; then
        break
    fi
    sleep 0.5
done

if [ -z "$TUNNEL_URL" ]; then
    echo "❌ Gagal mendapatkan URL tunnel. Cek cloudflared."
    kill $TUNNEL_PID 2>/dev/null
    exit 1
fi

# Ambil nama restoran dari database secara otomatis
OUTLET_UTAMA_NAME=$(python3 -c "
import sqlite3
try:
    conn = sqlite3.connect('/mnt/c/Users/user/Desktop/SGO_Nexa/restaurant.db')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(\"SELECT value FROM settings WHERE key='restaurant_name'\")
    row = cur.fetchone()
    conn.close()
    print(row['value'] if row else 'Outlet Utama')
except:
    print('Outlet Utama')
" 2>/dev/null)

# Ambil semua outlet dari master DB
OUTLETS_INFO=$(python3 -c "
import sqlite3
try:
    conn = sqlite3.connect('/mnt/c/Users/user/Desktop/SGO_Nexa/master.db')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute('SELECT id, name FROM outlets WHERE is_active=1 ORDER BY id')
    rows = cur.fetchall()
    conn.close()
    for r in rows:
        print(f\"{r['id']}|{r['name']}\")
except:
    pass
" 2>/dev/null)

echo ""
echo "✅ URL Tunnel Aktif:"
echo "   $TUNNEL_URL"
echo ""
echo "📌 Outlet Utama ($OUTLET_UTAMA_NAME):"
echo "   Login      : $TUNNEL_URL/login"
echo "   Dashboard  : $TUNNEL_URL/dashboard"
echo "   Pesanan    : $TUNNEL_URL/orders"
echo "   Laporan    : $TUNNEL_URL/sales-report"
echo "   Pengaturan : $TUNNEL_URL/settings"
echo ""

# Tampilkan semua outlet dari database
if [ -n "$OUTLETS_INFO" ]; then
    while IFS='|' read -r outlet_id outlet_name; do
        echo "📌 Outlet $outlet_id ($outlet_name):"
        echo "   Login      : $TUNNEL_URL/outlet/$outlet_id/login"
        echo "   Dashboard  : $TUNNEL_URL/outlet/$outlet_id/dashboard"
        echo "   Pesanan    : $TUNNEL_URL/outlet/$outlet_id/orders"
        echo "   Laporan    : $TUNNEL_URL/outlet/$outlet_id/sales-report"
        echo ""
    done <<< "$OUTLETS_INFO"
fi

echo "📌 Owner Dashboard:"
echo "   Login      : $TUNNEL_URL/owner/login"
echo ""

# Update .env dengan URL baru
sed -i "s|BASE_URL=.*|BASE_URL=$TUNNEL_URL|" .env
echo "✅ .env diupdate: BASE_URL=$TUNNEL_URL"
echo ""

# Jalankan server
echo "🟢 Menjalankan server..."
python main.py &
SERVER_PID=$!

# Tunggu server siap (max 15 detik)
echo "⏳ Menunggu server siap..."
for i in $(seq 1 30); do
    if curl -s http://localhost:8000/set_webhook > /dev/null 2>&1; then
        break
    fi
    sleep 0.5
done

# Reset webhook semua bot setelah server siap
sleep 2
curl -s "$TUNNEL_URL/set_webhook" > /dev/null 2>&1
echo "✅ Webhook bot utama direset"

curl -s "$TUNNEL_URL/set_outlet_webhooks" > /dev/null 2>&1
echo "✅ Webhook outlet direset"

echo ""
echo "⚠️  PENTING: Setelah server jalan, minta pelanggan ketik /start"
echo "   ulang di bot Telegram agar mendapat URL terbaru."
echo ""

# Tunggu server selesai
wait $SERVER_PID
