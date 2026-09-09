# Vietnam Rental Room — Crawler & Exporter (Phongtro123 & Alonhadat)

Hệ thống thu thập (crawling) và trích xuất dữ liệu phòng trọ cho thuê tại **Hà Nội** và **TP. Hồ Chí Minh** từ 2 nguồn:
1. **Phongtro123.com** (Chuyên phòng trọ sinh viên, chung cư mini)
2. **Alonhadat.com.vn** (Phòng trọ, nhà trọ chính chủ)

---

## 1. Định Dạng Dữ Liệu Đầu Ra

Mỗi khi cào xong, hệ thống sẽ **tự động xuất đồng thời cả 2 file `.csv` và `.json`** ở thư mục gốc và thư mục `data/interim/`:
* 📄 **File `.json`**: Mảng đối tượng JSON chuẩn `[ {...}, {...} ]`.
* 📊 **File `.csv`**: Bảng dữ liệu phẳng chuẩn UTF-8 BOM, mở bằng Excel tiếng Việt không lỗi font.

Các trường dữ liệu chuẩn thu được bao gồm:
* `listing_id`: Mã tin đăng duy nhất (VD: `phongtro123_712549`, `alonhadat_19042998`)
* `title`: Tiêu đề bài đăng
* `price_vnd_month`: Giá thuê chuẩn hóa thành số (VND/tháng)
* `area_m2`: Diện tích ($m^2$)
* `address_raw`: Địa chỉ chi tiết
* `description`: Toàn bộ nội dung mô tả phòng
* `image_urls`: Danh sách link ảnh chất lượng cao (tối đa 8 ảnh/tin)
* `phone_hash`: Số điện thoại đã được mã hóa bảo mật SHA-256
* `city`: Thành phố (`hanoi` hoặc `hcm`)
* `crawled_at`: Thời gian thu thập

---

## 2. Hướng Dẫn Chạy Cào Dữ Liệu

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

## 3. Tiện Ích Xuất Lại CSV & JSON
Bất kỳ lúc nào bạn muốn xuất lại toàn bộ dữ liệu ra file `.csv` và `.json`:
```bash
python3 scripts/export_all.py
```
