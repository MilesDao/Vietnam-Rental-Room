# Báo cáo: những gì đã làm

## 1. Lấy dữ liệu từ nhánh `unified-crawl-data`
- `git fetch` rồi `git restore --source=origin/unified-crawl-data --worktree -- data/`: chỉ chép thư mục `data/` vào workspace.
- 10 file mới ở `data/` (unified/cleaned CSV, geojson quận, đường và sông OSM, `precleaning_audit.json`). Không file nào bị ghi đè.
- **Không merge nhánh**: nhánh đó đã tách khỏi `main` và xóa nhiều file `src/`, `tests/` của `main`.
- `data/` nằm trong `.gitignore` nên các file này không bị commit nhầm.

## 2. Recommender
**File:** `src/recsys/recommend.py`, `src/recsys/__init__.py`, `tests/test_recommend.py`.
**Dữ liệu:** `data/unified_hanoi_rentals.csv`: 15.861 tin, 58 cột, 7 nền tảng
(phongtro123 4.820, Facebook 4.672, Chotot 3.631, Mogi 1.725, Rencity 862, YourHome 84, Alonhadat 67).

**Thiết kế (content-based, không cần dữ liệu người dùng):**
1. *Lọc cứng:* giá ≤ ngân sách; quận; diện tích tối thiểu; tiện nghi bắt buộc (8 loại); trường đại học gần nhất;
   khoảng cách tối đa tới trường/metro; loại phòng.
2. *Chấm điểm 0–1:* giá thấp hơn ngân sách (0,30) · giá trị so với thị trường, dựa trên `value_residual_pct` có sẵn (0,25) ·
   khoảng cách tới trường nếu có lọc trường, ngược lại tới trung tâm (0,25) · số tiện nghi (0,20).
   Giá trị thiếu được cho điểm trung tính 0,5.
3. *Đầu ra:* top-N kèm giá, diện tích, chi phí sinh hoạt ước tính, nhãn giá trị, khoảng cách, link tin; có thể lưu CSV.
   Không xuất số điện thoại hay hash liên hệ.

**Kiểm tra:** `pytest tests/test_recommend.py` pass (lọc đúng, điểm giảm dần, query bất khả thi trả rỗng).
Chạy thử `--budget 4000000 --district "Cầu Giấy" --need air_conditioner` trả 5 phòng giá 1,2–1,35 triệu, nhãn "Giá hời".

## 3. Hạn chế đã biết (chi tiết ở `docs/RECSYS_PLAN.md`)
- Chỉ khử trùng theo `listing_id`: cùng một phòng đăng ở nhiều nền tảng vẫn có thể lặp lại.
- 37% tin thiếu diện tích → được giữ lại khi lọc diện tích, điểm giá trị ở mức trung tính.
- Trọng số cố định, chưa kiểm chứng bằng đánh giá nào.
- Kết quả thử ở trên cho thấy top đang thiên về phòng ở ghép giá rất rẻ (1,2–1,35 triệu), có thể không phải phòng riêng người dùng cần; nên cân nhắc lọc `--house-type` hoặc `--min-area`.
- Chưa có bản đồ/web; chưa có folium/streamlit trên máy.
- Dữ liệu chỉ có Hà Nội.
- Chỉ chạy test mới, chưa chạy toàn bộ `tests/`.

## 4. Khử trùng lặp liên nền tảng (kế hoạch mục 1)
- `src/clean/sample_schema.py`: `mark_duplicates(df, cross_platform=False)`. Khi `True`, chỉ chặn theo quận (không theo nền tảng).
  Luật khớp giữ nguyên: giá ±5%, diện tích ±1 m², cùng tiêu đề hoặc cùng địa chỉ có số nhà/ngõ; complete-linkage.
- `src/recsys/dedup_unified.py`: chạy 1 lần (~70 giây), ghi `data/unified_hanoi_rentals_dedup.csv` với `duplicate_of`, `n_duplicates`.
  Giữ tin có nhiều trường nhất.
- `recommend.load()` đọc file mới và bỏ các dòng có `duplicate_of`.
- **Kết quả:** 15.861 → 13.675 tin (gộp 2.186; 2.016 trong đó là tin Facebook, nguồn chưa từng được khử trùng lặp).
  Top-30 của query thử (Cầu Giấy, ≤ 4 triệu) không còn cặp trùng giá + diện tích + phường.
- **Test:** `test_mark_duplicates_cross_platform` mới; toàn bộ 52 test pass.
- **Giới hạn:** tin thiếu diện tích ở cả hai bên được coi là "khớp diện tích", nên ví dụ "ngõ 113 Yên Hòa 5tr vs 4,8tr" bị gộp;
  tin chỉ có tiêu đề tương đồng nhưng địa chỉ cấp phố vẫn không gộp. Chưa đo precision/recall bằng nhãn tay.

## 5. Ước lượng diện tích thiếu (kế hoạch mục 2)
- `recommend.impute_area()` (gọi trong `load()`): thêm `area_est` (= diện tích thật, nếu thiếu thì median theo loại phòng × nhóm giá 5 phân vị) và cờ `area_imputed`.
- **Chọn nhóm bằng holdout 20%** trên tin có diện tích: MAE 10,5 m² (median toàn cục) → 8,0 (chỉ giá) → 7,8 (loại phòng × giá, được chọn);
  thêm quận không cải thiện (7,8–7,9). Cải thiện khá khiêm tốn: ước lượng chỉ mang tính tham khảo.
- **Thiếu diện tích theo nguồn:** Rencity 100%, Facebook 74%, Chotot 37%, các nguồn còn lại ≤ 2%.
- **Cách dùng:** `--min-area` vẫn lọc theo diện tích thật (tin thiếu được giữ lại). Điểm "giá trị": tin thiếu `value_residual_pct`
  dùng thứ hạng giá/m² theo `area_est` thay thế. Hai thước đo khác nhau được trộn nên đây là xấp xỉ (có comment `ponytail:` trong code).
  Kết quả hiển thị `area_est` và `area_imputed`.
- **Test:** `test_area_imputation_not_used_for_filter`; toàn bộ 53 test pass.
- **Chưa làm:** huấn luyện lại mô hình residual với diện tích ước lượng.

## 6. Giao diện Streamlit + bản đồ (kế hoạch mục 3)
- **Chạy:** `streamlit run src/recsys/app.py` (từ thư mục gốc repo). Đã thêm `streamlit`, `folium`, `streamlit-folium` vào `requirements.txt`.
- **Sidebar:** ngân sách, quận, trường gần nhất + khoảng cách, khoảng cách metro, diện tích tối thiểu, loại phòng, tiện nghi bắt buộc, số kết quả. Gọi đúng `recommend()` như CLI.
- **Kết quả:** bản đồ Folium (marker đánh số theo thứ hạng, popup có giá, diện tích — `~` nếu là ước lượng — và link tin) cạnh bảng kết quả.
  Tin thiếu tọa độ (~6%) vẫn nằm trong bảng, có dòng chú thích số tin không lên bản đồ.
- **Ghi công:** chân trang ghi "© OpenStreetMap contributors".
- **Kiểm tra:** `streamlit.testing.AppTest` chạy app không lỗi với bộ lọc mặc định và khi đổi ngân sách; server headless trả health 200.
  Chưa xem bằng mắt trên trình duyệt thật và chưa có test tự động cho giao diện.
- **Chưa làm:** vẽ ga metro / trường đại học lên bản đồ.

## 7. Đánh giá bằng persona (kế hoạch mục 4)
**Code:** `src/recsys/evaluate.py` (`python -m src.recsys.evaluate`) → `docs/RECSYS_EVAL.md` (bảng đầy đủ) và `data/recsys_eval_labels.csv`
(25 dòng top-5 của 5 persona để chấm tay 1–5; cột `rating_1_5` đang để trống). 20 persona (sinh viên 10 trường, người đi làm, studio, cặp đôi,
thú cưng, thang máy, ngân sách rất thấp/cao) × 5 cấu hình trọng số, top-10. Cả 20 persona luôn nhận đủ 10 kết quả.

**Phát hiện lỗi thật và đã sửa.** Lần chạy đầu: tin "ở ghép / slot / giường" chỉ chiếm 2,8% dữ liệu nhưng chiếm **42%** top-10 của cấu hình mặc định
(baseline rẻ nhất: 27%). Nguyên nhân: giá là giá một slot, diện tích là cả phòng → `value_residual_pct` trung vị −57% và 60% bị gắn "Giá hời".
Sửa: `recommend()` loại các tin này mặc định (`SHARED_RE`), bật lại bằng `--include-shared` (CLI) hoặc ô tick trong app.
Nhận diện bằng từ khóa trong tiêu đề nên có thể sót; test `test_shared_rooms_excluded_by_default`.

**Kết quả sau khi sửa (trung bình 20 persona, top-10):**

| cấu hình | giá/ngân sách | % giá hời | km TB | tiện nghi TB | m² TB | số quận |
|---|---|---|---|---|---|---|
| baseline: rẻ nhất | 0,32 | 0,55 | 4,24 | 2,36 | 25,9 | 3,05 |
| mặc định 30/25/25/20 | 0,42 | 0,68 | 2,72 | 3,84 | 35,8 | 2,40 |
| nghiêng giá trị | 0,43 | 0,73 | 2,78 | 3,76 | 41,7 | 2,45 |
| nghiêng khoảng cách | 0,45 | 0,58 | 2,27 | 3,20 | 33,3 | 2,10 |
| đều 25 mỗi mục | 0,44 | 0,71 | 2,70 | 4,12 | 35,9 | 2,30 |

**Đọc kết quả (thận trọng):**
- So với baseline, mọi cấu hình đều đổi ~10% ngân sách lấy phòng gần hơn (~1,5 km), nhiều tiện nghi hơn (+1,5) và rộng hơn (+10 m²). Đây là điều mong muốn nhưng **chưa chứng minh** người dùng thấy tốt hơn.
- "% giá hời" là thước đo một phần vòng tròn: nó cũng là một thành phần của điểm, nên cấu hình nghiêng giá trị cao hơn là hiển nhiên.
- Cấu hình mặc định và "đều 25" gần như không khác nhau → bộ trọng số 30/25/25/20 chưa có bằng chứng ưu việt; chưa có lý do để đổi.
- Đa dạng nguồn tốt (~3,7 nguồn/top-10); đa dạng quận thấp (~2,4) do nhiều persona gắn với một trường hoặc một quận.
- Chưa làm: chấm tay `data/recsys_eval_labels.csv`, và tính precision@k từ đó. Đó là bước cần người thật để biết gợi ý có tốt không.

## 8. Tự chấm tay và các lỗi tìm thêm (theo yêu cầu "tự đánh giá")
**Phương pháp và độ tin cậy.** Tôi (Claude) tự chấm 1–5 cho top-5 của 5 persona (25 dòng) chỉ dựa trên tiêu đề, mô tả, giá, diện tích, quận và khoảng cách
trong dữ liệu; không xem ảnh, không kiểm tra thực địa. Thang: 5 = đúng nhu cầu, thực tế, dữ liệu đáng tin; 3 = chấp nhận được nhưng có nghi vấn;
1 = sai (vd. dữ liệu vị trí sai). Đây là **đánh giá của mô hình, không phải của người dùng thật** nên chỉ dùng để tìm lỗi, không dùng làm kết luận về chất lượng.
Điểm trước sửa: `data/recsys_eval_labels_before_fix.csv`; sau sửa: `data/recsys_eval_labels.csv` (cột `rating_1_5`).

| | điểm TB | % tin ≥ 4 điểm |
|---|---|---|
| trước khi sửa lỗi dưới đây | 2,60 | 24% |
| sau khi sửa | 3,16 | 28% |

**Lỗi 1 (đã sửa) — tọa độ dự phòng sai.** 538 tin Phongtro123 (3,4% dữ liệu) dùng chung một tọa độ (21,028511; 105,804817), gắn "Láng Thượng / Đống Đa",
dù địa chỉ nêu 35 phường/xã khác nhau (Phù Đổng, Hồng Hà, Trung Giã, Thạch Thất...). Nhiều khả năng tên phường sau cải cách 2025 không có trong bảng đối chiếu nên rơi vào điểm dự phòng
(đúng khoảng trống "2025 admin-unit crosswalk" đã ghi ở `reports/cleaning_report.md`). Hậu quả: persona SV UTC nhận 4/5 phòng ở Thạch Thất/Quốc Oai (~30 km) với "cách UTC 0,11 km" (điểm TB 1,2).
Sửa: `null_fallback_geo()` trong `recommend.load()` xóa tọa độ, quận, phường và mọi cột khoảng cách/trường/metro của các điểm có ≥ 5 phường khác nhau trong địa chỉ (chỉ có 1 điểm như vậy, 531 tin sau khử trùng lặp);
cờ `geo_suspect`. Các tin này vẫn có thể xuất hiện khi không lọc theo vị trí, nhưng không còn giả vờ "gần trường".
**Cần sửa tận gốc** ở bước geocode/crosswalk; sửa trong recommender chỉ là che lỗi. Ngoài ra còn nhiều điểm bị nhiều tin dùng chung (359, 274, 248... tin) — có vẻ là tâm phường/quận, độ chính xác chỉ cấp phường.

**Lỗi 2 (đã sửa một phần) — giá theo đầu người.** "Homestay", "sleep box", "1 người", "/người", "/ng" là giá một giường nhưng diện tích là cả phòng. Đã thêm một phần vào `SHARED_RE`
(giờ loại ~4,2% tin thay vì 2,8%). Vẫn sót các dạng như "Home stay", "/ng", "cho nữ thuê chung cư". Heuristic từ khóa.

**Lỗi 3 (CHƯA sửa) — xếp hạng quá thiên về giá rẻ.** Điểm giá = 1 − giá/ngân sách nên tin rẻ nhất luôn lên đầu. 5% tin đắt ≤ 1,5 triệu (trung vị 3,9 triệu) nhưng phần lớn top-5
của persona sinh viên nằm ở 1,0–1,6 triệu — giá bất thường, thường là slot/đầu người hoặc tin thiếu thông tin. Gợi ý: cho điểm giá cao nhất quanh mức giá điển hình của loại phòng/quận
(vd. trung vị nhóm), hoặc bỏ tin dưới phân vị 5% theo nhóm, rồi chạy lại `evaluate`. Chưa làm vì đổi công thức xếp hạng cần bạn xác nhận.

**Điểm yếu còn lại:** tin Facebook thường thiếu diện tích nên persona "đi làm" (cần ≥ 20 m²) vẫn nhận nhiều tin chưa rõ diện tích (điểm TB 2,8, thấp nhất cùng với SV UTC).
Persona "nuôi thú cưng" tốt nhất (3,6), vì lọc cứng `pet_allowed` đã loại phần lớn tin nhiễu.
**Kết luận:** sau hai lần sửa dữ liệu, chất lượng tăng nhưng vẫn ở mức trung bình (≈ 3,2/5, 28% tin đạt ≥ 4). Lỗi 3 là việc đáng làm tiếp theo; chấm tay bởi người thật vẫn cần trước khi học trọng số (mục 5).

## 9. Sửa lỗi 3 — điểm giá thiên về tin rẻ nhất
- **Thay đổi** (`src/recsys/recommend.py`): `add_typical_price()` tính `typical_price` = median giá của cùng loại phòng × quận (chỉ theo loại phòng nếu nhóm < 30 tin).
  `price_score()` thay cho `1 − giá/ngân sách`: = 1 tại mức giá điển hình (hoặc tại ngân sách nếu ngân sách thấp hơn), giảm tuyến tính về 0 khi giá tiến tới 0 (tin quá rẻ thường là slot, tin sơ sài hoặc giá gán sai),
  và giảm nhẹ (tối đa 0,5) từ mức điển hình tới ngân sách. Vẫn ưu tiên rẻ hơn khi cả hai đều ở trên mức điển hình.
- **Test:** `test_price_score_prefers_typical_over_suspiciously_cheap`. Test này bắt được lỗi thật khi viết: `price_score` gọi `.clip(lower=)` nên hỏng với numpy array; đã đổi sang `np.maximum`.
  Toàn bộ 56 test pass.
- **Tự chấm lại (cùng 5 persona, top-5 mới, cùng phương pháp và cùng hạn chế như §8):**

| | điểm TB | % tin ≥ 4 điểm |
|---|---|---|
| ban đầu | 2,60 | 24% |
| sau sửa tọa độ + giá đầu người | 3,16 | 28% |
| **sau sửa điểm giá** | **3,52** | **52%** |

  Theo persona: SV NEU 3,4 · SV UTC 3,0 · SV VNU 4,0 · đi làm Thanh Xuân 3,8 · thú cưng 3,4.
- **Tác dụng phụ trên bảng `RECSYS_EVAL.md`:** giá/ngân sách trung bình của cấu hình mặc định tăng 0,47 → 0,76 (người dùng trả gần mức điển hình hơn thay vì tin rẻ bất thường); tin có diện tích ước lượng giảm 28% → 12%.
- **Còn lại sau lần chấm này:** (1) SV UTC chỉ 3,0 vì khoảng cách tới trường nhiều tin có vẻ không đáng tin (vd. Hoàng Hoa Thám ghi cách UTC ~1 km) — lỗi vị trí cấp phường ở bước geocode;
  (2) tin gần như trùng trong cùng tòa (YourHome ngõ 189 Hoàng Hoa Thám, giá 3,6/4,0 triệu) vẫn không bị gộp vì giá lệch > 5%;
  (3) một tin "Ký túc xá" tick `pet_allowed` — nhiều khả năng nhãn tiện nghi sai. Điểm số vẫn do tôi tự chấm, cần người thật xác nhận.
