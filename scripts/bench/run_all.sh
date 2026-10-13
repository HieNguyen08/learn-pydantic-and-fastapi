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
