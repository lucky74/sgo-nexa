#!/bin/bash
# Test semua route outlet langsung ke server yang berjalan
echo "=== Test Route Outlet (server port 8000) ==="
for path in \
    "/outlet/1/login" \
    "/outlet/1/dashboard" \
    "/outlet/1/orders" \
    "/outlet/1/sales-report" \
    "/outlet/1/couriers" \
    "/outlet/1/vouchers" \
    "/outlet/1/customers" \
    "/outlet/1/settings" \
    "/outlet/1/api/menu" \
    "/outlet/1/api/couriers/list"
do
    code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8000${path}")
    if [ "$code" = "404" ]; then
        echo "❌ $code <- $path"
    else
        echo "✅ $code <- $path"
    fi
done

echo ""
echo "=== Cek apakah ada error di response ==="
echo "Response /outlet/1/couriers:"
curl -s "http://localhost:8000/outlet/1/couriers" | head -c 200
