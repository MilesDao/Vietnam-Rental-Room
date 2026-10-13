# Kế hoạch chuyển trọng tâm: dự đoán giá (ML) là chính, recommender là ứng dụng

**Ngày lập:** 2026-10-07 · **Mục tiêu:** bài thi *Fundamentals of Data Science – Final Project* · **Thay thế phần "Phase 6" của `docs/PLAN.md`.**
Báo cáo hiện tại: `docs/latex/report.tex` (23 trang). Số liệu: `docs/report_numbers.json`.

## 0. Nguyên tắc (không thương lượng vì bài đi thi)

1. **Không giả mạo người dùng thật.** Phiếu do tôi hoặc một mô hình "đóng vai người dùng" tạo ra là **mô phỏng**, không phải dữ liệu người dùng. Nó
   không được trình bày như khảo sát thật, trong báo cáo, slide hay lúc vấn đáp. Làm vậy là gian lận học thuật và hội đồng hỏi một câu là lộ.
   Những gì được phép: (a) phân tích độ nhạy có nhãn "mô phỏng"; (b) **dữ liệu người thật do nhóm tự thu** (xem Phần C).
2. Mọi số trong báo cáo phải sinh ra từ code và nằm trong `docs/report_numbers.json`.
3. Nhãn do AI gán luôn ghi rõ là do AI gán (đã làm).
4. Không sửa kết quả cho đẹp: nếu mô hình mới không thắng, báo cáo nói đúng như vậy.
5. Dữ liệu cá nhân: giữ nguyên quy tắc băm số điện thoại, không đưa dữ liệu thô vào repo.

## 1. Câu chuyện mới

**Tên gợi ý:** *Estimating Fair Rents of Rooms in Hanoi: Data Collection, Price Prediction and a Value-Aware Search.*
**Luận điểm:** (1) dữ liệu thô về nhà trọ rất bẩn và sửa được; (2) một mô hình học máy dự đoán giá niêm yết tốt hơn quy tắc trung vị, và ta đo được
chính xác bao nhiêu và vì sao sai; (3) mô hình giá hợp lý có thể dùng trong một công cụ tìm kiếm có xếp hạng (ứng dụng, chưa kiểm chứng với người dùng).

**Trong báo cáo:** phần ML (§3 mới) nặng 40%, dữ liệu 25%, đánh giá và phân tích lỗi 20%, ứng dụng recommender 10%, thảo luận 5%.

## 2. Các giai đoạn

### Phần A: Thí nghiệm ML cho dự đoán giá (code + số liệu)
Tất cả trong một module mới `src/recsys/price_experiments.py` (đọc `data/unified_hanoi_rentals_dedup.csv`, ghi vào `docs/report_numbers.json`,
mục `price_experiments`). Mọi so sánh dùng cùng các fold nhóm (poster/ô 50 m) và bootstrap theo cụm.

| # | Việc | Chi tiết | Xong khi |
|---|---|---|---|
| A1 | **Định nghĩa nhãn và xử lý nhiễu** | Phát hiện giá theo đầu người/giường, giá mồi, khoảng giá, nhà nguyên căn bị gắn "phòng"; gắn cờ bằng luật + từ khoá (tái dùng `SHARED_RE`); thí nghiệm: huấn luyện trên dữ liệu thô vs đã lọc, **chấm trên cùng tập kiểm thử đã lọc** | Bảng: MAPE trước/sau; số tin bị gắn cờ theo lý do |
| A2 | **So sánh nhiều mô hình** | Baseline trung vị; Ridge/ElasticNet (one-hot + log); k-NN; Random Forest; ExtraTrees; GradientBoosting; HistGradientBoosting (hiện tại); thêm đặc trưng văn bản (TF-IDF→SVD hoặc Ridge trên TF-IDF rồi stack) | Bảng 8+ mô hình: MAPE, MAE, RMSE log, R², median APE, % trong ±15% và ±25%, khoảng tin cậy |
| A3 | **Tinh chỉnh siêu tham số** | Random search có ngân sách cố định, trong vòng lặp ngoài fold nhóm (nested); báo cả khoảng thời gian chạy | Bảng tham số tối ưu; kết quả không dùng dữ liệu kiểm thử để chọn |
| A4 | **Giải thích mô hình** | Permutation importance (theo nhóm đặc trưng), partial dependence cho diện tích/khoảng cách/loại phòng; SHAP chỉ nếu cài được | Hình tầm quan trọng đặc trưng + 1 hình PDP |
| A5 | **Ablation** | Bỏ từng nhóm: diện tích, tiện nghi, khoảng cách, nguồn, quận, văn bản | Bảng: MAPE khi bỏ từng nhóm |
| A6 | **Khái quát hoá** | Leave-one-source-out (huấn luyện bỏ 1 nguồn, kiểm thử trên nguồn đó); huấn luyện trên tin có ngày vs không ngày | Bảng theo nguồn |
| A7 | **Khoảng dự đoán** | Hồi quy phân vị (HistGB loss=quantile, 10%/50%/90%); độ phủ thực tế của khoảng 80%; dùng để quyết "rẻ/đắt" thay cho ngưỡng 25% cố định | Hình độ phủ; app dùng khoảng phân vị |
| A8 | **So sánh thống kê** | Bootstrap theo cụm cho **hiệu số** giữa mọi cặp mô hình chính | Cột "khác biệt vs mô hình tốt nhất" có khoảng tin cậy |
| A9 | **Test** | Mỗi A-bước có một test nhỏ (không rò rỉ giữa fold, nhãn lọc không dùng nhãn kiểm thử, v.v.) | `pytest` xanh |

**Quyết định dự kiến sau A2/A3:** giữ mô hình thắng *với khoảng tin cậy*, không phải mô hình có số lớn nhất. Nếu HistGB vẫn tốt nhất, giữ nguyên.

### Phần B: Recommender làm ứng dụng, kiểm chứng tử tế
| # | Việc | Chi tiết |
|---|---|---|
| B1 | Giữ ứng dụng, đổi hint giá sang khoảng phân vị (A7) | Có test |
| B2 | Re-ranking nhẹ: khử trùng cùng toà nhà trong app (tuỳ chọn, đã có sẵn tham số) | Quyết sau |
| B3 | **Một slide, một mục báo cáo** cho bộ xếp hạng, nói đúng mức: "minh hoạ, nhãn mô phỏng/AI, chưa thắng baseline" | Đã gần xong |

### Phần C: Người dùng thật, **do nhóm thu** (đây là cách làm đúng thay cho "mô phỏng")
Nhóm có **5 thành viên**, tức là đã đủ 5 phiên (điều kiện của bộ xếp hạng: ≥200 phiếu, ≥5 phiên). Mỗi người ~25 phút.

| # | Việc | Ai làm |
|---|---|---|
| C1 | Tôi viết **chế độ chấm điểm mù** trong app: mỗi người chọn 2 kịch bản tìm phòng (cho sẵn: sinh viên gần ĐH X, người đi làm Cầu Giấy…), thấy **20 phòng theo thứ tự ngẫu nhiên** (không theo xếp hạng, khử thiên lệch vị trí), bấm Thích/Không thích; ghi session ẩn danh | Tôi |
| C2 | Mỗi thành viên chấm 2 kịch bản × 20 phòng (≥200 phiếu tổng) và, nếu được, thêm 3–5 bạn cùng lớp | **Các bạn** |
| C3 | Chạy `ltr` **không `--force`**, đánh giá bằng NDCG trên các truy vấn giữ lại, so với nearest-first/hand-set/random, có khoảng tin cậy | Tôi |
| C4 | Báo cáo kết quả **dù ra sao**: thắng thì tốt, hoà/thua thì ghi đúng. Đây là phiếu thật đầu tiên của dự án | Tôi |

**Phân tích độ nhạy mô phỏng (tuỳ chọn, có nhãn):** tôi có thể chạy "người dùng mô phỏng" với các tiêu chí khác nhau (ví dụ chỉ quan tâm giá, chỉ
quan tâm khoảng cách) để xem bộ xếp hạng nhạy thế nào với sở thích. Kết quả đặt trong phụ lục, gọi là **simulation study**, không bao giờ gọi là user study.

### Phần D: Sửa báo cáo (`docs/latex/report.tex`)
| # | Việc |
|---|---|
| D1 | Đổi tên, tóm tắt điều hành, mục 1 (mục tiêu: ưu tiên dự đoán giá) |
| D2 | Đổi cấu trúc: **§3 Dữ liệu** → **§4 Dự đoán giá** (A1–A8, mới) → **§5 Phân tích lỗi** → **§6 Ứng dụng: tìm kiếm có xếp hạng** (gộp phần cũ Methods/TF-IDF/Ranker, ngắn hơn) → **§7 Đánh giá ứng dụng** (Phần C) → thảo luận, hạn chế, đạo đức |
| D3 | Hình mới: so sánh mô hình (điểm kèm khoảng), tầm quan trọng đặc trưng, PDP, ablation, leave-one-source-out, độ phủ khoảng phân vị, trước/sau xử lý nhãn nhiễu. Sinh bằng `make_paper_figures.py` |
| D4 | Bảng số liệu: toàn bộ từ JSON; mở rộng `check_pdf.py` kiểm tự động |
| D5 | Cập nhật Related work (thêm: so sánh mô hình hồi quy trên dữ liệu bất động sản, SHAP/permutation importance, quantile regression, cross-validation lồng) |
| D6 | Cập nhật Reproducibility, Statement on AI use (nêu cả vai trò của "mô phỏng") |
| D7 | Dọn trang trống, 20–25 trang, kiểm thị giác từng trang |

### Phần E: Slide (`docs/SLIDES_SCRIPT.md`, `SLIDES_PLAN.md`)
Cấu trúc 8 slide: bài toán và dữ liệu → làm sạch/khử trùng → dự đoán giá: **nhiều mô hình** → đánh giá đúng cách (rò rỉ, fold nhóm) → giải thích
và phân tích lỗi → ứng dụng (một slide, demo) → kết quả phiếu thật → hạn chế. Backup: ablation, leave-one-source-out, bản đồ.

### Phần F: Chuẩn bị thi
| # | Việc |
|---|---|
| F1 | Danh sách ~25 câu hỏi vấn đáp khó + trả lời có dẫn chứng (dựa trên `COUNTER_REPORT.md`) |
| F2 | Tài liệu một trang: các con số then chốt và nguồn gốc của chúng |
| F3 | Chạy "phản biện vòng 2": tôi viết lại một counter-report mới về phiên bản cuối, rồi sửa |
| F4 | Một lệnh dựng lại toàn bộ (`make all` hoặc script): dữ liệu → mô hình → số → hình → PDF |
| F5 | Quay GIF demo dự phòng; tập thuyết trình có đồng hồ |
| F6 | Dọn git: đổi tên `docs/PLAN.md` mới thành `docs/REPORT_PLAN.md`, khôi phục lộ trình gốc; **không commit dữ liệu thô** |

## 3. Thứ tự và ước lượng

| Bước | Phụ thuộc | Sức lao động |
|---|---|---|
| A1 → A2 → A3 | — | A1 ~2 giờ; A2 ~3 giờ; A3 ~2 giờ (thời gian máy chạy thêm) |
| A4–A8 | A2 | ~4 giờ |
| C1 | — (song song với A) | ~2 giờ |
| C2 | C1 xong | **các bạn: ~25 phút/người** |
| C3–C4 | C2 | ~1 giờ |
| D1–D7 | A, C | ~1 ngày |
| E, F | D | ~half day |
| **Tổng** | | **~3 ngày làm việc của tôi + 25 phút/người của nhóm** |

Việc nên làm **ngay**, vì cần người thật và có độ trễ: **C1**, rồi nhờ các bạn chấm trong lúc tôi làm Phần A.

## 4. Rủi ro và cách xử lý

| Rủi ro | Xử lý |
|---|---|
| Mô hình mới không hơn HistGB | Vẫn có giá trị: báo cáo "đã so sánh 8 mô hình, HistGB thuộc nhóm tốt nhất, khác biệt không có ý nghĩa". Đó là kết quả khoa học tốt |
| Lỗi giá vẫn ~25% | Giải thích bằng nhiễu nhãn (A1) và đo phần lỗi còn lại sau khi lọc; không hứa hơn |
| Phiếu thật cho thấy bộ xếp hạng không hơn baseline | Báo đúng; bộ xếp hạng chỉ là ứng dụng minh hoạ nên luận điểm chính không phụ thuộc |
| Hết thời gian | Ưu tiên A1+A2+A3 (so sánh mô hình), D1–D2 (đổi cấu trúc báo cáo), rồi C. Bỏ A5/A6/B2 trước |
| Giảng viên hỏi về nhãn AI | Đã ghi trong báo cáo từ đầu; Phần C thay thế bằng phiếu thật |

## 5. Tiêu chí hoàn thành
- Báo cáo mở đầu bằng bài toán dự đoán giá; ≥6 mô hình được so sánh có khoảng tin cậy; có giải thích đặc trưng, ablation, khái quát hoá và khoảng dự đoán.
- Phần recommender ≤ 1/6 báo cáo; mọi tuyên bố về người dùng dựa trên **phiếu thật của nhóm** hoặc nói rõ là AI/mô phỏng.
- `pytest` xanh; `check_pdf.py` không còn số lệch; không còn trang trống; không có chữ "mô phỏng" nào bị trình bày như người thật.

## 6. Cần bạn trả lời (không chặn việc bắt đầu Phần A)
1. Hạn nộp/ngày thi, và **tiêu chí chấm** của môn (nếu có rubric, gửi tôi để bố cục báo cáo khớp).
2. Các bạn trong nhóm có chấm được ~25 phút mỗi người không (Phần C)?
3. Có hạn chế độ dài báo cáo, số slide, thời gian thuyết trình không?
4. Tên đề tài mới có được phép đổi không?

---

## Trạng thái (2026-10-07)
Người dùng xác nhận thầy cho phép dùng AI để mô phỏng; báo cáo ghi rõ "simulated users".

| Phần | Kết quả |
|---|---|
| A1 Nhãn nhiễu | 480 tin (7%) gắn cờ theo tiêu đề; lỗi 35,0% vs 24,7%; huấn luyện trên dữ liệu sạch **không** cải thiện (−0,02 điểm, khoảng −0,21 đến +0,20) |
| A2 So sánh mô hình | 10 mô hình + baseline. Tốt nhất: **HGB + văn bản (đã xoá chữ số) 22,6% (21,5–23,8)**; HGB không văn bản 25,4%; baseline 34,3% |
| Rò rỉ thứ hai | 52% tiêu đề ghi giá; mô hình văn bản đọc được giá (21,5%) → xoá mọi chữ số, có test |
| A3 Tinh chỉnh lồng | 25,4% → 25,1%, không đáng kể; giữ tham số mặc định |
| A4 Giải thích | Diện tích quan trọng nhất (+9,3 điểm khi xáo trộn); khoảng cách không thêm gì khi đã có quận; PDP hợp lý |
| A5 Ablation | Bỏ diện tích +4,4; tiện nghi +2,1; loại phòng +1,2; nguồn +0,9; quận +0,4; khoảng cách −0,1 |
| A6 Bỏ một nguồn | Mogi/Nhatot/YourHome vẫn tốt; Facebook 40,9% (kém baseline 39,4%) |
| A7 Khoảng dự đoán | 80% danh nghĩa → 68% thực; 90% → 81% → dùng 5–95% làm "khoảng thường thấy" |
| A8 | Khoảng tin cậy cho mọi hiệu số (bảng và hình) |
| B1 | **Mô hình sản phẩm đổi sang HGB + văn bản** (`price_model.py`); app dùng khoảng phân vị cho gợi ý giá; 80,7% phòng trong khoảng |
| C | Thay bằng **simulation study** (`simulate_users.py`): khôi phục sở thích r = 0,97/0,95; cần ~400 phiếu để thắng công thức tay |
| D | Báo cáo viết lại: "Estimating Fair Rents of Rooms in Hanoi", 25 trang, 53/54 số khớp JSON tự động (số còn lại là quy ước làm tròn, đã sửa) |
| E | `SLIDES_SCRIPT.md`/`SLIDES_PLAN.md` v7; PNG slide từ hình báo cáo |
| F1/F2 | `docs/EXAM_PREP.md`: bảng số then chốt + 20 câu hỏi khó |
| Kiểm thử | 96 passed; AppTest không lỗi |

Lỗi tìm thấy và sửa thêm: `ltr.per_search` giả định một truy vấn mỗi phiên (đã sửa, có test); `report_numbers.py` ghi đè các mục của script khác (đã sửa: gộp).
**Còn lại:** F3 (phản biện vòng 2), F4 (một lệnh dựng lại toàn bộ), F5 (GIF demo, tập thuyết trình), F6 (git); `report.pdf` đang bị mở trong trình xem → bản mới là `docs/latex/report_new.pdf`.
