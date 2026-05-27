// Initialize Telegram WebApp if available
let tg = null;
if (window.Telegram && window.Telegram.WebApp) {
    tg = window.Telegram.WebApp;
    tg.expand();
}
let keranjang = {};

// Simpan tgid — prioritas: Telegram WebApp initData → window.TGID dari server → URL → localStorage
let _tgid = null;

// 1. Coba dari Telegram WebApp initDataUnsafe (paling reliable, tersedia di semua platform)
if (window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.initDataUnsafe && window.Telegram.WebApp.initDataUnsafe.user) {
    _tgid = String(window.Telegram.WebApp.initDataUnsafe.user.id);
}

// 2. Fallback: dari server via Jinja2 (ada jika URL punya ?tgid=)
if (!_tgid && window.TGID && window.TGID !== '') {
    _tgid = window.TGID;
}

// 3. Fallback: dari URL langsung
if (!_tgid) {
    _tgid = new URLSearchParams(window.location.search).get('tgid');
}

// 4. Fallback: dari localStorage (sesi sebelumnya)
if (!_tgid) {
    _tgid = localStorage.getItem('tg_user_id');
}

// ── Tax & Service settings — pakai dari server jika tersedia, fallback ke API ──
let TAX_SETTINGS = {
    enable_service: true,
    service_rate: 10,
    enable_tax: true,
    tax_rate: 11,
    tax_label: 'PBJT'
};

// Langsung pakai dari server (sudah di-embed sebelum script ini)
if (window.TAX_SETTINGS_SERVER) {
    TAX_SETTINGS = window.TAX_SETTINGS_SERVER;
} else {
    // Fallback: fetch dari API
    fetch('/api/tax-settings').then(r => r.json()).then(d => { TAX_SETTINGS = d; }).catch(() => {});
}

// Simpan ke localStorage untuk sesi berikutnya
if (_tgid) {
    localStorage.setItem('tg_user_id', _tgid);
}

function filterMenu(category, btn) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.querySelectorAll('.menu-card').forEach(card => {
        card.classList.toggle('show', card.getAttribute('data-category') === category);
    });
    // Clear search when switching tabs
    const searchInput = document.getElementById('menuSearch');
    if (searchInput) searchInput.value = '';
    const emptyState = document.getElementById('emptySearchState');
    if (emptyState) emptyState.style.display = 'none';
}

function tambahItem(nama, harga, btnElement) {
    if (!keranjang[nama]) {
        keranjang[nama] = { harga: harga, qty: 0 };
    }
    keranjang[nama].qty += 1;
    updateUI();
    
    // Update Button UI
    const container = btnElement.closest('.btn-container');
    container.dataset.harga = harga; // simpan harga untuk reset nanti
    updateButtonUI(container, nama, harga);
}

function kurangiItem(nama, harga, btnElement) {
    if (keranjang[nama] && keranjang[nama].qty > 0) {
        keranjang[nama].qty -= 1;
        if (keranjang[nama].qty === 0) {
            delete keranjang[nama];
        }
    }
    updateUI();
    
    const container = btnElement.closest('.btn-container');
    updateButtonUI(container, nama, harga);
}

function updateButtonUI(container, nama, harga) {
    const qty = keranjang[nama] ? keranjang[nama].qty : 0;
    
    if (qty > 0) {
        container.innerHTML = `
            <div class="qty-controls" style="display:flex; align-items:center; gap:5px; background:var(--primary-color); border-radius:8px; padding:2px;">
                <button class="qty-btn" onclick="kurangiItem('${nama}', ${harga}, this)" style="background:transparent; color:black; border:none; width:30px; font-weight:bold;">-</button>
                <span class="qty-val" style="color:black; font-weight:bold; min-width:20px; text-align:center;">${qty}</span>
                <button class="qty-btn" onclick="tambahItem('${nama}', ${harga}, this)" style="background:transparent; color:black; border:none; width:30px; font-weight:bold;">+</button>
            </div>
        `;
    } else {
        container.innerHTML = `
            <button class="add-btn" onclick="tambahItem('${nama}', ${harga}, this)">+</button>
        `;
    }
}

function updateUI() {
    const footer = document.getElementById('footerOrder');
    const summary = document.getElementById('totalSummary');
    let totalItem = 0, subtotal = 0;
    for (let item in keranjang) {
        totalItem += keranjang[item].qty;
        subtotal += (keranjang[item].harga * keranjang[item].qty);
    }
    
    if (totalItem > 0) {
        footer.style.display = 'block';
        const tax      = TAX_SETTINGS.enable_tax     ? subtotal * (TAX_SETTINGS.tax_rate     / 100) : 0;
        const service  = TAX_SETTINGS.enable_service ? subtotal * (TAX_SETTINGS.service_rate / 100) : 0;
        const grandTotal = subtotal + tax + service;
        summary.innerText = `${totalItem} Item | ~Rp ${grandTotal.toLocaleString('id-ID')}`;
    } else {
        footer.style.display = 'none';
    }
}

function bukaPayment() {
    const customerName = document.getElementById('nama').value.trim();
    if (!customerName) {
        showError("Silakan masukkan Nama Pemesan terlebih dahulu!");
        document.getElementById('nama').focus();
        return;
    }

    const modal = document.getElementById('paymentModal');
    const listArea = document.getElementById('orderListSummary');
    let subtotal = 0;
    let html = "";

    const allCards = document.querySelectorAll('.menu-grid .menu-card');

    for (let item in keranjang) {
        const itemData = keranjang[item];
        const itemTotal = itemData.harga * itemData.qty;
        subtotal += itemTotal;

        let catatan = "Tanpa catatan";
        // Find note from input
        allCards.forEach(card => {
            if (card.querySelector('.menu-title').innerText === item) {
                const noteInput = card.querySelector('.note-input');
                if (noteInput && noteInput.value.trim()) {
                    catatan = noteInput.value.trim();
                }
            }
        });
        keranjang[item].currentNote = catatan;

        html += `
        <div class="summary-item">
            <div><b>${item}</b> x${itemData.qty}<br><small style="color:#aaa;">Note: ${catatan}</small></div>
            <div>Rp ${itemTotal.toLocaleString('id-ID')}</div>
        </div>`;
    }

    const service   = TAX_SETTINGS.enable_service ? subtotal * (TAX_SETTINGS.service_rate / 100) : 0;
    const tax       = TAX_SETTINGS.enable_tax     ? subtotal * (TAX_SETTINGS.tax_rate     / 100) : 0;
    const grandTotal = subtotal + service + tax;

    html += `<div class="summary-item" style="border-top:1px dashed #444; margin-top:10px; padding-top:10px;"><div>Subtotal</div><div>Rp ${subtotal.toLocaleString('id-ID')}</div></div>`;
    if (TAX_SETTINGS.enable_service) {
        html += `<div class="summary-item"><div>Service Charge (${TAX_SETTINGS.service_rate}%)</div><div>Rp ${service.toLocaleString('id-ID')}</div></div>`;
    }
    if (TAX_SETTINGS.enable_tax) {
        html += `<div class="summary-item"><div>${TAX_SETTINGS.tax_label} (${TAX_SETTINGS.tax_rate}%)</div><div>Rp ${tax.toLocaleString('id-ID')}</div></div>`;
    }

    // Voucher row (hidden initially)
    html += `<div class="summary-item" id="voucherDiscountRow" style="display:none;color:#10B981;"><div>🎟️ Diskon Voucher</div><div id="voucherDiscountAmt">- Rp 0</div></div>`;

    listArea.innerHTML = html;

    // Voucher section
    const voucherSection = document.getElementById('voucherSection');
    if (voucherSection) {
        voucherSection.style.display = 'block';
        document.getElementById('voucherInput').value = '';
        document.getElementById('voucherMsg').textContent = '';
        document.getElementById('voucherMsg').style.color = '';
    }

    // Reset voucher state
    window._appliedVoucher = null;
    window._subtotalForVoucher = subtotal;

    document.getElementById('finalTotalDisplay').innerText = `TOTAL: Rp ${grandTotal.toLocaleString('id-ID')}`;
    window._baseGrandTotal = grandTotal;

    modal.style.display = 'block';
    document.getElementById('mainContent').style.display = 'none';
    modal.scrollTop = 0;
}

function tutupPayment() {
    document.getElementById('paymentModal').style.display = 'none';
    document.getElementById('mainContent').style.display = 'block';
}

// ── VOUCHER FUNCTIONS ──
window._appliedVoucher = null;
window._subtotalForVoucher = 0;
window._baseGrandTotal = 0;

function applyVoucher() {
    const code = (document.getElementById('voucherInput').value || '').trim().toUpperCase();
    const msgEl = document.getElementById('voucherMsg');
    if (!code) {
        msgEl.textContent = 'Masukkan kode voucher terlebih dahulu.';
        msgEl.style.color = '#EF4444';
        return;
    }

    const subtotal = window._subtotalForVoucher || 0;
    msgEl.textContent = 'Memeriksa...';
    msgEl.style.color = '#6B7280';

    fetch(`/api/voucher/check?code=${encodeURIComponent(code)}&subtotal=${subtotal}`)
        .then(r => r.json())
        .then(data => {
            if (data.status === 'ok') {
                window._appliedVoucher = { code: data.code, discount: data.discount };
                msgEl.textContent = `✅ Voucher berhasil! Hemat Rp ${data.discount.toLocaleString('id-ID')}`;
                msgEl.style.color = '#10B981';

                // Update discount row
                const discRow = document.getElementById('voucherDiscountRow');
                const discAmt = document.getElementById('voucherDiscountAmt');
                if (discRow) discRow.style.display = 'flex';
                if (discAmt) discAmt.textContent = `- Rp ${data.discount.toLocaleString('id-ID')}`;

                // Recalculate total
                const newTotal = Math.max(0, window._baseGrandTotal - data.discount);
                document.getElementById('finalTotalDisplay').innerText = `TOTAL: Rp ${newTotal.toLocaleString('id-ID')}`;
            } else {
                window._appliedVoucher = null;
                msgEl.textContent = '❌ ' + (data.message || 'Voucher tidak valid');
                msgEl.style.color = '#EF4444';
                // Reset discount row
                const discRow = document.getElementById('voucherDiscountRow');
                if (discRow) discRow.style.display = 'none';
                document.getElementById('finalTotalDisplay').innerText = `TOTAL: Rp ${window._baseGrandTotal.toLocaleString('id-ID')}`;
            }
        })
        .catch(() => {
            msgEl.textContent = 'Gagal memeriksa voucher.';
            msgEl.style.color = '#EF4444';
        });
}

function showError(msg) {
    const box = document.getElementById('errorBox');
    box.innerText = msg;
    box.style.display = 'block';
    setTimeout(() => { box.style.display = 'none'; }, 3000);
}

function finalisasiPesanan() {
    const nama = document.getElementById('nama').value;
    const nomorMeja = document.getElementById('nomor-meja').value;

    if (!nama || !nomorMeja) {
        alert('Mohon lengkapi Nama dan Nomor Meja!');
        return;
    }

    if (parseInt(nomorMeja) < 1) {
        alert('Nomor meja harus minimal 1!');
        document.getElementById('nomor-meja').focus();
        return;
    }

    if (Object.keys(keranjang).length === 0) {
        alert('Keranjang pesanan masih kosong!');
        return;
    }

    let subtotal = 0;
    const items = {};

    // Get general note value
    const generalNoteVal = document.getElementById('generalNote').value;

    for (const [key, value] of Object.entries(keranjang)) {
        subtotal += value.harga * value.qty;
        items[key] = {
            harga: value.harga,
            qty: value.qty,
            currentNote: value.currentNote || '-'
        };
    }

    const service = TAX_SETTINGS.enable_service ? subtotal * (TAX_SETTINGS.service_rate / 100) : 0;
    const tax     = TAX_SETTINGS.enable_tax     ? subtotal * (TAX_SETTINGS.tax_rate     / 100) : 0;
    const grandTotal = subtotal + service + tax;

    const payload = {
        customer: nama,
        table: nomorMeja,
        items: items,
        total: `TOTAL: Rp ${grandTotal.toLocaleString('id-ID')}`,
        generalNote: generalNoteVal,
        tgid: _tgid,  // sudah disimpan saat halaman load
        voucher_code: window._appliedVoucher ? window._appliedVoucher.code : null,
    };

    // Show loading state
    const checkoutBtn = document.querySelector('.confirm-pay-btn');
    const originalText = checkoutBtn.innerText;
    checkoutBtn.innerText = 'Mengirim...';
    checkoutBtn.disabled = true;

    // Use Fetch API for both Telegram and Browser
    const submitUrl = window.OUTLET_ID ? `/outlet/${window.OUTLET_ID}/submit_order` : '/submit_order';
    fetch(submitUrl, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`Server Error: ${response.status} (URL: ${response.url})`);
        }
        return response.json();
    })
    .then(data => {
        if (data.status === 'ok') {
            alert('✅ Pesanan Berhasil Terkirim!');
            
            // If in Telegram, try to close
            if (window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.initData) {
                window.Telegram.WebApp.close();
            } else {
                // Reset semua UI
                keranjang = {};
                resetAllButtons();
                updateUI();
                document.getElementById('nama').value = '';
                document.getElementById('nomor-meja').value = '';
                document.getElementById('generalNote').value = '';
                window._appliedVoucher = null;
                tutupPayment();
            }
        } else {
            alert('⚠️ Gagal mengirim pesanan: ' + data.message);
        }
    })
    .catch(error => {
        console.error('Order Error:', error);
        alert('❌ Gagal mengirim pesanan. Pastikan server berjalan.\nDetail: ' + error.message);
    })
    .finally(() => {
        checkoutBtn.innerText = originalText;
        checkoutBtn.disabled = false;
    });
}

// Reset semua tombol qty di kartu menu kembali ke tombol "+"
function resetAllButtons() {
    document.querySelectorAll('.menu-card').forEach(card => {
        const container = card.querySelector('.btn-container');
        const noteInput = card.querySelector('.note-input');
        if (!container) return;

        // Ambil nama & harga dari data attribute yang selalu ada
        const nama = container.dataset.nama || '';
        const harga = parseInt(container.dataset.harga || 0);

        // Reset tombol ke "+"
        container.innerHTML = `<button class="add-btn" onclick="tambahItem('${nama.replace(/'/g, "\\'")}', ${harga}, this)">+</button>`;

        // Reset catatan
        if (noteInput) noteInput.value = '';
    });
}

// Image Zoom Functions
function zoomImage(src) {
    const modal = document.getElementById('imageModal');
    const modalImg = document.getElementById('zoomedImage');
    modal.style.display = "block";
    modalImg.src = src;
}

function closeZoom() {
    document.getElementById('imageModal').style.display = "none";
}

// Greeting after name input
let greetingTimer = null;
function onNamaInput(input) {
    clearTimeout(greetingTimer);
    greetingTimer = setTimeout(() => {
        const val = input.value.trim();
        const greetingDiv = document.getElementById('namaGreeting');
        const greetingText = document.getElementById('namaGreetingText');
        if (val.length >= 2) {
            greetingText.textContent = val.split(' ')[0];
            greetingDiv.style.display = 'block';
        } else {
            greetingDiv.style.display = 'none';
        }
    }, 600);
}

// Search/filter menu across all categories
function searchMenu(query) {
    const q = query.trim().toLowerCase();
    const allCards = document.querySelectorAll('.menu-card');
    const emptyState = document.getElementById('emptySearchState');
    let visibleCount = 0;

    if (!q) {
        // Restore normal category filter
        const activeTab = document.querySelector('.tab-btn.active');
        if (activeTab) {
            const activeCategory = activeTab.textContent.trim();
            allCards.forEach(card => {
                card.classList.toggle('show', card.getAttribute('data-category') === activeCategory);
            });
        }
        if (emptyState) emptyState.style.display = 'none';
        return;
    }

    // Show all matching cards regardless of category
    allCards.forEach(card => {
        const title = card.querySelector('.menu-title');
        const desc = card.querySelector('.menu-desc');
        const cuisine = card.querySelector('span[style*="background-color"]');
        const text = [
            title ? title.textContent : '',
            desc ? desc.textContent : '',
            cuisine ? cuisine.textContent : '',
            card.getAttribute('data-category') || ''
        ].join(' ').toLowerCase();

        if (text.includes(q)) {
            card.classList.add('show');
            visibleCount++;
        } else {
            card.classList.remove('show');
        }
    });

    if (emptyState) {
        emptyState.style.display = visibleCount === 0 ? 'block' : 'none';
    }
}

// Call Waiter Function (Browser & Telegram Compatible)
function panggilWaiter() {
    const nama     = document.getElementById('nama').value.trim() || '';
    const nomorMeja = document.getElementById('nomor-meja').value.trim();

    if (!nomorMeja) {
        showError("Mohon isi Nomor Meja agar pelayan tahu posisi Anda!");
        document.getElementById('nomor-meja').focus();
        return;
    }

    if (!nama) {
        showError("Mohon isi Nama Pemesan terlebih dahulu!");
        document.getElementById('nama').focus();
        return;
    }

    if(!confirm(`Panggil pelayan ke Meja ${nomorMeja}?\nNama: ${nama}`)) return;

    fetch('/call_waiter', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ nama: nama, table_number: nomorMeja })
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`Server Error: ${response.status} ${response.statusText}`);
        }
        return response.json();
    })
    .then(data => {
        if (data.status === 'ok') {
            alert('✅ Pelayan telah dipanggil. Mohon tunggu sebentar.');
        } else {
            alert('⚠️ Gagal memanggil pelayan: ' + data.message);
        }
    })
    .catch(error => {
        console.error('Waiter Error:', error);
        alert('❌ Gagal memanggil pelayan. Pastikan server berjalan.\nDetail: ' + error.message);
    });
}
