# SGO — Smart Guest Order
## Sistem POS Restoran Berbasis Telegram Bot

---

**Dikembangkan oleh:**
**Sentra Guest OS**
Lucky Zamaludin Malik
📱 WhatsApp: 089639541438
📧 Email: sentraguest.os@gmail.com
© 2026 Sentra Guest OS. All rights reserved.

---

## Apa itu SGO?

SGO (Smart Guest Order) adalah sistem Point of Sale (POS) modern untuk restoran yang memanfaatkan **Telegram Bot** sebagai antarmuka utama. Pembeli memesan langsung dari smartphone via Telegram, sementara admin dan owner memantau semua aktivitas restoran dari dashboard berbasis web yang bisa diakses dari mana saja.

Tidak perlu aplikasi tambahan. Tidak perlu perangkat khusus. Cukup laptop dan koneksi internet.

---

## Mengapa SGO?

| Fitur | POS Konvensional | SGO |
|---|---|---|
| Laporan penjualan | Harian/bulanan | Real-time |
| Pantau pesanan | Harus di tempat | Dari mana saja |
| Notifikasi owner | ❌ Tidak ada | ✅ Via Telegram |
| Biaya lisensi | Rp 5–15 juta/tahun | Jauh lebih hemat |
| Integrasi delivery | ❌ Biasanya tidak ada | ✅ Terintegrasi |
| Notifikasi ke pembeli | ❌ Tidak ada | ✅ Otomatis via Telegram |
| Invoice digital | ❌ Manual | ✅ Otomatis dikirim |
| Rating & Review | ❌ Tidak ada | ✅ Terintegrasi |

---

## Fitur Lengkap

### 🛒 Untuk Pembeli
- Pesan makan di tempat (Dine-in) atau pesan antar (Delivery) langsung dari Telegram
- Tampilan menu digital dengan foto, deskripsi, dan harga
- Deteksi lokasi GPS otomatis untuk delivery
- Kalkulasi ongkos kirim otomatis berdasarkan jarak
- Invoice gambar profesional dikirim ke Telegram setelah pesan
- Notifikasi status pesanan real-time (Diproses → Disajikan → Selesai)
- Input kode voucher/diskon saat checkout
- Rating & review menu setelah pesanan selesai
- Panggil pelayan langsung dari aplikasi

### 👨‍💼 Untuk Admin
- Dashboard manajemen menu (tambah, edit, hapus, aktif/nonaktif)
- Upload foto menu langsung dari dashboard
- Manajemen stok per menu — otomatis nonaktif jika habis
- Notifikasi Telegram jika stok menipis atau habis
- Manajemen pesanan real-time tanpa perlu refresh halaman
- Assign kurir untuk pesanan delivery
- Halaman konfirmasi pengiriman untuk kurir (via link unik)
- Manajemen kurir (tambah, hapus, aktif/nonaktif)
- Buat dan kelola voucher/promo (persen atau nominal)
- Laporan penjualan harian dengan rincian per kategori menu
- Cetak laporan dengan format profesional (kop surat)
- Riwayat pelanggan — data pembelian, menu favorit, total belanja
- Kirim pesan promo langsung ke pelanggan via Telegram
- Backup database otomatis setiap hari jam 02:00 WIB
- Reset data pesanan dengan konfirmasi keamanan
- Ganti password admin dan owner dari dashboard
- Upload QRIS sendiri tanpa bantuan developer

### 👑 Untuk Owner
- Akses dashboard laporan penjualan dari mana saja
- Laporan harian otomatis dikirim ke Telegram setiap jam 22:00 WIB
- Informasi: total pesanan, pendapatan, menu terlaris, perbandingan kemarin
- Akses read-only — tidak bisa mengubah data operasional

### 🔐 Keamanan
- Sistem login dengan 2 level akses (Admin & Owner)
- Session 7 hari — tidak perlu login ulang setiap hari
- Semua halaman admin dilindungi autentikasi
- Password terenkripsi (SHA-256)

---

## Teknologi yang Digunakan

- **Backend:** Python + FastAPI
- **Database:** SQLite (ringan, tidak perlu server database terpisah)
- **Bot:** Telegram Bot API + WebApp
- **Tunnel:** Cloudflare Tunnel (tidak perlu domain/VPS berbayar)
- **Frontend:** Bootstrap 5 + Inter Font
- **Invoice:** Pillow (Python Imaging Library)
- **Scheduler:** APScheduler (backup & laporan otomatis)

---

## Paket Harga

### Paket Setup
**Rp 4.500.000** — Bayar sekali
- Instalasi dan konfigurasi sistem
- Setup Telegram Bot khusus restoran
- Input menu awal (maks. 30 item)
- Training admin (1 sesi, 2 jam)
- Garansi bug 30 hari

### Paket Bulanan (Maintenance)
**Rp 1.200.000 / bulan**
- Update fitur terbaru
- Backup data bulanan
- Support via WhatsApp (jam kerja)
- Prioritas perbaikan bug

### Paket Jual Putus
**Rp 10.000.000** — Hak milik penuh
- Source code lengkap diserahkan
- Dokumentasi teknis
- Training 1 hari penuh
- Tidak ada biaya bulanan
- Pengembangan selanjutnya tanggung jawab klien

---

## Persyaratan Sistem

**Minimum:**
- Laptop/PC dengan RAM 4GB
- Koneksi internet stabil
- Sistem operasi: Windows 10/11 atau Linux/Ubuntu
- Python 3.10 atau lebih baru

**Tidak diperlukan:**
- Server VPS berbayar
- Domain berbayar
- Database server terpisah
- Aplikasi mobile khusus

---

## Kontak & Informasi

**Sentra Guest OS**
Pengembang Sistem Digital untuk UMKM & Restoran

📱 WhatsApp: [089639541438](https://wa.me/6289639541438)
📧 Email: sentraguest.os@gmail.com
© 2026 Sentra Guest OS. All rights reserved.

---

*Dokumen ini bersifat rahasia dan hanya untuk keperluan presentasi kepada calon klien.*
