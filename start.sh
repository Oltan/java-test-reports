#!/bin/bash
# Test Raporlama Sistemi Sunucu Başlatma
# Kullanım: bash start.sh

cd "$(dirname "$0")/fastapi-server" || exit 1
echo "Sunucu başlatılıyor..."
python3 -m uvicorn server:app --host 0.0.0.0 --port 8000
