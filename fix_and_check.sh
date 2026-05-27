#!/bin/bash
# Jalankan di WSL: bash fix_and_check.sh

cd /mnt/c/Users/user/Desktop/SGO_Nexa
source ~/venv_sgo/bin/activate

echo "=== CEK FILE ==="
echo "Ukuran main.py: $(wc -c < main.py) bytes"
echo "Jumlah baris: $(wc -l < main.py)"

echo ""
echo "=== CEK ROUTE OUTLET ==="
grep -c 'outlet_id}/couriers' main.py && echo "✅ Route couriers ADA" || echo "❌ Route couriers TIDAK ADA"
grep -c 'outlet_id}/settings' main.py && echo "✅ Route settings ADA" || echo "❌ Route settings TIDAK ADA"
grep -c 'outlet_id}/vouchers' main.py && echo "✅ Route vouchers ADA" || echo "❌ Route vouchers TIDAK ADA"
grep -c 'outlet_id}/customers' main.py && echo "✅ Route customers ADA" || echo "❌ Route customers TIDAK ADA"

echo ""
echo "=== CEK SYNTAX ==="
python -m py_compile main.py && echo "✅ Syntax OK" || echo "❌ Syntax ERROR"

echo ""
echo "=== SELESAI ==="
