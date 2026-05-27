# Buku Panduan SGO
## Smart Guest Order — Sistem POS Restoran via Telegram Bot

---

**Dikembangkan oleh:**
**Sentra Guest OS**
Lucky Zamaludin Malik
📱 WhatsApp: 089639541438
📧 Email: sentraguest.os@gmail.com
© 2026 Sentra Guest OS. All rights reserved.

**Versi:** 2.1
**Tanggal:** 2026

---

## Daftar Isi

1. Pengenalan Sistem
2. Cara Memulai Server
3. Login Admin & Owner
4. Manajemen Menu
5. Manajemen Pesanan
6. Sistem Delivery & Kurir
7. Voucher & Promo
8. Stok & Inventory
9. Rating & Review
10. Riwayat Pelanggan
11. Laporan Penjualan
12. Laporan Harian Otomatis
13. Backup & Reset Database
14. Pengaturan Sistem
15. Panduan untuk Pembeli
16. Troubleshooting

---

## BAB 1 — Pengenalan Sistem

SGO adalah sistem POS (Point of Sale) untuk restoran yang menggunakan Telegram Bot sebagai media pemesanan. Sistem terdiri dari dua bagian utama:

**1. Bot Telegram (untuk Pembeli)**
Pembeli membuka bot Telegram restoran, memilih menu, dan melakukan pemesanan langsung dari smartphone.

**2. Dashboard Web (untuk Admin & Owner)**
Admin mengelola menu, pesanan, kurir, dan pengaturan melalui browser web. Owner memantau laporan penjualan.

### Alur Pemesanan Dine-in
```
Pembeli buka bot → Pilih "Makan di Tempat" → Isi nama & nomor meja
→ Pilih menu → Checkout → Bayar QRIS → Pesanan masuk ke admin
→ Admin proses → Status update → Pembeli dapat notifikasi
→ Pesanan disajikan → Pembeli beri rating
```

### Alur Pemesanan Delivery
```
Pembeli buka bot → Pilih "Pesan Antar" → Isi nama, WhatsApp, alamat
→ GPS otomatis hitung ongkir → Pilih menu → Checkout → Bayar QRIS
→ Pesanan masuk ke admin → Admin assign kurir → Kurir dapat link konfirmasi
→ Kurir antar → Konfirmasi selesai → Pembeli dapat notifikasi selesai
```

---

## BAB 2 — Cara Memulai Server

### Langkah 1: Buka Terminal WSL
Di Windows, buka **PowerShell** atau **Command Prompt**, lalu ketik:
```
wsl
```

### Langkah 2: Jalankan Script Start
```bash
bash /mnt/c/Users/user/Desktop/SGO_Nexa/start.sh
```

### Langkah 3: Catat URL Tunnel
Setelah script berjalan, akan muncul:
```
✅ URL Tunnel Aktif:
   https://xxxx-xxxx.trycloudflare.com

📌 Halaman Admin:
   Dashboard  : https://xxxx-xxxx.trycloudflare.com/dashboard
   Pesanan    : https://xxxx-xxxx.trycloudflare.com/orders
   ...
```

Catat URL ini — digunakan untuk mengakses dashboard admin.

### Langkah 4: Update Webhook Bot (jika perlu)
Jika bot tidak merespons setelah restart, buka browser dan akses:
```
https://xxxx-xxxx.trycloudflare.com/set_webhook
```

### Catatan Penting
> ⚠️ URL tunnel **berubah setiap kali** server di-restart. Selalu gunakan URL terbaru dari output script start.

---

## BAB 3 — Login Admin & Owner

### Akses Halaman Login
Buka browser, ketik URL dashboard:
```
https://xxxx-xxxx.trycloudflare.com/dashboard
```
Akan otomatis redirect ke halaman login.

### Kredensial Default

| Username | Password | Akses |
|---|---|---|
| `admin` | `admin123` | Semua halaman |
| `owner` | `owner123` | Laporan penjualan saja |

> ⚠️ **Segera ganti password** setelah pertama kali login!

### Cara Ganti Password
1. Login sebagai **admin**
2. Buka menu **Pengaturan**
3. Scroll ke bawah → section **"Ganti Password Login"**
4. Pilih user (admin/owner), isi password baru, konfirmasi
5. Klik **Ganti Password**

### Perbedaan Akses Admin vs Owner

**Admin dapat mengakses:**
- Manajemen Menu
- Laporan Penjualan
- Manajemen Pesanan
- Manajemen Kurir
- Voucher & Promo
- Riwayat Pelanggan
- Pengaturan (termasuk reset database)

**Owner hanya dapat mengakses:**
- Laporan Penjualan (read-only)

---

## BAB 4 — Manajemen Menu

### Membuka Dashboard Menu
Klik **"Manajemen Menu"** di sidebar kiri.

### Menambah Menu Baru
1. Klik tombol **"+ Tambah Menu"** (kanan atas)
2. Isi form:
   - **Nama Menu** — wajib diisi
   - **Kategori** — pilih dari dropdown (Appetizer, Main Course, dll)
   - **Cuisine** — asal masakan (Indonesian, Western, dll)
   - **Harga** — dalam Rupiah, tanpa titik/koma
   - **Deskripsi** — opsional, tampil di bawah nama menu
   - **Foto Produk** — wajib, format JPG/PNG
3. Klik **"Simpan Menu"**

### Mengedit Menu
1. Klik ikon pensil (🖊️) di kolom Aksi
2. Ubah data yang diperlukan
3. Klik **"Simpan Perubahan"**

### Menonaktifkan Menu
Klik ikon mata (👁️) di kolom Aksi. Menu nonaktif tidak akan muncul di bot pembeli.

### Menghapus Menu
Klik ikon tempat sampah (🗑️) → konfirmasi hapus.

### Mengatur Stok Menu
1. Klik ikon kotak (📦) di kolom Aksi
2. Isi **Jumlah Stok** (isi `-1` untuk stok tidak terbatas)
3. Isi **Batas Peringatan** — sistem kirim notifikasi jika stok di bawah angka ini
4. Klik **Simpan**

> Jika stok mencapai 0, menu otomatis dinonaktifkan dan admin mendapat notifikasi Telegram.

---

## BAB 5 — Manajemen Pesanan

### Membuka Halaman Pesanan
Klik **"Manajemen Pesanan"** di sidebar.

### Memahami Status Pesanan

| Status | Arti |
|---|---|
| ⏳ Pending | Pesanan baru masuk, belum diproses |
| 🍳 Diproses | Dapur sedang menyiapkan |
| 🚴 Dikirim | Kurir sedang mengantar (delivery) |
| ✅ Disajikan | Makanan sudah disajikan (dine-in) |
| ✅ Selesai | Pesanan selesai (delivery) |
| ❌ Dibatalkan | Pesanan dibatalkan |

### Mengubah Status Pesanan
1. Temukan pesanan di tabel
2. Klik dropdown di kolom **"Ubah Status"**
3. Pilih status baru
4. Pembeli otomatis mendapat notifikasi Telegram

### Assign Kurir (untuk Delivery)
1. Ubah status pesanan ke **"Diproses"**
2. Tombol **"Assign Kurir"** muncul di bawah dropdown
3. Klik → pilih kurir dari daftar
4. Link konfirmasi otomatis dikirim ke WhatsApp kurir
5. Pembeli mendapat notifikasi nama & nomor WhatsApp kurir

### Filter Pesanan
- Gunakan filter tanggal untuk melihat pesanan hari tertentu
- Filter tipe: Semua / Dine-in / Delivery

---

## BAB 6 — Sistem Delivery & Kurir

### Menambah Kurir
1. Klik **"Manajemen Kurir"** di sidebar
2. Klik **"+ Tambah Kurir"**
3. Isi nama dan nomor WhatsApp kurir
4. Klik **Simpan**

### Alur Pengiriman
1. Pesanan delivery masuk → admin ubah status ke **Diproses**
2. Klik **Assign Kurir** → pilih kurir
3. Sistem generate link unik untuk kurir
4. Admin kirim link ke kurir via WhatsApp (tombol tersedia)
5. Kurir buka link → lihat detail pesanan + Google Maps
6. Kurir antar → klik **"Konfirmasi Sudah Dikirim"**
7. Pembeli dan admin otomatis dapat notifikasi selesai

### Pengaturan Tarif Ongkir
Buka **Pengaturan** → section **"Tarif Ongkos Kirim"**:
- **Biaya Minimum** — ongkir untuk jarak minimum
- **Jarak Minimum** — jarak yang dikenakan biaya minimum
- **Tarif per km** — biaya tambahan per km setelah jarak minimum
- **Jarak Maksimal** — batas jangkauan pengiriman

---

## BAB 7 — Voucher & Promo

### Membuat Voucher
1. Klik **"Voucher & Promo"** di sidebar
2. Klik **"+ Buat Voucher"**
3. Isi form:
   - **Kode Voucher** — contoh: DISKON10 (otomatis huruf kapital)
   - **Tipe Diskon** — Persen (%) atau Nominal (Rp)
   - **Nilai Diskon** — angka diskon
   - **Minimum Order** — minimum belanja untuk pakai voucher (0 = tidak ada minimum)
   - **Maks. Penggunaan** — batas pemakaian (-1 = tidak terbatas)
   - **Berlaku Hingga** — tanggal kadaluarsa (kosongkan jika tidak ada)
4. Klik **Simpan Voucher**

### Cara Pembeli Pakai Voucher
1. Pembeli tambah item ke keranjang
2. Klik Checkout
3. Di halaman pembayaran, ada kolom **"🎟️ Kode Voucher"**
4. Ketik kode → klik **Terapkan**
5. Diskon otomatis terpotong dari total

### Menonaktifkan/Menghapus Voucher
- Klik ikon mata untuk aktif/nonaktif
- Klik ikon tempat sampah untuk hapus permanen

---

## BAB 8 — Stok & Inventory

### Cara Kerja Stok
- Setiap kali ada pesanan masuk, stok otomatis berkurang
- Jika stok = 0, menu otomatis dinonaktifkan
- Admin mendapat notifikasi Telegram jika stok menipis atau habis
- Stok = -1 berarti tidak terbatas (unlimited)

### Update Stok Manual
1. Di halaman **Manajemen Menu**
2. Klik ikon kotak (📦) di baris menu yang ingin diupdate
3. Isi jumlah stok baru
4. Klik **Simpan**

> Jika stok diisi ulang (> 0), menu yang sebelumnya nonaktif karena stok habis akan otomatis aktif kembali.

---

## BAB 9 — Rating & Review

### Cara Kerja Rating
1. Admin ubah status pesanan ke **"Disajikan"** atau **"Selesai"**
2. Bot otomatis kirim pesan ke pembeli dengan tombol bintang ⭐⭐⭐⭐⭐
3. Pembeli klik bintang untuk beri rating keseluruhan pesanan
4. Bot lanjut tanya rating per item menu yang dipesan
5. Admin mendapat notifikasi Telegram setiap ada rating masuk

### Melihat Rating di Dashboard
- Di halaman **Manajemen Menu**, kolom **Rating** menampilkan rata-rata bintang dan jumlah ulasan
- Di halaman menu pembeli, rating tampil di bawah nama menu

---

## BAB 10 — Riwayat Pelanggan

### Membuka Halaman Pelanggan
Klik **"Riwayat Pelanggan"** di sidebar.

### Informasi yang Tersedia
- Nama pelanggan + avatar inisial
- Badge status: ⭐ Setia (≥10x pesan), Regular (≥5x), Baru
- Total pesanan, dine-in, delivery
- Total belanja keseluruhan
- Menu favorit (3 teratas)
- Tanggal terakhir pesan

### Kirim Pesan Promo ke Pelanggan
1. Temukan pelanggan yang punya Telegram (ada tombol **Kirim**)
2. Klik tombol **Kirim**
3. Tulis pesan promo (contoh: kode voucher, info menu baru, ucapan terima kasih)
4. Klik **Kirim Pesan**
5. Pesan langsung masuk ke Telegram pelanggan atas nama restoran

---

## BAB 11 — Laporan Penjualan

### Membuka Laporan
Klik **"Laporan Penjualan"** di sidebar.

### Memilih Tanggal
Gunakan input tanggal di bagian atas untuk melihat laporan hari tertentu.

### Isi Laporan
- **Subtotal Penjualan** — total harga menu sebelum pajak/service
- **Service Charge** — jika diaktifkan di pengaturan
- **PBJT** — Pajak Barang dan Jasa Tertentu, jika diaktifkan
- **Total Revenue** — total pendapatan keseluruhan
- **Tabel per kategori** — rincian penjualan per menu

### Mencetak Laporan
Klik tombol **"🖨️ Cetak Laporan"** → browser membuka dialog print → pilih **Save as PDF** atau printer.

Laporan cetak sudah dilengkapi:
- Kop surat dengan nama restoran
- Kolom tanda tangan (Kasir & Manager)
- Nomor halaman dan tanggal cetak

---

## BAB 12 — Laporan Harian Otomatis

### Cara Kerja
Setiap hari pada jam yang dikonfigurasi (default: **22:00 WIB**), sistem otomatis mengirim ringkasan penjualan ke Telegram admin dan owner.

### Isi Laporan Harian
- Total pesanan hari ini
- Pesanan selesai, dibatalkan, dine-in, delivery
- Total pendapatan (termasuk tax & service)
- Perbandingan dengan kemarin (naik/turun)
- 3 menu terlaris hari ini

### Mengatur Jam Pengiriman
1. Buka **Pengaturan**
2. Section **"Ringkasan Harian Otomatis"**
3. Ubah jam dan menit
4. Aktifkan/nonaktifkan toggle
5. Klik **Simpan Pengaturan**

### Menambah Penerima Owner
1. Buka **Pengaturan**
2. Section **"Ringkasan Harian Otomatis"**
3. Isi **ID Telegram Owner** (dapatkan dari @userinfobot di Telegram)
4. Klik **Simpan Pengaturan**

### Test Kirim Laporan
Buka browser, akses:
```
https://xxxx-xxxx.trycloudflare.com/api/send-daily-report
```

---

## BAB 13 — Backup & Reset Database

### Backup Otomatis
Sistem otomatis backup database setiap hari jam **02:00 WIB**.
- File disimpan di folder `backups/` dengan nama `restaurant_YYYY-MM-DD.db`
- Backup lebih dari 30 hari otomatis dihapus
- Admin mendapat notifikasi Telegram setelah backup berhasil

### Backup Manual
1. Buka **Pengaturan**
2. Scroll ke bawah → section **"Backup & Reset Database"**
3. Klik **"Backup Sekarang"**
4. Konfirmasi file berhasil disimpan

### Melihat Daftar Backup
Klik **"Lihat Daftar Backup"** untuk melihat semua file backup yang tersimpan.

### Reset Data Pesanan
> ⚠️ **PERHATIAN:** Tindakan ini menghapus semua data pesanan secara permanen. Backup otomatis dibuat sebelum reset.

**Kapan perlu reset?**
Biasanya dilakukan setiap pagi sebelum restoran buka, setelah backup otomatis jam 02:00 sudah berjalan.

**Cara reset:**
1. Buka **Pengaturan**
2. Scroll ke bawah → section **"Backup & Reset Database"**
3. Klik **"Reset Data Pesanan"**
4. Ketik `RESET` (huruf kapital) di kolom konfirmasi
5. Klik **"Konfirmasi Reset"**

**Yang dihapus saat reset:**
- ✅ Data pesanan (orders)
- ✅ Rating & review
- ✅ Log stok

**Yang TIDAK dihapus:**
- ❌ Data menu
- ❌ Data kurir
- ❌ Voucher
- ❌ Pengaturan sistem
- ❌ Data pelanggan (tg_sessions)

---

## BAB 14 — Pengaturan Sistem

### Informasi Restaurant
- **Nama Restaurant** — tampil di semua halaman, bot, dan invoice

### Koordinat Restaurant
Digunakan untuk menghitung jarak delivery.
1. Klik **"Gunakan Lokasi Saya Sekarang"** untuk otomatis isi koordinat
2. Atau isi manual dari Google Maps (klik kanan → "What's here?")

### Tarif Ongkos Kirim
- **Biaya Minimum** — ongkir untuk jarak ≤ jarak minimum
- **Jarak Minimum** — contoh: 1 km
- **Tarif per km** — biaya tambahan per km
- **Jarak Maksimal** — batas pengiriman

**Contoh:** Biaya minimum Rp 5.000 untuk 1 km pertama, Rp 3.000/km setelahnya, maksimal 10 km.

### Tax & Service Charge
- Toggle **Service Charge** — aktif/nonaktif
- **Rate Service** — persentase (default 10%)
- Toggle **PBJT** — aktif/nonaktif
- **Rate PBJT** — persentase (default 11%)

> Jika dinonaktifkan, tax/service tidak muncul di invoice, bot pembeli, maupun laporan.

### Upload QRIS
1. Klik **"Pilih File QRIS"**
2. Pilih gambar QRIS dari komputer (JPG/PNG)
3. Klik **"Upload QRIS"**
4. QRIS baru langsung tampil di halaman pembayaran bot

---

## BAB 15 — Panduan untuk Pembeli

### Cara Memesan (Dine-in)
1. Buka bot Telegram restoran
2. Ketik `/start` atau klik tombol **Start**
3. Pilih **"🍽️ Makan di Tempat"**
4. Isi **Nama Pemesan** dan **Nomor Meja**
5. Pilih menu yang diinginkan (klik tombol +)
6. Tambahkan catatan per item jika perlu
7. Klik **"Checkout"** di bagian bawah
8. Cek rincian pesanan
9. Masukkan kode voucher jika ada
10. Scan QRIS untuk pembayaran
11. Klik **"SAYA SUDAH BAYAR ✓"**
12. Invoice otomatis dikirim ke Telegram

### Cara Memesan (Delivery)
1. Buka bot Telegram restoran
2. Pilih **"🛵 Pesan Antar (Online)"**
3. Isi **Nama**, **Nomor WhatsApp**, dan **Alamat Pengiriman**
4. Klik **"Gunakan Lokasi GPS Saya"** untuk deteksi otomatis
5. Ongkos kirim otomatis terhitung
6. Pilih menu → Checkout → Bayar QRIS
7. Tunggu konfirmasi dari restoran
8. Kurir akan menghubungi via WhatsApp

### Memberikan Rating
Setelah pesanan selesai, bot otomatis mengirim pesan dengan tombol bintang.
Klik bintang 1–5 untuk beri rating pesanan dan setiap menu yang dipesan.

---

## BAB 16 — Troubleshooting

### Bot tidak merespons setelah restart server
**Solusi:** Buka browser, akses:
```
https://xxxx-xxxx.trycloudflare.com/set_webhook
```

### Invoice tidak terkirim ke pembeli
**Penyebab:** Library Pillow belum terinstall.
**Solusi:**
```bash
source ~/venv_sgo/bin/activate
pip install Pillow==10.4.0
```
Lalu restart server.

### Tombol rating tidak bisa diklik
**Penyebab:** Webhook tidak menerima callback_query.
**Solusi:** Reset webhook:
```
https://xxxx-xxxx.trycloudflare.com/set_webhook
```

### Halaman admin tidak bisa dibuka (redirect ke login terus)
**Penyebab:** Session expired atau cookie terhapus.
**Solusi:** Login ulang dengan username dan password.

### Server tidak bisa start
**Penyebab:** Port 8000 sudah dipakai proses lain.
**Solusi:**
```bash
pkill -f "python main.py"
bash /mnt/c/Users/user/Desktop/SGO_Nexa/start.sh
```

### Backup tidak berjalan otomatis
**Penyebab:** Server tidak menyala pada jam 02:00 WIB.
**Solusi:** Lakukan backup manual dari halaman Pengaturan sebelum matikan laptop.

---

## Rutinitas Harian yang Disarankan

| Waktu | Kegiatan |
|---|---|
| Sebelum buka (08:00–09:00) | Start server, reset database (opsional) |
| Saat operasional | Monitor pesanan dari dashboard |
| 22:00 | Laporan harian otomatis terkirim ke owner & admin |
| 02:00 | Backup otomatis berjalan |

---

## Informasi Pengembang

**Sentra Guest OS**
Pengembang Sistem Digital untuk UMKM & Restoran

Kami menyediakan solusi teknologi terjangkau untuk membantu bisnis restoran dan UMKM berkembang di era digital.

📱 WhatsApp: [089639541438](https://wa.me/6289639541438)
📧 Email: sentraguest.os@gmail.com
© 2026 Sentra Guest OS. All rights reserved.

---

*Dokumen ini adalah panduan resmi penggunaan sistem SGO v2.1.*
*Dilarang memperbanyak atau mendistribusikan tanpa izin tertulis dari Sentra Guest OS.*
