#!/usr/bin/env bash
# Chạy lại toàn bộ benchmark của khóa (≈ 15 phút trên 4 vCPU).
# Yêu cầu: .venv (Pydantic v2 + thư viện so sánh) và .venv-v1 (pydantic<2) ở thư mục gốc repo.
set -euo pipefail
cd "$(dirname "$0")"
ROOT=../..
# ghim vào một core để giảm nhiễu do lập lịch
taskset -c 1 $ROOT/.venv/bin/python bench_validation.py --out results/validation_v2.json
taskset -c 1 $ROOT/.venv-v1/bin/python bench_validation.py --only "pydantic v1" --out results/validation_v1.json
taskset -c 1 $ROOT/.venv/bin/python bench_misc.py
$ROOT/.venv/bin/python bench_concurrency.py
taskset -c 1 $ROOT/.venv/bin/python bench_threads_coroutines.py
$ROOT/.venv/bin/python bench_gil.py
taskset -c 1 $ROOT/.venv/bin/python bench_pagination.py
taskset -c 1 $ROOT/.venv/bin/python bench_validators.py
$ROOT/.venv/bin/python bench_schema_diff.py
$ROOT/.venv/bin/python bench_breakdown.py
taskset -c 1 $ROOT/.venv/bin/python bench_inside_fastapi.py
taskset -c 1 $ROOT/.venv/bin/python bench_deps.py
# Module 10: cần PostgreSQL đang chạy, chuỗi kết nối qua PG_DSN (xem đầu bench_db.py)
if [ -n "${PG_DSN:-}" ]; then $ROOT/.venv/bin/python bench_db.py; else echo "bỏ qua bench_db.py (chưa đặt PG_DSN)"; fi
# Module 11: s3 cần redis-server (REDIS_URL, mặc định redis://localhost:6390)
$ROOT/.venv/bin/python bench_security.py
