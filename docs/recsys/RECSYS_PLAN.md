# Kế hoạch hoàn thiện Recommender (phần chưa làm)

Hiện có: bộ lọc cứng + chấm điểm có trọng số, chạy bằng CLI (`src/recsys/recommend.py`).
Các hạng mục dưới đây sắp theo thứ tự nên làm; mỗi hạng mục độc lập, xong cái nào dùng được cái đó.

## 1. Khử trùng lặp liên nền tảng  *(✅ ĐÃ XONG — xem RECSYS_REPORT.md §4)*
- **Vấn đề:** cùng một phòng đăng trên Facebook / phongtro123 / chotot... → xuất hiện nhiều lần trong top.
- **Cách làm:** dùng lại `src/clean/dedup.py` (complete-linkage, so sánh địa chỉ dạng text, chặn theo quận)
  trên `unified_hanoi_rentals.csv`; thêm cột `cluster_id`, recommender chỉ giữ 1 tin/cụm (tin có nhiều ảnh nhất).
- **Xong khi:** top-10 của vài query mẫu không còn cặp cùng giá + diện tích + địa chỉ; test tổng hợp nhỏ cho hàm gộp.
- **Rủi ro:** đại lý đăng nhiều phòng khác nhau cùng mẫu tiêu đề → giữ đúng 2 cải tiến đã ghi trong CLAUDE.md, không quay về single-linkage.

## 2. Xử lý tin thiếu diện tích (37%)  *(✅ ĐÃ XONG — xem RECSYS_REPORT.md §5)*
- **Cách làm:** điền `area_m2` ước lượng theo (loại phòng, quận, giá) bằng median của nhóm, kèm cờ `area_imputed`;
  chỉ dùng cho điểm, **không** dùng để lọc `--min-area`; hiển thị rõ "~ước lượng" trong kết quả.
- **Xong khi:** cột cờ có trong output, lọc `--min-area` vẫn xử lý riêng tin thiếu diện tích như hiện tại.

## 3. Bản đồ + giao diện web  *(✅ ĐÃ XONG — xem RECSYS_REPORT.md §6)*
- **Cách làm:** Streamlit + Folium (cài thêm `streamlit`, `folium`, `streamlit-folium`; chưa có trong `requirements.txt`).
  Sidebar = các tham số CLI hiện có; bản đồ = marker cho top-N, popup có giá, diện tích, link tin;
  vẽ thêm ga metro và các trường đại học đã có trong dữ liệu.
- **Lưu ý dữ liệu:** 6% tin thiếu tọa độ → hiển thị trong bảng nhưng không có marker.
- **Ghi công:** nếu dùng tọa độ geocode, ghi "© OpenStreetMap contributors" trên giao diện (yêu cầu của Nominatim).
- **Xong khi:** `streamlit run src/recsys/app.py` lọc và hiển thị được đúng kết quả như CLI.

## 4. Đánh giá chất lượng gợi ý  *(✅ ĐÃ XONG phần tự động — xem RECSYS_REPORT.md §7; còn chấm tay)*
- **Vấn đề:** chưa có ground truth nên chưa biết trọng số 30/25/25/20 tốt đến đâu.
- **Cách làm (không cần người dùng thật):** tạo ~20 persona (sinh viên NEU/TMU/HOU..., ngân sách 2–6 triệu...);
  đo độ phủ (có đủ N kết quả không), tỷ lệ tin "Giá hời", khoảng cách trung bình, độ đa dạng quận/nguồn.
  So sánh với baseline (chỉ sắp theo giá). Có thể nhờ vài bạn chấm tay top-5 cho 5 persona.
- **Xong khi:** có bảng so sánh trọng số trong report.

## 5. Học trọng số (chỉ làm nếu có phản hồi)
- Cần dữ liệu thích/không thích từ bước 3–4. Nếu có ≥ vài trăm lượt: hồi quy logistic trên 4 thành phần điểm.
- Nếu không có dữ liệu → **bỏ**, giữ trọng số cố định (YAGNI).

## 6. Hạng mục nhỏ
- Gợi ý "tin tương tự" (cosine trên giá, diện tích, tiện nghi, vị trí) — chỉ làm nếu thấy cần trong UI.
- Mở rộng ngoài Hà Nội: dữ liệu hiện chỉ có Hà Nội; HCMC cần crawl + geocode trước (Phase 2/4 trong `docs/PLAN.md`).

## Thứ tự & ước lượng
| # | Hạng mục | Công sức | Phụ thuộc |
|---|----------|----------|-----------|
| 1 | Khử trùng liên nền tảng | nhỏ | — |
| 2 | Ước lượng diện tích | nhỏ | — |
| 3 | Streamlit + bản đồ | vừa | cài thư viện, nên làm sau 1 |
| 4 | Đánh giá persona | nhỏ–vừa | 1 |
| 5 | Học trọng số | vừa | phản hồi từ 3–4 |

---
Latest update: see docs/RECSYS_UPDATE_REPORT.md (English), including the geocoding fix (src/recsys/regeocode_fallback.py).

Cập nhật 2026-10-05: ga metro/trường trên bản đồ, thêm dạng tin ở ghép, và giới hạn 1 phòng/tòa nhà khi gợi ý — xem RECSYS_UPDATE_REPORT.md §9.
