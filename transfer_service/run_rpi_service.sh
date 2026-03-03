#!/usr/bin/env bash
set -e
python3 -m pip install -r requirements.txt
uvicorn transfer_service.service.server:app --host 0.0.0.0 --port 8000
