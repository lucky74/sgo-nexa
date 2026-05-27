#!/bin/bash
echo "=== Proses Python yang berjalan ==="
ps aux | grep python | grep -v grep

echo ""
echo "=== Port 8000 ==="
ss -tlnp | grep 8000 || netstat -tlnp 2>/dev/null | grep 8000

echo ""
echo "=== Test route outlet ==="
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/outlet/1/couriers
echo " <- /outlet/1/couriers (harusnya 302 redirect ke login)"

curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/outlet/1/settings  
echo " <- /outlet/1/settings"

curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/outlet/1/vouchers
echo " <- /outlet/1/vouchers"
