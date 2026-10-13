# Module 06 — Hiệu năng Pydantic: đo, hiểu, tối ưu

> Thời lượng: ~45 phút · Mức độ: Trung bình–Nâng cao · Tiên quyết: Module 03, Module 04

"Pydantic v2 nhanh gấp 17 lần v1", "msgspec nhanh hơn Pydantic", "marshmallow chậm" — mọi kỹ sư Python đều đã nghe những câu này. Module này không lặp lại khẩu hiệu mà làm ba việc: (1) **đo** chín cách validate cùng một hóa đơn trên cùng một máy, có công bố phương pháp và độ nhiễu; (2) **dựng mô hình chi phí** để dự đoán thời gian cho payload bất kỳ; (3) dùng **định luật Amdahl** để trả lời câu hỏi thật sự quan trọng: *trong một request của `invoice-api`, validation chiếm bao nhiêu phần, và tối ưu nó có đáng không?* Kết luận có thể làm bạn bất ngờ.

Mọi số liệu đo trên container **4 vCPU Intel Xeon 2,8 GHz, Python 3.13**, script `scripts/bench/bench_validation.py`, `bench_breakdown.py` (Lab 02 hướng dẫn chạy lại).

## Mục tiêu học tập

Sau module này, bạn có thể:

1. Thiết kế một microbenchmark đáng tin: khởi động, lặp, chọn thống kê (min hay trung vị), ghim CPU, ước lượng độ nhiễu giữa các lần chạy.
2. Đọc kết quả so sánh 9 cách validate hóa đơn (Pydantic v2/v1, msgspec, marshmallow, attrs+cattrs, dataclasses viết tay…) và giải thích **vì sao** chúng khác nhau.
3. Lập **mô hình chi phí tuyến tính** $t(n) = a + b\,n$ theo số dòng hàng và dùng nó để ước lượng.
4. Phân rã chi phí một request: parse JSON, validate cấu trúc, quy tắc Python, serialize — và **áp dụng định luật Amdahl** để quyết định có nên tối ưu validation không.
5. Áp dụng danh sách tối ưu theo thứ tự lợi ích/rủi ro, và biết khi nào chuyển sang msgspec hay `model_construct` là hợp lý.
6. Đánh giá rủi ro hiệu năng của endpoint batch và chọn cách xử lý (giới hạn, bất đồng bộ, tiến trình riêng).

---

## 1. Đo cho đúng trước khi đo cho nhanh

### 1.1. Vấn đề

Một microbenchmark đo thời gian một đoạn code chạy vài micro-giây. Ở thang đó, mọi thứ đều là nhiễu: bộ lập lịch của hệ điều hành, tần số CPU thay đổi, bộ nhớ đệm, garbage collector, cách bố trí bộ nhớ khác nhau giữa các tiến trình, và hàng xóm trên cùng máy ảo. Một con số không kèm phương pháp đo gần như vô nghĩa.

### 1.2. Quy trình đo của khóa

1. **Khởi động**: gọi hàm vài lần trước khi đo (dựng cache, nạp code).
2. **`timeit.Timer.autorange()`**: chọn số lần lặp $N$ để một phép đo kéo dài ≥ 0,2 s, tránh độ phân giải đồng hồ.
3. **Lặp $R = 11$ lần**, mỗi lần đo $N$ lời gọi → 11 giá trị thời gian/lời gọi.
4. **Báo cáo min** (thời gian tốt nhất): nhiễu chỉ **cộng thêm** thời gian, không bao giờ làm code nhanh hơn, nên min là ước lượng ít nhiễu nhất của chi phí nội tại — đây cũng là khuyến nghị trong tài liệu `timeit`. Trung vị được lưu kèm trong file JSON.
5. **Ghim một core** (`taskset -c 1`) để giảm việc tiến trình bị di chuyển giữa các CPU.

### 1.3. Độ nhiễu thật: chạy lại 8 tiến trình

Cùng một phép đo (`model_validate_json` hóa đơn 12 dòng) chạy trong 8 tiến trình độc lập:

<!-- placeholder-noise -->

<!-- fig:noise -->
<figure markdown="span">
  ![Số đo thật: cùng một phép đo chạy trong 8 tiến trình độc lập](assets/figures/06/noise.light.svg#only-light){ loading=lazy }
  ![Số đo thật: cùng một phép đo chạy trong 8 tiến trình độc lập](assets/figures/06/noise.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 6.1 — Số đo thật: cùng một phép đo chạy trong 8 tiến trình độc lập. Min ổn định hơn trung vị trong một lần chạy, nhưng giữa các tiến trình vẫn dao động ±15%.</figcaption>
</figure>
<!-- /fig -->

| | Thấp nhất | Cao nhất | Chênh |
|---|---|---|---|
| min của từng tiến trình | 19,7 µs | 26,4 µs | ±15% |
| trung vị của từng tiến trình | 26,3 µs | 32,3 µs | ±10% |

Hai bài học:

- **Trong một lần chạy**, min ổn định hơn trung vị. Nhưng **giữa các tiến trình** vẫn có dao động ±15% (bố trí bộ nhớ, trạng thái máy ảo). Trên máy này, chênh lệch dưới ~30% giữa hai thư viện là **không đủ bằng chứng** để kết luận cái nào nhanh hơn.
- Vì vậy các so sánh trong module chỉ rút kết luận từ **tỷ lệ lớn** (gấp 2 lần trở lên) và từ **hình dạng đường cong** (tuyến tính, hằng số), những thứ ổn định giữa các máy.

---

## 2. Kết quả: chín cách validate một hóa đơn

### 2.1. Thiết lập

Cùng một đặc tả hóa đơn (Module 00) được cài bằng mỗi thư viện ở hai mức:

- **schema**: kiểu + ràng buộc từng trường (độ dài, khoảng giá trị, regex MST, tập thuế suất).
- **full**: schema + quy tắc nghiệp vụ Python dùng chung (checksum MST, `amount`, tổng).

Mỗi cài đặt được kiểm tra **đúng đắn** trước khi đo: payload hợp lệ phải qua; payload sai tổng 1 đồng phải bị chặn ở mức full (script dừng nếu thư viện nào không chặn — chính bước này đã bắt được một lỗi cài đặt `__post_init__` của msgspec trong lúc viết khóa). Payload có 1, 12, 50 và 200 dòng (0,6 / 2,3 / 8,3 / 32 KB).

### 2.2. Hóa đơn 12 dòng

<!-- placeholder-libs-12 -->

<!-- fig:libs-12 -->
<figure markdown="span">
  ![Số đo thật: hóa đơn 12 dòng, chín cách làm, hai mức kiểm tra (thang log)](assets/figures/06/libs-12.light.svg#only-light){ loading=lazy }
  ![Số đo thật: hóa đơn 12 dòng, chín cách làm, hai mức kiểm tra (thang log)](assets/figures/06/libs-12.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 6.2 — Số đo thật: hóa đơn 12 dòng, chín cách làm, hai mức kiểm tra (thang log).</figcaption>
</figure>
<!-- /fig -->

| Cách làm | schema (µs) | full (µs) |
|---|---|---|
| `orjson.loads` — **chỉ parse**, không kiểm tra | 8,7 | — |
| `json.loads` — **chỉ parse** | 23,2 | — |
| msgspec `Struct` | **9,6** | **16,5** |
| Pydantic v2 `model_validate_json` | 22,7 | 28,2 |
| Pydantic v2 strict | 21,3 | 29,4 |
| Pydantic v2 `json.loads` + `model_validate` | 46,6 | 55,9 |
| dataclasses + code tay | 47,2 | 55,7 |
| attrs + cattrs | 63,5 | 74,9 |
| Pydantic v2, `TypeAdapter` dựng mỗi request | 88,5 | 134,8 |
| Pydantic v1 (bản biên dịch Cython) `parse_raw` | 201,7 | 247,7 |
| marshmallow 4 | 416,4 | 452,8 |

### 2.3. Giải thích từng khoảng cách

- **v2 so với v1: nhanh hơn ~8,5–8,9 lần** ở mọi kích thước. Con số nằm trong khoảng 4–50 lần mà dự án công bố cho v2 (điển hình ~17 lần trên model của họ). Lý do chính: v1 duyệt type hint và gọi hàm Python cho từng trường mỗi lần validate; v2 chạy cây validator Rust dựng sẵn (Module 03).
- **Pydantic v2 ngang `json.loads`**: parse **và** validate bằng Pydantic tốn ngang chỉ parse bằng thư viện chuẩn, vì Pydantic không dựng cây object trung gian.
- **Viết tay không nhanh hơn**: dataclasses + code tay (47 µs) chậm gấp đôi Pydantic (23 µs) — vì mỗi kiểm tra là một dòng Python, trong khi Pydantic kiểm tra trong Rust. Lý do thường gặp để "tự viết cho nhanh" không đứng vững; thêm vào đó code tay không sinh JSON Schema, không gom lỗi có `loc`.
- **msgspec nhanh hơn Pydantic ~1,7–2,4 lần**: thiết kế tối giản hơn — `Struct` là kiểu C riêng, decoder được biên dịch cho đúng kiểu đích, ít tính năng (không có chế độ lax cho chuỗi số, không có validator before/wrap, không có alias động…). Cái giá của tính năng là hằng số nhỏ chứ không phải bậc độ lớn.
- **marshmallow chậm hơn Pydantic v2 ~16–19 lần**: toàn bộ là Python thuần, mỗi trường là một chuỗi lời gọi phương thức.

### 2.4. Theo kích thước payload

<!-- placeholder-scaling -->

<!-- fig:scaling -->
<figure markdown="span">
  ![Số đo thật: thời gian validate theo số dòng hàng (log–log); các đường gần như song song](assets/figures/06/scaling.light.svg#only-light){ loading=lazy }
  ![Số đo thật: thời gian validate theo số dòng hàng (log–log); các đường gần như song song](assets/figures/06/scaling.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 6.3 — Số đo thật: thời gian validate theo số dòng hàng (log–log); các đường gần như song song.</figcaption>
</figure>
<!-- /fig -->

Mọi thư viện tăng **tuyến tính** theo số dòng — không có thư viện nào có hành vi siêu tuyến tính trên dữ liệu này. Trên thang log–log, các đường gần như song song; khoảng cách dọc giữa chúng chính là tỷ lệ hằng số ở mục 2.3.

---

## 3. Mô hình chi phí

### 3.1. Hồi quy tuyến tính

Với mỗi cách làm, khớp $t(n) = a + b\,n$ (bình phương tối thiểu trên 4 kích thước):

| Cách làm (mức full) | $a$ — chi phí cố định (µs) | $b$ — mỗi dòng hàng (µs) |
|---|---|---|
| msgspec | 3,7 | 1,04 |
| Pydantic v2 `model_validate_json` | 7,4 | 1,86 |
| Pydantic v2 `json.loads` + `model_validate` | 11,9 | 3,37 |
| dataclasses + code tay | 9,9 | 3,55 |
| attrs + cattrs | 17,6 | 4,64 |
| Pydantic v1 | 113,0 | 12,77 |
| marshmallow 4 | 104,5 | 30,02 |
| Pydantic v2, dựng `TypeAdapter` mỗi request | **106,3** | 2,21 |

<!-- placeholder-cost-model -->

<!-- fig:cost-model -->
<figure markdown="span">
  ![Hai tham số của mô hình chi phí tuyến tính cho từng cách làm](assets/figures/06/cost-model.light.svg#only-light){ loading=lazy }
  ![Hai tham số của mô hình chi phí tuyến tính cho từng cách làm](assets/figures/06/cost-model.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 6.4 — Hai tham số của mô hình chi phí tuyến tính cho từng cách làm.</figcaption>
</figure>
<!-- /fig -->

Đọc bảng:

- $b$ phản ánh tốc độ "động cơ" validate (mỗi dòng ~8 trường). Pydantic v2 ~1,9 µs/dòng ≈ 230 ns/trường kể cả quy tắc Python.
- $a$ là chi phí cố định mỗi lời gọi. Dòng cuối minh họa anti-pattern của Module 03: dựng `TypeAdapter` mỗi request **không** làm động cơ chậm đi ($b$ gần như không đổi) mà cộng ~100 µs **cố định** — gây hại nhất với payload nhỏ, đúng loại request phổ biến nhất.

### 3.2. Dùng mô hình để ước lượng

Hóa đơn 12 dòng: $7{,}4 + 12 \times 1{,}86 \approx 30$ µs (đo được 28,2 µs). Endpoint batch tối đa 500 hóa đơn × 12 dòng:

$$
t_{\text{batch}} \approx 500 \times 30\ \mu s = 15\ \text{ms}.
$$

Nhưng nếu khách gửi 500 hóa đơn **200 dòng**: $500 \times (7{,}4 + 200 \times 1{,}86) \approx 190$ ms CPU — trên một event loop, đó là 190 ms mọi request khác phải chờ (mục 6).

---

## 4. Phân rã một request và định luật Amdahl

### 4.1. Phân rã chi phí xử lý hóa đơn

Đo từng bước bằng Pydantic v2 (min, 1 core):

| Bước | 1 dòng | 12 dòng | 200 dòng |
|---|---|---|---|
| parse JSON thành object Python (`pydantic_core.from_json`) | 1,9 µs | 8,9 µs | 127 µs |
| parse + validate cấu trúc (mức schema) | 4,8 µs | 18,5 µs | 238 µs |
| + quy tắc nghiệp vụ Python (mức full) | 7,1 µs | 25,3 µs | 318 µs |
| serialize response (`model_dump_json`) | 3,7 µs | 10,7 µs | 135 µs |

<!-- placeholder-breakdown -->

<!-- fig:breakdown -->
<figure markdown="span">
  ![Số đo thật: phân rã chi phí Pydantic cho một hóa đơn theo bốn bước](assets/figures/06/breakdown.light.svg#only-light){ loading=lazy }
  ![Số đo thật: phân rã chi phí Pydantic cho một hóa đơn theo bốn bước](assets/figures/06/breakdown.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 6.5 — Số đo thật: phân rã chi phí Pydantic cho một hóa đơn theo bốn bước.</figcaption>
</figure>
<!-- /fig -->

Với hóa đơn 12 dòng: parse + validate + quy tắc + serialize ≈ **36 µs**. Phần quy tắc Python của mình (~7 µs) chiếm ~20% của phần Pydantic.

### 4.2. Validation chiếm bao nhiêu phần của một request?

Bảng trên đo Pydantic **đứng riêng**. Trong FastAPI, đường đi của body khác một chút: FastAPI đọc byte, gọi `request.json()` (tức `json.loads` của thư viện chuẩn) rồi mới validate dict — tức là đường **chậm** ở mục 2.2, không phải `model_validate_json` (Module 07 mục 3 đọc mã nguồn). Đo trong tiến trình, gọi thẳng ứng dụng ASGI không qua mạng (script `bench_inside_fastapi.py`):

| Endpoint (cùng model hóa đơn 12 dòng) | µs/request |
|---|---|
| `GET /health` trả `dict` — chi phí khung sườn FastAPI + Starlette | ~54 |
| `POST /invoices` khai báo `inv: Invoice`, trả response model nhỏ | ~135 |
| `POST /invoices` tự đọc byte + `Invoice.model_validate_json`, trả response model nhỏ | **~86** |

Phần "đọc body + parse + validate + response" theo cách mặc định tốn ~$135 - 54 \approx 81$ µs. Qua server thật (Module 09), mỗi request `POST /invoices` tốn ~490 µs thời gian worker với Uvicorn thuần (h11 + asyncio) và ~250 µs với `uvicorn[standard]`, nên tỷ lệ của phần đó là

$$
p \approx \frac{81}{490} \approx 17\% \quad\text{(h11)}, \qquad p \approx \frac{81}{250} \approx 32\% \quad\text{(httptools + uvloop)}.
$$

**Định luật Amdahl**: nếu tăng tốc phần chiếm tỷ lệ $p$ lên $s$ lần, cả hệ nhanh lên

$$
S = \frac{1}{(1 - p) + p/s}.
$$

<!-- placeholder-amdahl -->

<!-- fig:amdahl -->
<figure markdown="span">
  ![Định luật Amdahl với số liệu của invoice-api: thay thư viện validation chỉ cho vài phần trăm, trong khi đổi bộ phân tích HTTP cho ~1,7 lần](assets/figures/06/amdahl.light.svg#only-light){ loading=lazy }
  ![Định luật Amdahl với số liệu của invoice-api: thay thư viện validation chỉ cho vài phần trăm, trong khi đổi bộ phân tích HTTP cho ~1,7 lần](assets/figures/06/amdahl.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 6.6 — Định luật Amdahl với số liệu của invoice-api: thay thư viện validation chỉ cho vài phần trăm, trong khi đổi bộ phân tích HTTP cho ~1,7 lần.</figcaption>
</figure>
<!-- /fig -->

| Phương án (ước lượng từ số đo, cộng trừ thời gian tuyệt đối) | Tăng tốc cả request $S$ |
|---|---|
| Thay Pydantic bằng msgspec, phần đó nhanh ~2× ($p$ = 17%) | ~1,09× |
| Tự đọc byte + `model_validate_json` (bớt ~50 µs/request) | ~1,11× (h11) · ~1,25× (`[standard]`) |
| Validation nhanh vô hạn ($p$ = 17%) | ~1,20× |
| Đổi `uvicorn` → `uvicorn[standard]` (đo được ở Module 02) | **~1,7×** |

Kết luận: với `invoice-api`, **viết lại toàn bộ model sang msgspec chỉ đổi được ~9%**, một dòng trong `requirements.txt` cho ~70%, và đổi cách FastAPI nhận body (giữ nguyên Pydantic) cho 11–25%. Và đây mới chỉ là CPU — trong thực tế mỗi request còn một transaction database cỡ vài mili-giây, khiến các tỷ lệ trên càng nhỏ. Nguyên tắc: **đo phân rã trước, tối ưu phần lớn nhất trước**.

### 4.3. Khi nào validation thật sự là nút thắt?

Khi tỷ lệ $p$ lớn: service không có I/O nặng mà chỉ biến đổi dữ liệu (proxy chuyển đổi định dạng, xử lý stream sự kiện, ETL), payload rất lớn (hàng nghìn phần tử), hoặc tải hàng chục nghìn request/giây mỗi tiến trình. Khi đó msgspec, `model_construct` cho dữ liệu tin cậy, hay chuyển phần nóng sang tiến trình riêng mới đáng cân nhắc.

---

## 5. Danh sách tối ưu, theo thứ tự lợi ích/rủi ro

| # | Việc làm | Lợi ích đo được | Rủi ro |
|---|---|---|---|
| 1 | `model_validate_json(raw)` thay vì `json.loads` + `model_validate` | ~2× cho phần validate | không |
| 2 | Tạo model/`TypeAdapter` một lần ở cấp module | bỏ ~70–130 µs cố định mỗi request | không |
| 3 | Ràng buộc bằng `Field`/`Literal`/`annotated_types` thay vì validator Python | +0,3 ns thay vì +30–170 ns mỗi trường | không; còn có JSON Schema |
| 4 | Discriminated union thay smart union | ~5× cho phần union, 1 lỗi thay vì nhiều | cần trường tag |
| 5 | `model_dump_json()` thay vì `model_dump()` + `json.dumps` | ~2,8× cho serialize | không |
| 6 | Tránh `validate_assignment=True` trong vòng lặp nóng; tránh validate lại instance (`revalidate_instances="never"`) | tùy | thấp |
| 7 | `defer_build=True` cho model ít dùng | giảm thời gian khởi động | lỗi schema xuất hiện muộn (lần dùng đầu) |
| 8 | `model_construct()` cho dữ liệu đã kiểm tra (đọc lại từ DB/cache của chính mình) | bỏ toàn bộ validation | bất biến có thể bị phá âm thầm |
| 9 | msgspec cho đường nóng chuyên biệt | ~1,7–2,4× cho phần validate | hai hệ model, mất tính năng (lax, validator before/wrap) |

<!-- placeholder-checklist -->

<!-- fig:checklist -->
<figure markdown="span">
  ![Lợi ích đo được của bốn tối ưu mặc định, tính trên phần mã liên quan](assets/figures/06/checklist.light.svg#only-light){ loading=lazy }
  ![Lợi ích đo được của bốn tối ưu mặc định, tính trên phần mã liên quan](assets/figures/06/checklist.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 6.7 — Lợi ích đo được của bốn tối ưu mặc định, tính trên phần mã liên quan.</figcaption>
</figure>
<!-- /fig -->

Mục 1–5 nên là **mặc định** trong mọi codebase. Mục 8–9 chỉ khi phân rã (mục 4) cho thấy validation chiếm phần đáng kể.

---

## 6. Case Mekong Cloud: endpoint batch và event loop

### 6.1. Vấn đề

`POST /v1/invoice-batches` nhận tối đa 500 hóa đơn. Validation là CPU thuần; trên một worker async, trong lúc validate batch, **event loop không phục vụ request nào khác** (Module 02, mục 4). Với batch 500 × 12 dòng: ~15 ms — chấp nhận được. Với batch 500 × 200 dòng: ~190 ms (theo mô hình mục 3; tính cả parse và serialize còn hơn) — mọi request khác trên worker đó trễ thêm tới 190 ms, ăn gần hết SLO p99 300 ms.

### 6.2. Các lựa chọn

| Cách | Hiệu quả | Ghi chú |
|---|---|---|
| Giới hạn tổng số dòng mỗi batch (ví dụ ≤ 10.000 dòng), không chỉ số hóa đơn | chặn trường hợp xấu nhất ở ~40 ms | rẻ, nên làm luôn; kiểm tra sớm bằng validator độ dài |
| Khai báo endpoint là `def` (chạy trong threadpool) | event loop vẫn chạy được giữa các lần nhả GIL (mặc định mỗi 5 ms) | không giảm tổng CPU; các request khác vẫn chậm đi |
| Trả `202 Accepted`, validate + ghi trong **worker riêng** (hàng đợi) | API worker không bị chặn | đúng với thiết kế REST ở Module 02 (batch là tài nguyên bất đồng bộ) |
| Chạy validate trong `ProcessPoolExecutor` | song song CPU thật | tốn chi phí truyền dữ liệu giữa tiến trình; phức tạp |

Thiết kế của `invoice-api`: **giới hạn 10.000 dòng/batch + xử lý bất đồng bộ bằng worker riêng** (Module 13–14). Request batch chỉ kiểm tra kích thước và ghi vào hàng đợi; validation chi tiết chạy ở worker, kết quả từng hóa đơn đọc qua `GET /v1/invoice-batches/{id}`.

<!-- placeholder-batch -->

<!-- fig:batch -->
<figure markdown="span">
  ![Batch lớn chặn event loop; thiết kế giới hạn kích thước và xử lý bất đồng bộ của invoice-api](assets/figures/06/batch.light.svg#only-light){ loading=lazy }
  ![Batch lớn chặn event loop; thiết kế giới hạn kích thước và xử lý bất đồng bộ của invoice-api](assets/figures/06/batch.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 6.8 — Batch lớn chặn event loop; thiết kế giới hạn kích thước và xử lý bất đồng bộ của invoice-api.</figcaption>
</figure>
<!-- /fig -->

---

## Lỗi thường gặp & cách xử lý

| Triệu chứng | Nguyên nhân gốc | Cách xử lý |
|---|---|---|
| Benchmark hôm nay khác hôm qua 20% | Nhiễu giữa các tiến trình/máy ảo | Lặp nhiều tiến trình; báo min + khoảng; chỉ tin tỷ lệ lớn |
| "Thư viện X nhanh hơn" nhưng service không nhanh hơn | Validation chỉ chiếm vài % request (Amdahl) | Phân rã chi phí request trước khi tối ưu |
| Viết validate tay "cho nhanh" lại chậm hơn | Mỗi kiểm tra là bytecode Python | Dùng ràng buộc trong core của Pydantic |
| Request nhỏ chậm bất thường | Dựng model/`TypeAdapter` trong handler (chi phí cố định ~100 µs) | Đưa lên cấp module |
| Một khách gửi batch lớn làm p99 của mọi khách tăng vọt | CPU-bound trên event loop | Giới hạn tổng dòng, xử lý batch bất đồng bộ |
| Chuyển sang `model_construct` rồi dữ liệu sai lan rộng | Bỏ validation với dữ liệu chưa thật sự tin cậy | Chỉ dùng cho dữ liệu đã qua chính model; đo trước khi dùng |

## Tóm tắt (cheat-sheet)

- Đo: khởi động → `autorange` → lặp 11 lần → báo **min** (+ trung vị) → ghim core → chạy lại nhiều tiến trình; nhiễu ±15% trên máy ảo.
- 12 dòng, mức full: msgspec 16,5 µs · **Pydantic v2 28 µs** · dataclasses tay 56 µs · attrs+cattrs 75 µs · v1 248 µs · marshmallow 453 µs.
- v2 nhanh hơn v1 ~8,5–9× (trong khoảng 4–50× công bố); viết tay chậm hơn Pydantic ~2×; msgspec nhanh hơn ~2×.
- Chi phí tuyến tính: Pydantic v2 ≈ 7,4 µs + 1,86 µs × số dòng.
- Trong FastAPI, body đi qua `json.loads` rồi mới validate (~81 µs/request cho phần body + response). Request đầy đủ ~490 µs (h11) / ~250 µs (`[standard]`) → $p$ ≈ 17–32%. Amdahl: msgspec ~1,09×; tự `model_validate_json` ~1,11–1,25×; `uvicorn[standard]` ~1,7×.
- Mặc định: `model_validate_json`, model ở cấp module, ràng buộc trong core, discriminated union, `model_dump_json`.
- CPU-bound lớn (batch) → giới hạn kích thước + xử lý bất đồng bộ.

## Câu hỏi tự kiểm tra / phỏng vấn

1. Vì sao báo cáo min thay vì trung bình cho microbenchmark? Khi nào min gây hiểu lầm?

    <details markdown="1"><summary>Gợi ý</summary>
    Nhiễu chỉ làm chậm thêm; min gần chi phí nội tại nhất. Min gây hiểu lầm khi điều bạn quan tâm là phân phối thực tế (latency đuôi của service, có GC, cache lạnh) — khi đó phải đo percentile dưới tải thật (Module 09).
    </details>

2. Đồng nghiệp đề xuất chuyển toàn bộ model sang msgspec "để API nhanh gấp đôi". Bạn trả lời bằng số nào?

    <details markdown="1"><summary>Gợi ý</summary>
    Phân rã: phần body + validate + response ~81 µs trong ~490 µs mỗi request (~17%); msgspec nhanh ~2× phần đó → Amdahl $S = 1/(0{,}83 + 0{,}085) \approx 1{,}09$. Đổi `uvicorn[standard]` cho ~1,7×; tự gọi `model_validate_json` cho 11–25% mà vẫn giữ Pydantic; tối ưu DB còn nhiều hơn. Chưa kể chi phí duy trì hai hệ model và mất tính năng.
    </details>

3. Giải thích vì sao code validate viết tay bằng dataclasses chậm hơn Pydantic v2.

    <details markdown="1"><summary>Gợi ý</summary>
    Mỗi kiểm tra (type, độ dài, khoảng) là vài bytecode Python + lời gọi hàm; Pydantic chạy các kiểm tra đó trong Rust và parse JSON không qua object trung gian. Hơn nữa phải gọi `json.loads` trước (~23 µs, ngang toàn bộ Pydantic).
    </details>

4. Từ mô hình $t(n) = 7{,}4 + 1{,}86n$ µs, ước lượng thời gian validate batch 500 hóa đơn × 50 dòng. Có chặn event loop đáng kể không?

    <details markdown="1"><summary>Gợi ý</summary>
    $500 \times (7{,}4 + 93) \approx 50$ ms. Có: mọi request khác trên worker đó chờ thêm ~50 ms; nên giới hạn tổng dòng và xử lý bất đồng bộ.
    </details>

5. Dựng `TypeAdapter` trong mỗi request ảnh hưởng tới $a$ hay $b$ trong mô hình chi phí? Hệ quả?

    <details markdown="1"><summary>Gợi ý</summary>
    Tới $a$ (cố định, +~100 µs), không tới $b$. Request nhỏ bị ảnh hưởng nặng nhất (một hóa đơn 1 dòng chậm ~15 lần).
    </details>

6. Một bài blog nói "Pydantic v2 nhanh hơn v1 17 lần", bạn đo được 9 lần. Ai sai?

    <details markdown="1"><summary>Gợi ý</summary>
    Không ai sai: tỷ lệ phụ thuộc model (kiểu trường, độ lồng nhau, validator Python), phiên bản, máy. Dự án công bố khoảng 4–50×; 17× là điển hình trên model của họ. Luôn đo trên payload của chính mình.
    </details>

7. Khi nào `model_construct` là lựa chọn hợp lý?

    <details markdown="1"><summary>Gợi ý</summary>
    Dữ liệu đã được chính model đó validate trước đây và đọc lại từ nguồn bạn kiểm soát (DB, cache), validation chiếm phần đáng kể theo phân rã, và có test bảo đảm dữ liệu ghi vào luôn hợp lệ.
    </details>

## Bài tập thực hành

1. **Chạy lại benchmark (CPU, 20 phút).** Làm theo Lab 02: chạy `bench_validation.py` trên máy bạn, vẽ lại bảng mục 2.2. Tỷ lệ v1/v2 và msgspec/v2 của bạn là bao nhiêu?
2. **Đo nhiễu (CPU, 10 phút).** Chạy `bench_breakdown.py` hai lần, có và không có `taskset`. Độ phân tán của min thay đổi thế nào?
3. **Phân rã request của bạn (CPU, 30 phút).** Lấy một endpoint FastAPI bạn đã viết, đo bằng `cProfile` hoặc `pyinstrument` khi chịu tải (Lab 04). Tỷ lệ thời gian của Pydantic là bao nhiêu? Tính $S$ theo Amdahl nếu Pydantic nhanh gấp đôi.
4. **Giới hạn batch (CPU, 20 phút).** Viết validator cho `InvoiceBatchIn` chặn tổng số dòng > 10.000 **trước** khi validate từng hóa đơn (gợi ý: validator `before` ở mức model đếm `len` trên dữ liệu thô). Đo thời gian từ chối một batch quá lớn.

## Tài liệu tham khảo

Paper và bài viết:

- Amdahl, G. M. (1967). *Validity of the single processor approach to achieving large scale computing capabilities*. AFIPS Spring Joint Computer Conference, pp. 483–485.
- Mytkowicz, T., Diwan, A., Hauswirth, M., Sweeney, P. F. (2009). *Producing Wrong Data Without Doing Anything Obviously Wrong!* ASPLOS 2009 — về các yếu tố "vô hại" (biến môi trường, thứ tự link) làm lệch kết quả đo.
- Curtsinger, C., Berger, E. D. (2013). *STABILIZER: Statistically Sound Performance Evaluation*. ASPLOS 2013 — về ảnh hưởng của bố trí bộ nhớ lên kết quả benchmark.
- Pydantic — *Pydantic V2 Plan* (2022–2023): các con số 4–50×, ~17×. https://docs.pydantic.dev/2.0/blog/pydantic-v2/

Tài liệu chính thức (tra cứu 10/2026):

- Python docs — `timeit` (khuyến nghị dùng min). https://docs.python.org/3/library/timeit.html
- Pydantic — *Performance tips*. https://docs.pydantic.dev/latest/concepts/performance/
- msgspec — *Benchmarks* và *Structs*. https://jcristharif.com/msgspec/benchmarks.html
- pyperf — công cụ benchmark ổn định cho Python. https://pyperf.readthedocs.io/
- marshmallow. https://marshmallow.readthedocs.io/
- cattrs. https://catt.rs/
