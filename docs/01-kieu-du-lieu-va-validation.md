# Module 01 — Kiểu dữ liệu & validation: nền tảng lý thuyết

> Thời lượng: ~45 phút · Mức độ: Trung bình · Tiên quyết: Module 00

Trước khi viết dòng Pydantic đầu tiên, hãy trả lời một câu hỏi nghe có vẻ triết học: **type hint trong Python có nghĩa là gì?** `def f(x: int)` không ngăn ai gọi `f("abc")`. Trình thông dịch bỏ qua chú thích đó; mypy kiểm tra nó, nhưng chỉ với code mypy nhìn thấy. Còn byte JSON từ máy POS thì không type checker nào nhìn thấy cả. Module này xây nền lý thuyết để hiểu **vì sao cần validation lúc chạy, đặt nó ở đâu, và thiết kế nó đúng** — từ lý thuyết kiểu, gradual typing, đến nguyên lý *parse, don't validate* và an ninh ngôn ngữ (LangSec). Đây là phần "vì sao" cho mọi thứ Pydantic làm ở Module 03–06.

## Mục tiêu học tập

Sau module này, bạn có thể:

1. Định nghĩa kiểu như **tập giá trị + phép toán**, phân biệt static/dynamic, nominal/structural, sound/unsound, và xếp Python vào đúng chỗ.
2. Giải thích **gradual typing**, quan hệ *consistency* với `Any`, vì sao gradual typing *sound* tốn kém (Takikawa et al. 2016) và vì sao Python chọn type hint **bị xóa lúc chạy**.
3. Trích dẫn và diễn giải đúng các bằng chứng thực nghiệm: type checker bắt được khoảng **15%** lỗi (Gao 2017, Khan 2021); tốc độ chấp nhận type hint (Di Grazia & Pradel 2022).
4. Áp dụng **"parse, don't validate"**: viết smart constructor, phân biệt hàm `validate` (trả `bool`) và hàm `parse` (trả kiểu tinh chỉnh).
5. Phân tích một định dạng đầu vào theo **LangSec**: lớp ngôn ngữ trong phân cấp Chomsky, shotgun parsing, parser differential — có thí nghiệm thật trên bốn thư viện JSON.
6. Lập luận khi nào nên **chặt** (strict) và khi nào **lỏng** (lax), dựa trên nguyên lý Postel và phản biện của RFC 9413.
7. Phân tầng các quy tắc của một hóa đơn (cú pháp, cấu trúc, ngữ nghĩa trường, liên trường, ngữ cảnh) và đặt mỗi tầng vào đúng thành phần.

---

## 1. Kiểu là gì

### 1.1. Vấn đề

Trong ngôn ngữ thường ngày, "kiểu" của `total` là "số nguyên". Nhưng một con số tổng tiền hóa đơn còn phải **không âm**, **bằng tổng các dòng**, và **tính bằng VND**. Đâu là "kiểu", đâu là "validation"? Ranh giới đó quyết định cách bạn thiết kế model, nên cần định nghĩa cho rõ.

### 1.2. Định nghĩa

Một cách nhìn đủ dùng cho kỹ sư: **kiểu $T$ là một tập giá trị $\llbracket T \rrbracket$ cùng các phép toán được phép trên tập đó.**

- $\llbracket \texttt{int} \rrbracket = \mathbb{Z}$ (Python có số nguyên không giới hạn).
- $\llbracket \texttt{bool} \rrbracket = \{\texttt{True}, \texttt{False}\}$ — và trong Python $\texttt{bool} \subset \texttt{int}$ (`True + 1 == 2`), một chi tiết sẽ quay lại ở Module 03.
- $\llbracket \texttt{Literal["0","5","8","10","KCT","KKKNT"]} \rrbracket$ là tập 6 chuỗi.
- Kiểu tinh chỉnh (refinement type) $\{ x \in \mathbb{Z} \mid x \ge 0 \}$ — "số nguyên không âm" — là **tập con** của `int` xác định bởi một vị từ.

Với cách nhìn này, ràng buộc `ge=0`, regex của mã số thuế, hay "tổng bằng tổng các dòng" đều là **vị từ thu hẹp tập giá trị**. Phân biệt "kiểu" và "validation" chỉ là phân biệt **vị từ nào hệ thống kiểu của ngôn ngữ biểu diễn được** và vị từ nào phải kiểm tra bằng code. Pydantic xóa nhòa ranh giới này một cách có chủ đích: `Annotated[int, Field(ge=0)]` là một kiểu tinh chỉnh viết bằng cú pháp kiểu.

### 1.3. Các trục phân loại

| Trục | Hai cực | Python ở đâu |
|---|---|---|
| Thời điểm kiểm tra | **static** (trước khi chạy) vs **dynamic** (lúc chạy) | dynamic; type hint là thông tin *tùy chọn* cho công cụ static bên ngoài (mypy, pyright, ty) |
| Mức nghiêm ngặt khi kết hợp kiểu | **strong** vs **weak** (ngầm chuyển đổi) | khá strong: `"1" + 1` lỗi; nhưng `bool` là `int`, `1 == 1.0` |
| Tương thích kiểu dựa vào | **nominal** (tên/khai báo kế thừa) vs **structural** (hình dạng) | cả hai: class là nominal; `Protocol` (PEP 544), `TypedDict` là structural |
| Đảm bảo | **sound** (đã kiểm tra thì không sai kiểu lúc chạy) vs **unsound** | type hint Python **unsound và bị xóa** (erased) — không ảnh hưởng thực thi |

**Soundness** nói nôm na: nếu checker chấp nhận chương trình thì lúc chạy không có lỗi kiểu (các định lý *progress* và *preservation* trong lý thuyết ngôn ngữ). Mypy không sound — một `cast()`, một `# type: ignore`, một thư viện không có stub, một `json.loads` trả `Any` là đủ để giá trị sai kiểu chảy vào code "đã được kiểm tra".

Điểm then chốt cho khóa này: **type hint Python bị xóa về mặt ngữ nghĩa nhưng vẫn còn về mặt dữ liệu.** Chúng không ảnh hưởng thực thi, nhưng được lưu trong `__annotations__` (từ Python 3.14 là đánh giá trễ qua `annotationlib`, PEP 649/749) và đọc được lúc chạy. Pydantic và FastAPI *đọc* chúng để dựng bộ kiểm tra lúc chạy. Đây là một "hợp đồng" giữa hai thế giới:

```python
from typing import Annotated, get_type_hints
from pydantic import Field

class Line:
    quantity: Annotated[float, Field(gt=0)]
    vat_rate: str

print(get_type_hints(Line, include_extras=True))
# {'quantity': typing.Annotated[float, FieldInfo(annotation=NoneType, required=True, metadata=[Gt(gt=0)])],
#  'vat_rate': <class 'str'>}
```

Không có gì được kiểm tra ở đây — Python chỉ lưu lại thông tin. Ai đó (Pydantic) phải biến thông tin ấy thành code kiểm tra.

### 1.4. Nominal và structural trong thực tế

Structural typing quan trọng với API vì JSON **vốn là structural**: một object JSON không mang tên class, chỉ có các khóa. Khi FastAPI nhận `{"sku": ..., "quantity": ...}`, việc gán nó vào `Line` là một **quyết định nominal** do code server đưa ra dựa trên **ngữ cảnh** (endpoint nào, trường nào). Khi một trường có thể là nhiều loại object (thanh toán bằng thẻ hay chuyển khoản), JSON không tự nói nó là loại nào — đó là lý do cần **discriminated union** với một trường "thẻ" (tag) như `"type": "card"` (Module 04). Tagged union là cách đưa thông tin nominal vào dữ liệu structural.

---

## 2. Gradual typing: vì sao Python chọn hint bị xóa

### 2.1. Vấn đề

Ngôn ngữ động muốn thêm kiểu tĩnh mà không bắt viết lại toàn bộ code. Cần một hệ kiểu cho phép **trộn** code có kiểu và không kiểu.

### 2.2. Ý tưởng: kiểu động `?` và quan hệ consistency

Siek & Taha (2006) đề xuất **gradual typing**: thêm một kiểu đặc biệt `?` (trong Python là `Any`), và thay quan hệ bằng nhau giữa kiểu bằng quan hệ **consistency** $\sim$:

$$
\texttt{?} \sim T, \qquad T \sim \texttt{?}, \qquad T \sim T, \qquad \frac{A_1 \sim B_1 \quad A_2 \sim B_2}{A_1 \to A_2 \;\sim\; B_1 \to B_2}.
$$

Điểm tinh tế: $\sim$ **không bắc cầu**. Có `int ~ ?` và `? ~ str` nhưng không có `int ~ str`. Nếu bắc cầu, mọi kiểu đều tương thích với nhau qua `?` và hệ kiểu vô nghĩa. Hệ quả thực tế trong Python: `json.loads` trả `Any`, nên

```python
data = json.loads(raw)          # data: Any
total: int = data["total"]      # mypy chấp nhận: Any ~ int
total + 1                        # lúc chạy có thể là str → TypeError
```

Mọi giá trị đi qua `Any` đều "tắt" kiểm tra tĩnh. Và **mọi dữ liệu từ ngoài vào đều đi qua `Any`** (hoặc `dict[str, Any]`).

### 2.3. Sound gradual typing đắt

Để gradual typing *sound*, ngôn ngữ phải chèn **phép ép kiểu có kiểm tra (cast)** tại mọi chỗ giá trị đi từ vùng không kiểu sang vùng có kiểu; với hàm và cấu trúc mutable, cast phải được bọc lại (wrapper/proxy) và kiểm tra mỗi lần dùng. Takikawa et al. (POPL 2016, *"Is Sound Gradual Typing Dead?"*) đo trên Typed Racket: với mọi cấu hình trộn module có kiểu/không kiểu của một tập benchmark, nhiều cấu hình chậm hơn **hàng chục lần, có trường hợp hơn 100 lần**, và người lập trình khó đoán cấu hình nào chậm. Bauman et al. (OOPSLA 2017, *"Sound Gradual Typing: Only Mostly Dead"*) cho thấy JIT có thể giảm mạnh chi phí này, nhưng không về 0.

<!-- placeholder-spectrum -->

<!-- fig:spectrum -->
<figure markdown="span">
  ![Phổ các cách gõ kiểu theo đảm bảo lúc chạy và chi phí](assets/figures/01/spectrum.light.svg#only-light){ loading=lazy }
  ![Phổ các cách gõ kiểu theo đảm bảo lúc chạy và chi phí](assets/figures/01/spectrum.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 1.1 — Phổ các cách gõ kiểu theo đảm bảo lúc chạy và chi phí. Pydantic đặt cast có kiểm tra đúng một lần tại ranh giới.</figcaption>
</figure>
<!-- /fig -->

### 2.4. Python chọn gì và hệ quả

Python (cùng TypeScript) chọn **optional/erased typing**: hint không ảnh hưởng thực thi, không có cast lúc chạy, chi phí 0, đảm bảo 0. Reticulated Python (Vitousek et al., DLS 2014) từng thử nghiệm ngữ nghĩa *transient* — kiểm tra nông ở biên hàm — nhưng không được đưa vào CPython.

Hệ quả cho người viết API:

1. Type checker giúp nhất quán **bên trong** code của bạn.
2. Ở **ranh giới** (byte từ mạng), type checker mù hoàn toàn. Phải có cast có kiểm tra **viết tay hoặc sinh tự động**.
3. Pydantic chính là "cast có kiểm tra" được đặt **có chủ đích tại ranh giới**, thay vì rải khắp nơi như sound gradual typing. Bên trong vùng chỉ nhận object đã parse, ta có lại phần lớn đảm bảo mà không trả chi phí kiểm tra ở mọi lời gọi hàm.

Đây là một thiết kế kỹ thuật hợp lý: **trả chi phí kiểm tra đúng một lần, ở nơi dữ liệu kém tin cậy nhất.** Module 06 đo chi phí đó: khoảng 30 µs cho một hóa đơn 12 dòng — rẻ hơn nhiều so với một truy vấn database.

---

## 3. Bằng chứng thực nghiệm: kiểu tĩnh bắt được bao nhiêu lỗi?

### 3.1. Ba nghiên cứu

**Gao, Bird & Barr (ICSE 2017), *To Type or Not to Type*.** Lấy các lỗi đã sửa trong dự án JavaScript công khai, thêm chú thích kiểu vào code *trước khi sửa*, rồi hỏi: Flow hoặc TypeScript có báo lỗi không? Kết quả: cả hai bắt được khoảng **15%** số lỗi. Các tác giả lưu ý con số này là cận dưới vì lỗi công khai đã lọt qua test và review.

**Khan, Chen, Varró & McIntosh (IEEE TSE 2021/2022), *An Empirical Study of Type-Related Defects in Python Projects*.** Lặp lại phương pháp trên **210 dự án Python**: mypy có thể đã ngăn khoảng **15%** lỗi. Nguyên nhân lỗi liên quan kiểu phổ biến nhất: gán lại tham chiếu với kiểu khác, khởi tạo thuộc tính động, xử lý `None` sai. Không có khác biệt đáng kể về kinh nghiệm giữa người gây lỗi liên quan kiểu và lỗi khác.

**Di Grazia & Pradel (ESEC/FSE 2022, Distinguished Paper), *The Evolution of Type Annotations in Python*.** Phân tích ~1,4 triệu thay đổi annotation trong 9.655 dự án: tỷ lệ commit có ít nhất một annotation tăng từ **3,8% (2015) lên 10,9% (2021)**; thêm annotation làm lộ thêm lỗi kiểu, và **78,3%** commit được đẩy lên dù checker còn báo lỗi.

<!-- placeholder-evidence -->

<!-- fig:evidence -->
<figure markdown="span">
  ![Trái: tỷ lệ lỗi đã sửa mà type checker phát hiện được (Gao et al](assets/figures/01/evidence.light.svg#only-light){ loading=lazy }
  ![Trái: tỷ lệ lỗi đã sửa mà type checker phát hiện được (Gao et al](assets/figures/01/evidence.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 1.2 — Trái: tỷ lệ lỗi đã sửa mà type checker phát hiện được (Gao et al. 2017; Khan et al. 2021). Phải: tỷ lệ commit có annotation (Di Grazia & Pradel 2022).</figcaption>
</figure>
<!-- /fig -->

### 3.2. Diễn giải đúng

- **15% là nhiều**: một công cụ miễn phí, chạy trong CI, loại được một phần bảy lỗi đã lọt ra ngoài. Nên dùng type checker.
- **15% cũng là ít**: 85% còn lại là lỗi logic, lỗi tích hợp, lỗi dữ liệu. Đặc biệt, **không nghiên cứu nào ở trên đo lỗi do dữ liệu bên ngoài sai hình dạng**, vì type checker không nhìn thấy dữ liệu đó — chúng thuộc một lớp lỗi khác hẳn.
- Với API, lớp lỗi quan trọng nhất (payload sai, thiếu trường, sai đơn vị, số quá lớn) chỉ bị chặn bởi **validation lúc chạy**. Kiểm tra tĩnh và validation lúc chạy **bổ sung** nhau, không thay thế nhau.

Liên hệ Mekong Cloud: CI chạy `pyright --strict` trên toàn bộ service (bắt lỗi bên trong), còn mọi byte vào từ POS/Zendesk/LLM đi qua model Pydantic (bắt lỗi ở biên). Module 12 thiết lập cả hai trong CI.

---

## 4. Parse, don't validate

### 4.1. Vấn đề: validation làm mất thông tin

So sánh hai chữ ký:

```python
def validate_mst(s: str) -> None: ...      # ném lỗi nếu sai, không trả gì
def parse_mst(s: str) -> MST: ...          # trả về kiểu MST nếu đúng, ném lỗi nếu sai
```

Sau `validate_mst(s)`, kiểu của `s` vẫn là `str`. Ba hàm sau nhận `s` không biết nó đã được kiểm tra chưa → hoặc kiểm tra lại (lãng phí, dễ lệch), hoặc tin tưởng (rủi ro nếu có nhánh code bỏ qua bước kiểm tra). Thông tin "đã kiểm tra" **tồn tại trong đầu người viết nhưng không tồn tại trong kiểu**.

Sau `parse_mst(s)`, ta có một giá trị kiểu `MST`. Hàm nào nhận `MST` thì **bằng chính chữ ký của nó** đòi hỏi giá trị đã qua kiểm tra. Kiểu trở thành **bằng chứng** (evidence). Alexis King gói ý tưởng này trong khẩu hiệu *"Parse, don't validate"* (2019): một bộ parse là một hàm từ dữ liệu kém cấu trúc sang dữ liệu nhiều cấu trúc hơn, có thể thất bại; khác với validator, nó **giữ lại** những gì đã học được về dữ liệu dưới dạng kiểu.

<!-- placeholder-parse-vs-validate -->

<!-- fig:parse-vs-validate -->
<figure markdown="span">
  ![Shotgun validation để lại tác dụng phụ dở dang; parse ở cửa từ chối toàn bộ trước khi có bất kỳ tác dụng phụ nào](assets/figures/01/parse-vs-validate.light.svg#only-light){ loading=lazy }
  ![Shotgun validation để lại tác dụng phụ dở dang; parse ở cửa từ chối toàn bộ trước khi có bất kỳ tác dụng phụ nào](assets/figures/01/parse-vs-validate.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 1.3 — Shotgun validation để lại tác dụng phụ dở dang; parse ở cửa từ chối toàn bộ trước khi có bất kỳ tác dụng phụ nào.</figcaption>
</figure>
<!-- /fig -->

### 4.2. Smart constructor trong Python

Trong ngôn ngữ có kiểu tĩnh mạnh, ta ẩn constructor để chỉ có thể tạo `MST` qua hàm parse. Python không ẩn được hoàn toàn, nhưng làm được đủ tốt:

```python
from typing import Annotated, NewType
from pydantic import AfterValidator, TypeAdapter

WEIGHTS = (31, 29, 23, 19, 17, 13, 7, 5, 3)

def _check_mst(s: str) -> str:
    s = s.replace("-", "").replace(" ", "")
    if len(s) not in (10, 13) or not s.isdigit():
        raise ValueError("MST phải có 10 hoặc 13 chữ số")
    total = sum(w * int(c) for w, c in zip(WEIGHTS, s))
    if str(10 - total % 11) != s[9]:
        raise ValueError("MST sai chữ số kiểm tra")
    return s

MST = Annotated[str, AfterValidator(_check_mst)]   # kiểu tinh chỉnh: str thỏa vị từ
parse_mst = TypeAdapter(MST).validate_python       # smart constructor

print(parse_mst("0100233488"))        # '0100233488'
print(parse_mst("0314409058-002"))    # '0314409058002'
parse_mst("0100233480")               # ValidationError: MST sai chữ số kiểm tra
```

Chữ số kiểm tra của MST (cùng thuật toán với thư viện python-stdnum): nhân 9 chữ số đầu với trọng số $(31, 29, 23, 19, 17, 13, 7, 5, 3)$, chữ số thứ 10 phải bằng $10 - (\Sigma \bmod 11)$. Ví dụ `0100233488`:

$$
0\cdot31 + 1\cdot29 + 0\cdot23 + 0\cdot19 + 2\cdot17 + 3\cdot13 + 3\cdot7 + 4\cdot5 + 8\cdot3 = 167, \quad 167 \bmod 11 = 2, \quad 10 - 2 = 8. \checkmark
$$

Chú ý biên: nếu $\Sigma \bmod 11 = 0$ thì $10 - 0 = 10$ — không phải một chữ số, nên **mọi tiền tố 9 chữ số có tổng chia hết cho 11 không thể là MST hợp lệ**. Đây là loại góc khuất mà property-based testing tìm ra rất giỏi (Module 12, Lab 05).

Với `MST` là một kiểu, mọi model dùng nó (`seller_tax_code: MST`, `buyer.tax_code: MST | None`) đều tự động kiểm tra — một định nghĩa, nhiều nơi dùng. Đó là "parse, don't validate" theo phong cách Pydantic: **đặt quy tắc vào kiểu, không vào hàm xử lý.**

### 4.3. "Làm cho trạng thái phi pháp không biểu diễn được"

Nguyên tắc anh em (Yaron Minsky, cộng đồng OCaml): thiết kế kiểu sao cho tổ hợp giá trị vô nghĩa **không thể được tạo ra**. Ví dụ thanh toán:

```python
# Dễ sai: 4 trường optional → 16 tổ hợp, chỉ 2 tổ hợp có nghĩa
class Payment(BaseModel):
    method: str
    card_last4: str | None = None
    bank_code: str | None = None
    transfer_ref: str | None = None

# Đúng: union có thẻ → chỉ 2 hình dạng hợp lệ tồn tại
class Card(BaseModel):
    method: Literal["card"]
    card_last4: Annotated[str, Field(pattern=r"^\d{4}$")]

class Transfer(BaseModel):
    method: Literal["transfer"]
    bank_code: str
    transfer_ref: str

Payment = Annotated[Card | Transfer, Field(discriminator="method")]
```

Số trạng thái biểu diễn được giảm từ $2^3 \times |\texttt{str}|$ tổ hợp xuống đúng hai hình dạng. Module 04 đi sâu discriminated union và chi phí của nó.

---

## 5. LangSec: đầu vào là một ngôn ngữ

### 5.1. Vấn đề

Phần lớn lỗ hổng bảo mật lớn (Heartbleed, các lỗi parse chứng chỉ X.509, request smuggling) có chung một gốc: **code xử lý đầu vào trước khi đầu vào được nhận dạng đầy đủ**, hoặc **hai thành phần hiểu cùng một đầu vào theo hai cách khác nhau**.

### 5.2. Ý tưởng

Nhóm **Language-theoretic Security** (Sassaman, Patterson, Bratus, Locasto, Shubina — báo cáo kỹ thuật Dartmouth 2011, sau đó đăng ở IEEE Systems Journal) đề xuất nhìn đầu vào như một **ngôn ngữ hình thức** và bộ xử lý đầu vào như một **máy nhận dạng** (recognizer). Các nguyên tắc chính, diễn đạt lại:

1. **Định nghĩa ngôn ngữ đầu vào một cách tường minh** (grammar/schema), không để nó "trồi lên" từ code.
2. **Nhận dạng đầy đủ trước khi xử lý** — từ chối toàn bộ đầu vào không thuộc ngôn ngữ, ngay tại cửa. Ngược lại là **shotgun parsing**: kiểm tra rải rác lẫn vào logic, nên khi phát hiện dữ liệu sai thì một phần xử lý đã chạy rồi.
3. **Dùng lớp ngôn ngữ đơn giản nhất đủ dùng** (nguyên lý sức mạnh tính toán tối thiểu): đầu vào càng gần lớp chính quy/phi ngữ cảnh, việc nhận dạng càng quyết định được và kiểm chứng được.
4. **Tránh parser differential**: mọi thành phần phải hiểu cùng một đầu vào như nhau.

<!-- placeholder-chomsky -->

<!-- fig:chomsky -->
<figure markdown="span">
  ![Các quy tắc của hóa đơn trên phân cấp Chomsky và bộ nhận dạng tương ứng](assets/figures/01/chomsky.light.svg#only-light){ loading=lazy }
  ![Các quy tắc của hóa đơn trên phân cấp Chomsky và bộ nhận dạng tương ứng](assets/figures/01/chomsky.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 1.4 — Các quy tắc của hóa đơn trên phân cấp Chomsky và bộ nhận dạng tương ứng.</figcaption>
</figure>
<!-- /fig -->

### 5.3. Xếp các quy tắc hóa đơn vào phân cấp Chomsky

| Quy tắc | Lớp ngôn ngữ | Bộ nhận dạng |
|---|---|---|
| MST: 10 hoặc 13 chữ số | chính quy | regex `^\d{10}(\d{3})?$` |
| Chữ số kiểm tra MST | chính quy (tập hữu hạn tiền tố × phần dư mod 11, có automaton hữu hạn) — nhưng viết bằng code số học dễ đọc hơn | hàm Python ngắn |
| Cú pháp JSON | phi ngữ cảnh (cần ngăn xếp cho ngoặc lồng nhau) | parser JSON (jiter) |
| Cấu trúc hóa đơn (trường, kiểu, độ dài) | phi ngữ cảnh + ràng buộc từng trường | JSON Schema / Pydantic core schema |
| Tổng = Σ dòng | vượt phi ngữ cảnh (cần so sánh số học giữa các phần xa nhau) | code (model validator) |
| Số hóa đơn chưa tồn tại; MST thuộc tenant | phụ thuộc trạng thái ngoài | database (unique constraint, truy vấn) |

Bảng này cho một quy tắc thiết kế thực dụng: **mỗi tầng quy tắc dùng bộ nhận dạng yếu nhất đủ dùng**, và các tầng chạy theo thứ tự từ rẻ đến đắt. Pydantic sắp xếp đúng như vậy: parse JSON (Rust) → kiểu và ràng buộc trường (Rust) → validator Python của bạn → (ngoài Pydantic) kiểm tra với database.

### 5.4. Thí nghiệm: parser differential trên bốn thư viện JSON

RFC 8259 nói tên khóa trong object JSON **nên** (SHOULD) là duy nhất và hành vi khi trùng là không đoán trước được; không giới hạn độ lớn số. Mình cho cùng một chuỗi byte đi qua bốn bộ parse đang có trong venv của khóa (Python 3.13, chạy thật):

| Đầu vào | `json.loads` | `orjson` | `msgspec` | Pydantic (`TypeAdapter(Any)`, jiter) |
|---|---|---|---|---|
| `{"total": 1, "total": 999}` | `999` | `999` | `999` | `999` |
| `{"total": 18446744073709551616}` (2⁶⁴) | int chính xác | **`1.8446744073709552e+19` (float, mất chính xác)** | int chính xác | int chính xác |
| `{"total": 1e400}` | `inf` | lỗi | lỗi | `inf` |
| `{"total": NaN}` (không phải JSON chuẩn) | `nan` | lỗi | lỗi | `nan` |
| BOM UTF-8 ở đầu | chấp nhận | lỗi | lỗi | lỗi |
| `"\ud800"` (surrogate lẻ) | chấp nhận | lỗi | lỗi | lỗi |
| dấu phẩy thừa `{"total": 1,}` | lỗi | lỗi | lỗi | lỗi |

<!-- placeholder-differential -->

<!-- fig:differential -->
<figure markdown="span">
  ![Kết quả chạy thật bảng ở mục 5](assets/figures/01/differential.light.svg#only-light){ loading=lazy }
  ![Kết quả chạy thật bảng ở mục 5](assets/figures/01/differential.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 1.5 — Kết quả chạy thật bảng ở mục 5.4: các ô vàng là chỗ bộ parse nhận dữ liệu phi chuẩn hoặc đổi nghĩa — nguồn gốc của parser differential.</figcaption>
</figure>
<!-- /fig -->

Đọc bảng như một kỹ sư bảo mật:

- Nếu cổng API dùng `orjson` để log/định tuyến còn service xử lý dùng Pydantic, một tổng tiền $2^{64}$ được **hiểu thành hai số khác nhau** ở hai chỗ — một parser differential kinh điển.
- `json.loads` và Pydantic (với kiểu `Any`/`float`) chấp nhận `NaN`/`inf` — **không phải JSON hợp lệ** theo RFC 8259. Với trường tiền, phải dùng kiểu `int` hoặc ràng buộc `allow_inf_nan=False` (Module 03).
- Khóa trùng: cả bốn lấy giá trị **cuối**. Nhất quán ở đây, nhưng một proxy/WAF viết bằng ngôn ngữ khác có thể lấy giá trị **đầu** — kẻ tấn công gửi `{"role": "user", "role": "admin"}` để WAF thấy `user`, backend thấy `admin`.

Bài học LangSec áp vào FastAPI: **một ranh giới, một bộ parse.** Đừng parse request body hai lần bằng hai thư viện khác nhau (ví dụ middleware log dùng `json.loads`, handler dùng Pydantic) rồi đưa ra quyết định dựa trên cả hai kết quả.

---

## 6. Nguyên lý Postel và cái giá của sự dễ dãi

### 6.1. Phát biểu

Nguyên lý robustness (Jon Postel, thường tóm là "*bảo thủ khi gửi, dễ dãi khi nhận*") giúp Internet thời đầu vận hành dù các cài đặt không hoàn hảo.

### 6.2. Phản biện của RFC 9413

RFC 9413 (*Maintaining Robust Protocols*, IAB 2023, Thomson & Schinazi) lập luận rằng áp dụng nguyên lý này quá rộng làm **giao thức suy thoái**: khi bên nhận chấp nhận dữ liệu lệch chuẩn, bên gửi không bao giờ sửa; "ngôn ngữ thực tế" của giao thức phình ra so với đặc tả, và mọi cài đặt mới phải bắt chước cả những lệch chuẩn đó. Tài liệu đề xuất thay vào đó là **bảo trì giao thức chủ động**: báo lỗi rõ ràng, sửa bên gửi, giữ đặc tả và thực tế khớp nhau.

<!-- placeholder-postel -->

<!-- fig:postel -->
<figure markdown="span">
  ![Tập đầu vào được chấp nhận ở chế độ strict và lax; phần chênh lệch là nơi cần quyết định thiết kế](assets/figures/01/postel.light.svg#only-light){ loading=lazy }
  ![Tập đầu vào được chấp nhận ở chế độ strict và lax; phần chênh lệch là nơi cần quyết định thiết kế](assets/figures/01/postel.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 1.6 — Tập đầu vào được chấp nhận ở chế độ strict và lax; phần chênh lệch là nơi cần quyết định thiết kế.</figcaption>
</figure>
<!-- /fig -->

### 6.3. Áp vào thiết kế API: lax hay strict?

Pydantic có hai chế độ (chi tiết ở Module 03):

- **Lax** (mặc định): chuyển đổi "an toàn" — chuỗi `"42"` thành `42` cho trường `int`, `42.0` thành `42`, chuỗi ISO thành `datetime`.
- **Strict**: chỉ nhận đúng kiểu JSON tương ứng — trường `int` chỉ nhận số nguyên JSON.

Gọi $A_{\text{strict}}$ và $A_{\text{lax}}$ là tập đầu vào được chấp nhận; ta có $A_{\text{strict}} \subset A_{\text{lax}}$, và hai chế độ cho **cùng kết quả** trên $A_{\text{strict}}$. Câu hỏi thiết kế là: những đầu vào trong $A_{\text{lax}} \setminus A_{\text{strict}}$ có **một cách hiểu duy nhất, hiển nhiên** không?

- Query string, path, header, form: mọi thứ **vốn là chuỗi** trên đường truyền. `?page=2` buộc phải chuyển `"2"` → `2`. Lax là đúng — FastAPI dựa vào điều này.
- JSON body của **dữ liệu tài chính**: `"amount": "82500"` (chuỗi) hay `"amount": 82500.0` (float) nhiều khả năng là **lỗi tích hợp phía client**. Chấp nhận nó là "dễ dãi kiểu Postel": client không bao giờ sửa, và một ngày `"82.500"` (dấu chấm phân cách nghìn kiểu Việt Nam) được hiểu thành `82.5`. Với `invoice-api`, mình khuyên **strict cho body**, lax cho tham số trên URL.

---

## 7. Validation như một hàm: các tính chất cần có

### 7.1. Hình thức hóa

Gọi $B$ là tập chuỗi byte, $T$ là kiểu đích, $E$ là tập danh sách lỗi. Một bộ parse là hàm toàn phần

$$
\mathrm{parse}_T : B \to T \uplus E.
$$

Gọi $V \subseteq B$ là tập đầu vào "hợp lệ theo đặc tả". Ta muốn:

- **Sound (an toàn):** $\mathrm{parse}_T(b) \in T \Rightarrow b \in V$ — không chấp nhận dữ liệu sai.
- **Complete (đầy đủ):** $b \in V \Rightarrow \mathrm{parse}_T(b) \in T$ — không từ chối dữ liệu đúng.
- **Round-trip:** với mọi $x \in T$, $\mathrm{parse}_T(\mathrm{serialize}_T(x)) = x$ — dữ liệu mình tự xuất ra phải đọc lại được (Module 05, kiểm thử bằng property-based ở Module 12).
- **Tất định và toàn phần:** không treo, không ném ngoại lệ "lạ" ngoài $E$, thời gian bị chặn theo kích thước đầu vào (chống DoS, Module 11).

Sound mà không complete → khách hàng hợp lệ bị từ chối (mất doanh thu). Complete mà không sound → dữ liệu sai lọt vào (mất tiền, mất an toàn). Trade-off giữa chúng chính là lựa chọn lax/strict ở trên.

### 7.2. Gom lỗi: fail-fast hay tích lũy?

Hai chiến lược khi gặp lỗi:

- **Fail-fast (kiểu monad):** dừng ở lỗi đầu tiên. Rẻ, nhưng client sửa xong lỗi 1 mới thấy lỗi 2 — một hóa đơn 12 dòng sai 5 chỗ cần 5 vòng gửi–sửa.
- **Tích lũy (kiểu applicative):** kiểm tra các trường **độc lập** song song về mặt logic và trả **tất cả** lỗi, mỗi lỗi có vị trí (`loc`). Pydantic làm như vậy với các trường cùng cấp; chỉ những bước **phụ thuộc** (model validator `after` cần mọi trường đã hợp lệ) mới bị bỏ qua khi có lỗi trước đó.

```python
from pydantic import BaseModel, Field, ValidationError
from typing import Annotated

class Line(BaseModel):
    quantity: Annotated[float, Field(gt=0)]
    unit_price: Annotated[int, Field(ge=0)]

try:
    Line.model_validate({"quantity": -1, "unit_price": "abc"})
except ValidationError as e:
    for err in e.errors():
        print(err["loc"], err["type"], err["msg"])
# ('quantity',) greater_than Input should be greater than 0
# ('unit_price',) int_parsing Input should be a valid integer, unable to parse string as an integer
```

Hai lỗi độc lập, trả cùng lúc, mỗi lỗi có `loc` và `type` máy đọc được. Module 03 phân tích cấu trúc lỗi và cách biến nó thành response 422 thân thiện.

<!-- placeholder-accumulate -->

<!-- fig:accumulate -->
<figure markdown="span">
  ![Số lượt gửi–sửa của client theo số lỗi độc lập trong payload: fail-fast so với tích lũy lỗi](assets/figures/01/accumulate.light.svg#only-light){ loading=lazy }
  ![Số lượt gửi–sửa của client theo số lỗi độc lập trong payload: fail-fast so với tích lũy lỗi](assets/figures/01/accumulate.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 1.7 — Số lượt gửi–sửa của client theo số lỗi độc lập trong payload: fail-fast so với tích lũy lỗi.</figcaption>
</figure>
<!-- /fig -->

---

## 8. Case Mekong Cloud: phân tầng quy tắc của một hóa đơn

Gom tất cả lại, các quy tắc của `POST /v1/invoices` chia thành **năm tầng**, mỗi tầng có bộ nhận dạng và vị trí thực thi riêng:

<!-- placeholder-layers -->

<!-- fig:layers -->
<figure markdown="span">
  ![Năm tầng quy tắc của POST /v1/invoices, nơi thực thi và chi phí điển hình của từng tầng](assets/figures/01/layers.light.svg#only-light){ loading=lazy }
  ![Năm tầng quy tắc của POST /v1/invoices, nơi thực thi và chi phí điển hình của từng tầng](assets/figures/01/layers.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 1.8 — Năm tầng quy tắc của POST /v1/invoices, nơi thực thi và chi phí điển hình của từng tầng.</figcaption>
</figure>
<!-- /fig -->

| Tầng | Ví dụ | Thực thi ở đâu | Chi phí điển hình |
|---|---|---|---|
| 0. Giới hạn vận chuyển | body ≤ 2 MB, `Content-Type: application/json` | reverse proxy / middleware (Module 11) | ~0 |
| 1. Cú pháp | JSON hợp lệ, UTF-8 hợp lệ | parser JSON trong Pydantic (Rust) | ~1 µs/KB |
| 2. Cấu trúc & trường | đủ trường, đúng kiểu, `quantity > 0`, MST đúng regex, `vat_rate` ∈ tập 6 giá trị | core schema Pydantic (Rust) | chục µs |
| 3. Ngữ nghĩa trong object | chữ số kiểm tra MST, `amount = round(qty × price)`, tổng khớp | validator Python của model | chục µs |
| 4. Ngữ cảnh & trạng thái | MST người bán thuộc tenant của token; số hóa đơn chưa dùng; idempotency key | dependency + database (Module 08, 10) | ms |

Quy tắc vàng: **tầng rẻ chạy trước, tầng đắt chạy sau, và mỗi tầng chỉ nhận đầu ra đã qua tầng trước.** Một payload 50 MB bị chặn ở tầng 0 trước khi tốn một micro-giây parse; một MST sai checksum bị chặn ở tầng 3 trước khi tốn một round-trip database. Tầng 4 không thuộc Pydantic — đặt kiểm tra cần database vào validator Pydantic là một anti-pattern (validator trở nên chậm, khó test, và chạy cả khi bạn chỉ muốn parse dữ liệu đã tin cậy).

---

## Lỗi thường gặp & cách xử lý

| Triệu chứng | Nguyên nhân gốc | Cách xử lý |
|---|---|---|
| Code "đã có type hint" vẫn `TypeError` lúc chạy với dữ liệu từ API | Hint bị xóa; dữ liệu đi vào qua `Any` (`json.loads`, `request.json()`) | Parse ở biên bằng model Pydantic; không truyền `dict` thô vào trong |
| Cùng một quy tắc (MST hợp lệ) được kiểm tra ở 5 chỗ, mỗi chỗ một kiểu | Validate thay vì parse; quy tắc nằm trong hàm, không trong kiểu | Định nghĩa kiểu `MST = Annotated[str, AfterValidator(...)]`, dùng lại mọi nơi |
| Khách gửi `"82.500"` thành 82,5 đồng | Lax mode chấp nhận chuỗi số cho trường tiền | Strict cho body tài chính; tiền là `int` VND |
| WAF chặn nhưng backend vẫn bị khai thác | Parser differential (khóa trùng, số lớn, encoding) | Một ranh giới, một bộ parse; từ chối khóa trùng nếu cần (validator `wrap` ở mức raw) |
| Client phải gửi lại 5 lần mới sửa hết lỗi | Fail-fast; lỗi không có vị trí | Trả toàn bộ lỗi có `loc` (mặc định của Pydantic), map sang 422 có cấu trúc |
| Validator gọi database, test chậm và flaky | Trộn tầng 4 vào tầng 3 | Validator chỉ kiểm tra thuần dữ liệu; kiểm tra trạng thái ở dependency/service |

## Tóm tắt (cheat-sheet)

- Kiểu = tập giá trị + phép toán; ràng buộc là **kiểu tinh chỉnh** (tập con xác định bởi vị từ).
- Python: dynamic, khá strong, nominal + structural, hint **unsound và bị xóa** nhưng **đọc được lúc chạy** → Pydantic/FastAPI dùng chính chúng.
- Gradual typing: `Any` tương thích mọi kiểu, quan hệ **không bắc cầu**; sound gradual typing cần cast ở mọi biên → đắt (Takikawa 2016). Python chọn chi phí 0 + đặt cast có kiểm tra **tại ranh giới** (Pydantic).
- Type checker bắt ~**15%** lỗi (Gao 2017, Khan 2021) — đáng dùng, nhưng mù với dữ liệu ngoài.
- **Parse, don't validate**: trả kiểu tinh chỉnh làm bằng chứng; đặt quy tắc vào kiểu; làm trạng thái phi pháp không biểu diễn được (tagged union).
- **LangSec**: định nghĩa ngôn ngữ đầu vào, nhận dạng đủ trước khi xử lý, dùng lớp ngôn ngữ yếu nhất đủ dùng, tránh parser differential (thí nghiệm: 2⁶⁴, NaN, BOM khác nhau giữa 4 thư viện).
- **RFC 9413**: dễ dãi kiểu Postel làm giao thức suy thoái → strict cho body tài chính, lax cho tham số URL.
- Bộ parse tốt: sound, complete, round-trip, toàn phần; **tích lũy lỗi** có `loc`.
- Năm tầng quy tắc: vận chuyển → cú pháp → cấu trúc → ngữ nghĩa → ngữ cảnh; rẻ trước, đắt sau.

## Câu hỏi tự kiểm tra / phỏng vấn

1. Vì sao quan hệ consistency trong gradual typing không được bắc cầu? Cho ví dụ hậu quả nếu nó bắc cầu.

    <details markdown="1"><summary>Gợi ý</summary>
    Nếu bắc cầu, từ `int ~ Any` và `Any ~ str` suy ra `int ~ str`, mọi kiểu tương thích mọi kiểu, checker không còn phát hiện được gì. Tính không bắc cầu giữ cho `Any` là "lỗ hổng cục bộ" chứ không làm sụp cả hệ kiểu.
    </details>

2. Type hint Python "bị xóa" nghĩa là gì, và tại sao Pydantic vẫn dùng được chúng?

    <details markdown="1"><summary>Gợi ý</summary>
    Hint không ảnh hưởng ngữ nghĩa thực thi (không có kiểm tra/cast tự động), nhưng vẫn được lưu dưới dạng dữ liệu (`__annotations__`, `get_type_hints`, `annotationlib` từ 3.14). Pydantic đọc chúng lúc định nghĩa class để sinh core schema và dựng validator.
    </details>

3. "Mypy bắt được 15% lỗi" — hãy diễn giải con số này cho một người quản lý đang hỏi "vậy có cần validation nữa không".

    <details markdown="1"><summary>Gợi ý</summary>
    15% lỗi đã lọt ra ngoài là đáng kể và chi phí thấp → nên dùng. Nhưng các nghiên cứu đo lỗi trong code, không đo dữ liệu bên ngoài; type checker không nhìn thấy byte từ mạng. Validation ở biên chặn một lớp lỗi khác (payload sai hình dạng/ngữ nghĩa). Hai thứ bổ sung nhau.
    </details>

4. Viết lại `def is_valid_email(s: str) -> bool` theo tinh thần "parse, don't validate". Lợi ích cụ thể là gì?

    <details markdown="1"><summary>Gợi ý</summary>
    `Email = Annotated[str, AfterValidator(check_email)]` hoặc `def parse_email(s) -> Email`. Hàm gửi mail nhận `Email` thay vì `str`, nên không thể gọi với chuỗi chưa kiểm tra; kiểm tra một lần, chuẩn hóa (lowercase domain) một lần.
    </details>

5. Shotgun parsing là gì? Chỉ ra một đoạn code shotgun parsing điển hình trong một handler FastAPI viết sai.

    <details markdown="1"><summary>Gợi ý</summary>
    Kiểm tra đầu vào rải rác lẫn với logic xử lý. Ví dụ handler nhận `request: Request`, `data = await request.json()`, rồi `if "lines" in data:` … ghi DB từng dòng, giữa chừng mới phát hiện dòng 7 thiếu `quantity` → đã ghi 6 dòng. Sửa: khai báo body là model `Invoice`, FastAPI parse toàn bộ trước khi gọi handler.
    </details>

6. Trong thí nghiệm parser differential, kịch bản tấn công nào khai thác được việc `orjson` đọc 2⁶⁴ thành float?

    <details markdown="1"><summary>Gợi ý</summary>
    Một thành phần (cổng hạn mức, log, kiểm tra gian lận) dùng orjson thấy `1.8446744073709552e19` (đã làm tròn), thành phần khác dùng parser giữ int chính xác thấy số khác. Với số gần biên (ví dụ hạn mức), hai bên có thể đưa ra hai quyết định ngược nhau. Phòng: giới hạn độ lớn số ở schema (`le=...`), một bộ parse duy nhất.
    </details>

7. Khi nào lax mode là lựa chọn đúng? Khi nào nó là "dễ dãi kiểu Postel" có hại?

    <details markdown="1"><summary>Gợi ý</summary>
    Đúng khi đường truyền vốn là chuỗi (path, query, header, form, biến môi trường) và chuyển đổi có một cách hiểu duy nhất. Có hại khi đường truyền có kiểu (JSON) và chuyển đổi che giấu lỗi tích hợp của client, nhất là dữ liệu tiền/số lượng.
    </details>

8. Định nghĩa sound và complete cho một bộ parse. Trong `invoice-api`, vi phạm cái nào nguy hiểm hơn?

    <details markdown="1"><summary>Gợi ý</summary>
    Sound: chấp nhận ⇒ hợp lệ; complete: hợp lệ ⇒ chấp nhận. Vi phạm sound (chấp nhận hóa đơn sai tổng/sai MST) nguy hiểm hơn: hóa đơn sai gửi lên cơ quan thuế khó sửa (phải lập hóa đơn điều chỉnh). Vi phạm complete gây phiền nhưng client thấy lỗi ngay và sửa được.
    </details>

9. Vì sao không nên kiểm tra "số hóa đơn chưa tồn tại" bên trong model validator của Pydantic?

    <details markdown="1"><summary>Gợi ý</summary>
    Đó là quy tắc tầng 4 phụ thuộc trạng thái ngoài: cần I/O (chậm, có thể lỗi mạng), không tất định, và có race condition (hai request cùng kiểm tra rồi cùng ghi). Đúng chỗ là unique constraint trong database + xử lý lỗi vi phạm, hoặc dependency/service.
    </details>

10. Mars Climate Orbiter mất vì sai đơn vị dù dữ liệu "đúng kiểu float". Thiết kế kiểu nào giảm rủi ro tương tự trong `invoice-api`?

    <details markdown="1"><summary>Gợi ý</summary>
    Kiểu tiền riêng (`VND = Annotated[int, Field(ge=0)]`, hoặc model `Money(amount: int, currency: Literal["VND"])`), không dùng `float` cho tiền; tên trường mang đơn vị (`unit_price_vnd`); thuế suất là `Literal` thay vì số thực "0.08 hay 8?".
    </details>

## Bài tập thực hành

1. **Smart constructor cho MST (CPU, 15 phút).** Mở rộng `MST` ở mục 4.2: chuẩn hóa dấu `-`, `.` và khoảng trắng; từ chối chuỗi có `0000000` ở vị trí 3–9 và nhánh `000`. Viết 10 test bằng `pytest` gồm cả trường hợp $\Sigma \bmod 11 = 0$. (Lab 01 có lời giải.)
2. **Tái lập thí nghiệm parser differential (CPU, 10 phút).** Chạy bảng ở mục 5.4 với Python của bạn, thêm hai trường hợp: số thực `0.1e-400` và chuỗi có ký tự NUL `"\u0000"`. Ghi lại thư viện nào khác biệt.
3. **Phân tầng quy tắc (giấy, 15 phút).** Lấy một API bạn từng làm (ví dụ form đăng ký của app Rails) và xếp mọi quy tắc vào năm tầng ở mục 8. Có quy tắc nào đang nằm sai tầng không?
4. **Đọc paper (60 phút).** Đọc phần 1–3 của *Is Sound Gradual Typing Dead?* hoặc *To Type or Not to Type* và tóm tắt phương pháp đo trong 10 dòng: biến độc lập, biến phụ thuộc, mối đe dọa tính hợp lệ.

## Tài liệu tham khảo

Paper:

- Siek, J. G., Taha, W. (2006). *Gradual Typing for Functional Languages*. Scheme and Functional Programming Workshop 2006.
- Vitousek, M. M., Kent, A. M., Siek, J. G., Baker, J. (2014). *Design and Evaluation of Gradual Typing for Python*. DLS 2014.
- Takikawa, A., Feltey, D., Greenman, B., New, M. S., Vitek, J., Felleisen, M. (2016). *Is Sound Gradual Typing Dead?* POPL 2016. https://users.cs.northwestern.edu/~dmf082/papers/popl16-tfgnvf.pdf
- Bauman, S., Bolz-Tereick, C. F., Siek, J., Tobin-Hochstadt, S. (2017). *Sound Gradual Typing: Only Mostly Dead*. OOPSLA 2017.
- Gao, Z., Bird, C., Barr, E. T. (2017). *To Type or Not to Type: Quantifying Detectable Bugs in JavaScript*. ICSE 2017, pp. 758–769. https://ieeexplore.ieee.org/document/7985711/
- Khan, F., Chen, B., Varró, D., McIntosh, S. (2021). *An Empirical Study of Type-Related Defects in Python Projects*. IEEE TSE 48(8). DOI 10.1109/TSE.2021.3082068. https://rebels.cs.uwaterloo.ca/papers/tse2021_khan.pdf
- Di Grazia, L., Pradel, M. (2022). *The Evolution of Type Annotations in Python: An Empirical Study*. ESEC/FSE 2022 (Distinguished Paper). https://2022.esec-fse.org/details/fse-2022-research-papers/36/The-Evolution-of-Type-Annotations-in-Python-An-Empirical-Study
- Sassaman, L., Patterson, M. L., Bratus, S., Locasto, M. E., Shubina, A. (2011). *Security Applications of Formal Language Theory*. Dartmouth TR2011-709 (bản tạp chí: IEEE Systems Journal, 2013). https://digitalcommons.dartmouth.edu/cs_tr/335

Bài viết, tiêu chuẩn và tài liệu chính thức:

- King, A. (2019). *Parse, don't validate*. https://lexi-lambda.github.io/blog/2019/11/05/parse-don-t-validate/
- Thomson, M., Schinazi, D. (2023). *RFC 9413: Maintaining Robust Protocols*. https://www.rfc-editor.org/rfc/rfc9413
- Bray, T. (2017). *RFC 8259: The JavaScript Object Notation (JSON) Data Interchange Format*. https://www.rfc-editor.org/rfc/rfc8259
- LangSec — tổng quan và danh mục paper. https://www.cs.dartmouth.edu/~sergey/langsec/
- PEP 484 (Type Hints), PEP 544 (Protocols), PEP 593 (Annotated), PEP 649/749 (đánh giá annotation trễ). https://peps.python.org/
- Python docs — `annotationlib`. https://docs.python.org/3/library/annotationlib.html
- python-stdnum — `stdnum.vn.mst`. https://arthurdejong.org/python-stdnum/doc/stdnum.vn.mst
