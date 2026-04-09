#!/usr/bin/env bash
set -o errexit

uvicorn main:app --host 0.0.0.0 --port $PORT