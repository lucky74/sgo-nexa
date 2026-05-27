// ── Address Autocomplete (OpenStreetMap Nominatim) ──
let _addrTimer = null;
let _addrSelected = false;

function onAddressInput(val) {
    _addrSelected = false;
    // Reset koordinat jika user edit ulang
    deliveryData.lat = null;
    deliveryData.lng = null;
    deliveryData.fee = 0;
    document.getElementById('addressConfirmed').style.display = 'none';
    document.getElementById('locationResult').style.display = 'none';

    clearTimeout(_addrTimer);
    if (val.length < 4) {
        closeDropdown();
        return;
    }
    _addrTimer = setTimeout(() => searchAddress(val), 500);
}

function searchAddress(query) {
    // Tambahkan konteks Indonesia agar hasil lebih relevan
    const q = encodeURIComponent(query + ', Indonesia');
    fetch(`https://nominatim.openstreetmap.org/search?q=${q}&format=json&limit=5&addressdetails=1`, {
        headers: { 'Accept-Language': 'id' }
    })
    .then(r => r.json())
    .then(results => {
        if (!results || results.length === 0) { closeDropdown(); return; }
        showDropdown(results);
    })
    .catch(() => closeDropdown());
}

function showDropdown(results) {
    const dropdown = document.getElementById('addressDropdown');
    dropdown.innerHTML = results.map((r, i) => {
        const main = r.display_name.split(',')[0];
        const sub  = r.display_name.split(',').slice(1, 4).join(',').trim();
        return `<div class="autocomplete-item" onclick="selectAddress(${i})"
                     data-lat="${r.lat}" data-lng="${r.lon}" data-full="${r.display_name.replace(/"/g, '&quot;')}">
                    <div class="addr-main">${main}</div>
                    <div class="addr-sub">${sub}</div>
                </div>`;
    }).join('');
    dropdown.style.display = 'block';
}

function selectAddress(idx) {
    const items = document.querySelectorAll('#addressDropdown .autocomplete-item');
    const item  = items[idx];
    if (!item) return;

    const lat  = parseFloat(item.dataset.lat);
    const lng  = parseFloat(item.dataset.lng);
    const full = item.dataset.full;

    document.getElementById('delivery_address').value = full;
    closeDropdown();
    _addrSelected = true;

    // Hitung ongkir otomatis
    calculateDeliveryFee(lat, lng);

    // Tampilkan konfirmasi
    document.getElementById('addressConfirmedText').textContent = full;
    document.getElementById('addressConfirmed').style.display = 'block';
}

function closeDropdown() {
    const d = document.getElementById('addressDropdown');
    if (d) d.style.display = 'none';
}

// Tutup dropdown jika klik di luar
document.addEventListener('click', e => {
    if (!e.target.closest('.address-wrapper')) closeDropdown();
});

// ── Delivery-specific JavaScript ──

let deliveryData = {
    lat: null,
    lng: null,
    address: '',
    distance: null,
    fee: 0,
    maps_url: '',
};

// Override finalisasiPesanan untuk delivery
function finalisasiPesanan() {
    const nama     = document.getElementById('nama').value.trim();
    const whatsapp = document.getElementById('whatsapp').value.trim();
    const address  = document.getElementById('delivery_address').value.trim();

    if (!nama) {
        showError('Mohon isi Nama Pemesan!');
        document.getElementById('nama').focus();
        return;
    }
    if (!whatsapp) {
        showError('Mohon isi Nomor WhatsApp!');
        document.getElementById('whatsapp').focus();
        return;
    }
    if (!address) {
        showError('Mohon isi Alamat Pengiriman!');
        document.getElementById('delivery_address').focus();
        return;
    }
    if (Object.keys(keranjang).length === 0) {
        alert('Keranjang pesanan masih kosong!');
        return;
    }

    let subtotal = 0;
    const items = {};
    const generalNoteVal = document.getElementById('generalNote')?.value || document.getElementById('deliveryNote')?.value || '';

    for (const [key, value] of Object.entries(keranjang)) {
        subtotal += value.harga * value.qty;
        items[key] = { harga: value.harga, qty: value.qty, currentNote: value.currentNote || '-' };
    }

    const service   = TAX_SETTINGS.enable_service ? subtotal * (TAX_SETTINGS.service_rate / 100) : 0;
    const tax       = TAX_SETTINGS.enable_tax     ? subtotal * (TAX_SETTINGS.tax_rate     / 100) : 0;
    const ongkir    = deliveryData.fee || 0;
    const grandTotal = subtotal + service + tax + ongkir;

    const payload = {
        customer: nama,
        table: '-',
        items: items,
        total: `TOTAL: Rp ${grandTotal.toLocaleString('id-ID')}`,
        generalNote: generalNoteVal,
        order_type: 'delivery',
        whatsapp: whatsapp,
        delivery_address: address,
        delivery_lat: deliveryData.lat,
        delivery_lng: deliveryData.lng,
        delivery_distance: deliveryData.distance,
        delivery_fee: ongkir,
        maps_url: deliveryData.maps_url,
        tgid: (window.TGID && window.TGID !== '') ? window.TGID : (localStorage.getItem('tg_user_id') || null),
        voucher_code: window._appliedVoucher ? window._appliedVoucher.code : null,
    };

    const checkoutBtn = document.querySelector('.confirm-pay-btn');
    const originalText = checkoutBtn.innerText;
    checkoutBtn.innerText = 'Mengirim...';
    checkoutBtn.disabled = true;

    const submitUrl = window.OUTLET_ID ? `/outlet/${window.OUTLET_ID}/submit_order` : '/submit_order';
    fetch(submitUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
    .then(r => { if (!r.ok) throw new Error(`Server Error: ${r.status}`); return r.json(); })
    .then(data => {
        if (data.status === 'ok') {
            alert('✅ Pesanan Antar Berhasil Terkirim!\n\nKami akan segera memproses pesanan Anda.');
            if (window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.initData) {
                window.Telegram.WebApp.close();
            } else {
                keranjang = {};
                resetAllButtons();
                updateUI();
                document.getElementById('nama').value = '';
                document.getElementById('whatsapp').value = '';
                document.getElementById('delivery_address').value = '';
                document.getElementById('generalNote').value = '';
                document.getElementById('locationResult').style.display = 'none';
                deliveryData = { lat: null, lng: null, address: '', distance: null, fee: 0, maps_url: '' };
                window._appliedVoucher = null;
                tutupPayment();
            }
        } else {
            alert('⚠️ Gagal mengirim pesanan: ' + data.message);
        }
    })
    .catch(err => alert('❌ Gagal mengirim pesanan.\nDetail: ' + err.message))
    .finally(() => { checkoutBtn.innerText = originalText; checkoutBtn.disabled = false; });
}

// Override bukaPayment untuk delivery
function bukaPayment() {
    const nama     = document.getElementById('nama').value.trim();
    const whatsapp = document.getElementById('whatsapp').value.trim();
    const address  = document.getElementById('delivery_address').value.trim();

    if (!nama) { showError('Mohon isi Nama Pemesan!'); document.getElementById('nama').focus(); return; }
    if (!whatsapp) { showError('Mohon isi Nomor WhatsApp!'); document.getElementById('whatsapp').focus(); return; }
    if (!address) { showError('Mohon isi Alamat Pengiriman!'); document.getElementById('delivery_address').focus(); return; }

    const modal    = document.getElementById('paymentModal');
    const listArea = document.getElementById('orderListSummary');
    let subtotal = 0;
    let html = '';

    const allCards = document.querySelectorAll('.menu-grid .menu-card');
    for (let item in keranjang) {
        const itemData  = keranjang[item];
        const itemTotal = itemData.harga * itemData.qty;
        subtotal += itemTotal;

        let catatan = 'Tanpa catatan';
        allCards.forEach(card => {
            if (card.querySelector('.menu-title')?.innerText === item) {
                const noteInput = card.querySelector('.note-input');
                if (noteInput && noteInput.value.trim()) catatan = noteInput.value.trim();
            }
        });
        keranjang[item].currentNote = catatan;

        html += `<div class="summary-item">
            <div><b>${item}</b> x${itemData.qty}<br><small style="color:#aaa;">Note: ${catatan}</small></div>
            <div>Rp ${itemTotal.toLocaleString('id-ID')}</div>
        </div>`;
    }

    const service    = TAX_SETTINGS.enable_service ? subtotal * (TAX_SETTINGS.service_rate / 100) : 0;
    const tax        = TAX_SETTINGS.enable_tax     ? subtotal * (TAX_SETTINGS.tax_rate     / 100) : 0;
    const ongkir     = deliveryData.fee || 0;
    const grandTotal = subtotal + service + tax + ongkir;

    html += `<div class="summary-item" style="border-top:1px dashed #444;margin-top:10px;padding-top:10px;">
        <div>Subtotal</div><div>Rp ${subtotal.toLocaleString('id-ID')}</div></div>`;
    if (TAX_SETTINGS.enable_service) {
        html += `<div class="summary-item"><div>Service Charge (${TAX_SETTINGS.service_rate}%)</div><div>Rp ${service.toLocaleString('id-ID')}</div></div>`;
    }
    if (TAX_SETTINGS.enable_tax) {
        html += `<div class="summary-item"><div>${TAX_SETTINGS.tax_label} (${TAX_SETTINGS.tax_rate}%)</div><div>Rp ${tax.toLocaleString('id-ID')}</div></div>`;
    }
    html += `<div class="summary-item"><div>🚴 Ongkos Kirim${deliveryData.distance ? ` (${deliveryData.distance.toFixed(1)} km)` : ''}</div><div>Rp ${ongkir.toLocaleString('id-ID')}</div></div>`;
    html += `<div class="summary-item" id="voucherDiscountRow" style="display:none;color:#10B981;"><div>🎟️ Diskon Voucher</div><div id="voucherDiscountAmt">- Rp 0</div></div>`;

    listArea.innerHTML = html;

    // Reset voucher state
    window._appliedVoucher = null;
    window._subtotalForVoucher = subtotal;
    window._baseGrandTotal = grandTotal;

    const voucherSection = document.getElementById('voucherSection');
    if (voucherSection) {
        voucherSection.style.display = 'block';
        const vi = document.getElementById('voucherInput');
        const vm = document.getElementById('voucherMsg');
        if (vi) vi.value = '';
        if (vm) { vm.textContent = ''; vm.style.color = ''; }
    }

    document.getElementById('finalTotalDisplay').innerText = `TOTAL: Rp ${grandTotal.toLocaleString('id-ID')}`;
    modal.style.display = 'block';
    document.getElementById('mainContent').style.display = 'none';
    modal.scrollTop = 0;
}

// Ambil lokasi GPS
function getLocation() {
    const btn = document.getElementById('locationBtn');
    const errDiv = document.getElementById('locationError');
    const resDiv = document.getElementById('locationResult');

    errDiv.style.display = 'none';
    resDiv.style.display = 'none';
    btn.classList.add('loading');
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Mengambil lokasi...';

    if (!navigator.geolocation) {
        showLocationError('Browser Anda tidak mendukung GPS. Silakan isi alamat manual.');
        resetLocationBtn();
        return;
    }

    navigator.geolocation.getCurrentPosition(
        pos => {
            const lat = pos.coords.latitude;
            const lng = pos.coords.longitude;
            calculateDeliveryFee(lat, lng);
        },
        err => {
            let msg = 'Gagal mendapatkan lokasi. ';
            if (err.code === 1) msg += 'Izin lokasi ditolak. Silakan aktifkan izin lokasi di browser.';
            else if (err.code === 2) msg += 'Lokasi tidak tersedia.';
            else msg += 'Silakan isi alamat manual.';
            showLocationError(msg);
            resetLocationBtn();
        },
        { enableHighAccuracy: true, timeout: 10000 }
    );
}

function calculateDeliveryFee(lat, lng) {
    const feeUrl = window.OUTLET_ID ? `/outlet/${window.OUTLET_ID}/api/delivery-fee?lat=${lat}&lng=${lng}` : `/api/delivery-fee?lat=${lat}&lng=${lng}`;
    fetch(feeUrl)
    .then(r => r.json())
    .then(data => {
        resetLocationBtn();
        if (data.status === 'error') {
            showLocationError(data.message || 'Lokasi di luar jangkauan pengiriman.');
            return;
        }

        deliveryData.lat      = lat;
        deliveryData.lng      = lng;
        deliveryData.distance = data.distance;
        deliveryData.fee      = data.fee;
        deliveryData.maps_url = data.maps_url;

        // Reverse geocode untuk nama alamat
        fetch(`https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lng}&format=json`)
        .then(r => r.json())
        .then(geo => {
            const addr = geo.display_name || `${lat.toFixed(5)}, ${lng.toFixed(5)}`;
            deliveryData.address = addr;
            if (!document.getElementById('delivery_address').value.trim()) {
                document.getElementById('delivery_address').value = addr;
            }
            showLocationResult(addr, data.distance, data.fee, data.maps_url);
        })
        .catch(() => {
            showLocationResult(`${lat.toFixed(5)}, ${lng.toFixed(5)}`, data.distance, data.fee, data.maps_url);
        });
    })
    .catch(() => {
        resetLocationBtn();
        showLocationError('Gagal menghitung ongkos kirim. Coba lagi.');
    });
}

function showLocationResult(address, distance, fee, mapsUrl) {
    document.getElementById('locAddress').textContent = '📍 ' + address;
    document.getElementById('locDistance').textContent = `Jarak: ${distance.toFixed(1)} km dari restaurant`;
    document.getElementById('locFee').textContent = `Ongkos Kirim: Rp ${fee.toLocaleString('id-ID')}`;
    document.getElementById('locMaps').href = mapsUrl;
    document.getElementById('locationResult').style.display = 'block';
    document.getElementById('locationError').style.display = 'none';
    updateUI(); // refresh footer total
}

function showLocationError(msg) {
    const errDiv = document.getElementById('locationError');
    errDiv.textContent = '⚠️ ' + msg;
    errDiv.style.display = 'block';
}

function resetLocationBtn() {
    const btn = document.getElementById('locationBtn');
    btn.classList.remove('loading');
    btn.innerHTML = '<i class="fas fa-crosshairs"></i> Gunakan Lokasi GPS Saya';
}

// Override updateUI untuk tambahkan ongkir di footer
const _origUpdateUI = updateUI;
function updateUI() {
    const footer  = document.getElementById('footerOrder');
    const summary = document.getElementById('totalSummary');
    let totalItem = 0, subtotal = 0;
    for (let item in keranjang) {
        totalItem += keranjang[item].qty;
        subtotal  += keranjang[item].harga * keranjang[item].qty;
    }
    if (totalItem > 0) {
        footer.style.display = 'block';
        const tax      = TAX_SETTINGS.enable_tax     ? subtotal * (TAX_SETTINGS.tax_rate     / 100) : 0;
        const service  = TAX_SETTINGS.enable_service ? subtotal * (TAX_SETTINGS.service_rate / 100) : 0;
        const ongkir   = deliveryData.fee || 0;
        const grand    = subtotal + tax + service + ongkir;
        summary.innerText = `${totalItem} Item | ~Rp ${grand.toLocaleString('id-ID')}`;
    } else {
        footer.style.display = 'none';
    }
}
