# Panduan Setup — WSL Ubuntu sebagai Server (Cloudflare Tunnel + SQLite)

## Arsitektur Baru
```
Tamu (Telegram / Browser)
        ↓
Cloudflare Tunnel (HTTPS gratis, URL tetap)
        ↓
FastAPI + SQLite (jalan di WSL Ubuntu laptop Anda)
        ↓
Notifikasi → Telegram Admin
```

---

## LANGKAH 1 — Buka Terminal WSL Ubuntu

Di Windows, buka **Ubuntu** dari Start Menu (bukan PowerShell/CMD).
Lalu masuk ke folder project:

```bash
cd /mnt/c/Users/user/Desktop/SGO_Nexa
```

---

## LANGKAH 2 — Buat Virtual Environment & Install Dependencies

```bash
# Buat venv di home WSL (lebih cepat dari /mnt/c)
python3 -m venv ~/venv_sgo

# Aktifkan venv
source ~/venv_sgo/bin/activate

# Install semua dependencies
pip install -r requirements.txt
```

Setelah ini prompt akan berubah jadi `(venv_sgo) user@...`

> **Tip:** Setiap kali buka terminal WSL baru, jalankan dulu:
> `source ~/venv_sgo/bin/activate`

---

## LANGKAH 3 — Download & Install cloudflared di WSL

```bash
# Download cloudflared untuk Linux
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O cloudflared

# Beri izin eksekusi
chmod +x cloudflared

# Pindah ke /usr/local/bin agar bisa dipakai dari mana saja
sudo mv cloudflared /usr/local/bin/

# Verifikasi
cloudflared --version
```

---

## LANGKAH 4 — Jalankan Cloudflare Tunnel (Tanpa Login, Gratis)

Buka **terminal WSL baru** (tab/window baru), lalu:

```bash
cloudflared tunnel --url http://localhost:8000
```

Tunggu beberapa detik, akan muncul output seperti:
```
+--------------------------------------------------------------------------------------------+
|  Your quick Tunnel has been created! Visit it at (it may take some time to be reachable):  |
|  https://abc-def-ghi-jkl.trycloudflare.com                                                 |
+--------------------------------------------------------------------------------------------+
```

**Salin URL tersebut** (contoh: `https://abc-def-ghi-jkl.trycloudflare.com`)

---

## LANGKAH 5 — Update File .env

Buka file `.env` di folder project, ganti `BASE_URL`:

```env
API_TOKEN=token_bot_telegram_anda
ADMIN_ID=id_telegram_anda
BASE_URL=https://abc-def-ghi-jkl.trycloudflare.com
```

---

## LANGKAH 6 — Migrasi Data Menu (Opsional)

Jika ada data menu lama yang ingin dipindahkan:

1. Buka file `migrate_from_supabase.py`
2. Isi data menu di variabel `MENU_DATA`
3. Jalankan:
```bash
source ~/venv_sgo/bin/activate
cd /mnt/c/Users/user/Desktop/SGO_Nexa
python migrate_from_supabase.py
```

Atau bisa langsung tambah menu baru lewat Dashboard setelah server jalan.

---

## LANGKAH 7 — Jalankan Server FastAPI

Di terminal WSL (yang sudah aktif venv):

```bash
source ~/venv_sgo/bin/activate
cd /mnt/c/Users/user/Desktop/SGO_Nexa
python main.py
```

Akan muncul:
```
✅ Database SQLite siap: .../restaurant.db
✅ Webhook set to https://abc-def-ghi-jkl.trycloudflare.com/webhook
INFO:     Uvicorn running on http://0.0.0.0:8000
```

---

## LANGKAH 8 — Set Webhook Telegram (jika belum otomatis)

Buka browser dan akses:
```
https://abc-def-ghi-jkl.trycloudflare.com/set_webhook
```

Jika berhasil:
```json
{"status": "ok", "message": "Webhook set to https://..."}
```

---

## LANGKAH 9 — Test Sistem

| Test | URL |
|------|-----|
| Menu pelanggan (browser) | `https://url-tunnel.trycloudflare.com` |
| Menu via Telegram | Buka bot → `/start` → klik tombol |
| Dashboard admin | `https://url-tunnel.trycloudflare.com/dashboard` |
| Laporan penjualan | `https://url-tunnel.trycloudflare.com/sales-report` |

---

## Cara Pakai Setiap Hari

Setiap kali mau menjalankan sistem, buka **2 terminal WSL**:

**Terminal 1 — Tunnel:**
```bash
cloudflared tunnel --url http://localhost:8000
```
*(catat URL baru jika berubah, lalu update .env dan /set_webhook)*

**Terminal 2 — Server:**
```bash
source ~/venv_sgo/bin/activate
cd /mnt/c/Users/user/Desktop/SGO_Nexa
python main.py
```

---

## Struktur Database SQLite

File database tersimpan di: `restaurant.db` (di folder project)

**Tabel `menu_items`:**
- id, name, category, cuisine, price, description, image_url, is_available, created_at

**Tabel `orders`:**
- id, customer_name, table_number, items (JSON), total_price, note, status, created_at

---

## Tips

- **Backup database:** Cukup copy file `restaurant.db`
- **Gambar menu:** Tersimpan di `static/images/menu/`
- **Jika URL tunnel berubah:** Update `BASE_URL` di `.env` lalu restart server dan akses `/set_webhook` lagi
- **Laptop harus nyala** selama restoran beroperasi

---

## Upgrade ke Produksi (Nanti)

Ketika siap untuk klien, tinggal:
1. Sewa VPS murah (~$5/bulan)
2. Upload semua file ke VPS
3. Pasang domain + SSL (Let's Encrypt gratis)
4. Jalankan dengan `systemd` agar otomatis start
5. Ganti SQLite dengan PostgreSQL jika traffic tinggi
