# Lab 02 — Benchmark validation

> ~15 phút · Sau Module 06 · Lời giải: `labs/lab02_benchmark_validation/bench.py`

## Mục tiêu

Đo đúng cách (min của nhiều lần lặp, ghim một core) chi phí validate hóa đơn của Lab 01 qua các đường khác nhau, và giải thích kết quả bằng kiến trúc của Pydantic (Module 03, 06).

## Bước 1 — Dự đoán

Với hóa đơn 12 dòng (~1,4 KB), xếp hạng từ nhanh đến chậm:

1. `json.loads(raw)` (chỉ parse);
2. `Invoice.model_validate_json(raw)`;
3. `Invoice.model_validate(json.loads(raw))`;
4. `TypeAdapter(list[Invoice])` tạo mới mỗi request;
5. `inv.model_dump_json()`.

## Bước 2 — Chạy

```bash
cd labs/lab02_benchmark_validation
taskset -c 1 python bench.py            # Linux/WSL: ghim một core để giảm nhiễu (Module 06)
```

Output mẫu:

```text
Hóa đơn 12 dòng, 1362 byte
cách                                             min µs  median µs
json.loads (chỉ parse)                             11.5       12.2
model_validate_json(bytes)                         44.6       59.2
json.loads + model_validate                        60.9       65.1
model_validate(dict có sẵn)                        53.4       65.1
TypeAdapter(list[Invoice]) dùng lại                46.8       58.9
TypeAdapter(list[Invoice]) tạo mới mỗi lần        127.6      146.5
model_dump_json                                     8.6        9.0

json.loads + model_validate chậm hơn model_validate_json 1.37×
TypeAdapter tạo mới mỗi lần chậm hơn dùng lại 2.7×
```

## Bước 3 — Giải thích

1. Vì sao `model_validate_json` nhanh hơn `json.loads` + `model_validate`, dù bước thứ hai "chỉ" làm thêm một lần parse? (Gợi ý: jiter parse thẳng vào validator Rust, không tạo `dict` Python trung gian.)
2. Vì sao `model_validate(dict)` vẫn chậm hơn `model_validate_json(bytes)`?
3. Vì sao `TypeAdapter(list[Invoice])` tạo mới mỗi lần đắt, trong khi `TypeAdapter(Invoice)` (một `BaseModel`) thì gần như miễn phí? (Module 03: core schema của model được cache trên class.)
4. Median lớn hơn min khá nhiều ở vài dòng. Đó là gì, và vì sao báo cáo min? (Module 06.)

## Bước 4 — Đặt vào bối cảnh

Validation chỉ ~45 µs, trong khi một `POST` đầy đủ mất ~8 ms, phần lớn ở transaction DB (Module 14, `c1`). Theo Amdahl, tối ưu validation xuống 0 thì request nhanh hơn bao nhiêu phần trăm?

## Mở rộng

- `python bench.py --lines 100` và `--lines 500`: chi phí có tuyến tính theo số dòng không? Ước lượng $a$ và $b$ trong $t(n) = a + bn$ (Module 06).
- Thêm msgspec vào so sánh (xem `scripts/bench/impls.py`).
