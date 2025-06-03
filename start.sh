#!/usr/bin/env bash
pip install --upgrade pip
pip install -r requirements.txt
playwright install --with-deps
uvicorn app:app --host 0.0.0.0 --port $PORT

