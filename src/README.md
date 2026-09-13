# Vietnam Rental Room — Crawler & Exporter (Phongtro123 & Alonhadat)

Hệ thống thu thập (crawling), lọc thông minh và trích xuất dữ liệu **Phòng trọ cho thuê** tại **Hà Nội** và **TP. Hồ Chí Minh** từ 2 nguồn chính:
1. **Phongtro123.com** (Chuyên phòng trọ sinh viên, chung cư mini, ở ghép)
2. **Alonhadat.com.vn** (Mục cho thuê phòng trọ, nhà trọ chính chủ)

---

## 1. Tiêu Chí & Bộ Lọc Dữ Liệu (Business Rules)

Hệ thống được tích hợp bộ lọc tự động (`src/parse/filter.py`) để đảm bảo chất lượng dữ liệu:
* 🎯 **Chỉ lấy Phòng trọ / Nhà trọ / CCMN sinh viên / Ở ghép / Studio / KTX**: Tự động loại bỏ hoàn toàn các loại hình nhà ở khác như chung cư cao cấp, căn hộ 2PN-3PN, biệt thự, nhà nguyên căn, văn phòng, mặt bằng kinh doanh, kho xưởng,...
* 💰 **Giới hạn mức giá $\le$ 6 triệu VNĐ/tháng**: Tự động loại bỏ tất cả các tin đăng có giá trên 6 triệu VNĐ/tháng.
* ⏰ **Tự động lọc tin hết hạn**: Kiểm tra trạng thái bài đăng (trên danh sách trang và trang chi tiết), tự động loại bỏ các bài đăng đã hết hạn, đã cho thuê, ngừng giao dịch hoặc tin cũ.

---

## 2. Quy Cách Xuất Dữ Liệu (1 CSV & 1 JSON Duy Nhất / Website)

Hệ thống hoạt động theo cơ chế **Ghi đè và Cập nhật (Upsert & Overwrite)**. Với mỗi website sẽ **chỉ tồn tại đúng 1 file CSV và 1 file JSON duy nhất** ở thư mục gốc:
* 📁 **Phongtro123**:
  - `raw_phongtro123.csv`: Bảng dữ liệu phẳng chuẩn UTF-8 BOM, mở bằng Excel không lỗi font tiếng Việt.
  - `raw_phongtro123.json`: Mảng đối tượng JSON chuẩn `[ {...}, {...} ]`.
* 📁 **Alonhadat**:
  - `raw_alonhadat.csv`: Bảng dữ liệu phẳng chuẩn UTF-8 BOM.
  - `raw_alonhadat.json`: Mảng đối tượng JSON chuẩn.

> 💡 **Lưu ý:** Mỗi lần chạy cào mới, hệ thống sẽ tự động cập nhật và ghi đè vào các file trên (không tạo thêm file rác, không tạo file đuôi ngày tháng).

---

## 3. Các Trường Dữ Liệu Chuẩn (31 Cột)

* `listing_id`: Mã tin đăng duy nhất (VD: `phongtro123_712549`, `alonhadat_19042998`)
* `source`: Nguồn website (`phongtro123`, `alonhadat`)
* `url`: Đường dẫn link bài đăng gốc
* `title`: Tiêu đề bài đăng
* `description`: Toàn bộ nội dung mô tả phòng
* `price`: Giá thuê dạng số (VNĐ/tháng) hoặc cụm từ thỏa thuận (`"Thỏa thuận"`, `"Thương lượng"`, `"Liên hệ"`)
* `area_m2`: Diện tích ($m^2$)
* `address_raw`: Địa chỉ chi tiết gốc
* `city`: Thành phố (`hanoi` hoặc `hcm`)
* `district`: Quận/Huyện đã chuẩn hóa
* `ward`: Phường/Xã trích xuất
* `house_type`: Loại hình phòng (`Studio khép kín`, `1PN/1N1K`, `CCMN`, `Gác xép / Duplex`, `Phòng trọ khép kín`...)
* `electric_price`, `water_price`, `wifi_price`, `other_utilities_price`, `parking_fee`: Giá dịch vụ trích xuất
* `air_conditioner`, `water_heater`, `refrigerator`, `washing_machine`, `elevator`, `balcony_window`, `fire_safety`, `pet_allowed`: Cờ tiện nghi boolean (`True`/`False`)
* `image_urls`: Danh sách link ảnh chất lượng cao (tối đa 8 ảnh/tin)
* `phone_hash`: Số điện thoại đã được băm mã hóa bảo mật SHA-256
* `room_type`: Loại phòng (`phòng trọ`)
* `posted_at_raw`: Thời gian đăng tin gốc
* `crawled_at`: Thời gian thu thập dữ liệu

---

## 4. Hướng Dẫn Chạy Cào Dữ Liệu

### ⚡ Cách 1: Chạy Tự Động Toàn Bộ 2 Trang (1 Lệnh Duy Nhất)
Chạy script tự động cào cả **Phongtro123** và **Alonhadat** tại cả 2 thành phố **Hà Nội & TP.HCM**:
```bash
python3 scripts/crawl_all.py --max-pages 5
```
*(Thay `--max-pages 5` bằng số trang bạn muốn, hoặc đặt `--max-pages 0` để cào toàn bộ các trang cho đến hết).*

---

### 🎯 Cách 2: Chạy Từng Trang Riêng Biệt

#### A. Cào từ **Phongtro123.com**:
* **Tại Hà Nội:**
  ```bash
  python3 -m src.crawl.run --site phongtro123 --city hanoi --max-pages 5
  ```
* **Tại TP. Hồ Chí Minh:**
  ```bash
  python3 -m src.crawl.run --site phongtro123 --city hcm --max-pages 5
  ```

#### B. Cào từ **Alonhadat.com.vn**:
* **Tại Hà Nội:**
  ```bash
  python3 -m src.crawl.run --site alonhadat --city hanoi --max-pages 5
  ```
* **Tại TP. Hồ Chí Minh:**
  ```bash
  python3 -m src.crawl.run --site alonhadat --city hcm --max-pages 5
  ```

---

## 5. Tiện Ích Xuất Lại CSV & JSON
Bất kỳ lúc nào bạn muốn đọc lại toàn bộ raw HTML đã lưu và ghi đè lại file `.csv` và `.json`:
```bash
python3 scripts/export_all.py
```
