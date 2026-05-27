#!/bin/bash
cd /mnt/c/Users/user/Desktop/SGO_Nexa
source ~/venv_sgo/bin/activate

echo "=== Test semua route outlet ==="
routes=(
    "/outlet/1/login"
    "/outlet/1/dashboard"
    "/outlet/1/orders"
    "/outlet/1/sales-report"
    "/outlet/1/couriers"
    "/outlet/1/vouchers"
    "/outlet/1/customers"
    "/outlet/1/settings"
)

for r in "${routes[@]}"; do
    code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8000$r")
    echo "$code <- $r"
done

echo ""
echo "=== Cek apakah ada error di startup ==="
curl -s http://localhost:8000/outlet/1/couriers
