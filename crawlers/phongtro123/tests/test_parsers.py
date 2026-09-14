"""
tests/test_parsers.py - Unit tests for price/area parsing, property validation, and HTML parsers
"""

import unittest
from src.parse.phongtro123_parser import (
    parse_price,
    parse_area,
    parse_phongtro123_detail,
)
from src.parse.filter import is_valid_rental_room, is_listing_expired, MAX_RENTAL_PRICE_VND


class TestParsersAndFilters(unittest.TestCase):

    def test_is_listing_expired(self):
        # Active HTML -> False
        active_html = "<html><body><h1>Phòng trọ Cầu Giấy 3tr</h1><p>Phòng mới sạch đẹp</p></body></html>"
        is_exp, _ = is_listing_expired(active_html)
        self.assertFalse(is_exp)

        # Phongtro123 expired banner -> True
        phongtro_expired_html = '<div class="alert bg-danger text-white">Bạn đang xem tin cũ tại Phongtro123.com, tin đăng này đã hết hạn.</div>'
        is_exp, reason = is_listing_expired(phongtro_expired_html)
        self.assertTrue(is_exp)
        self.assertIn("hết hạn", reason.lower())

        # Alonhadat expired marker -> True
        alonhadat_expired_html = '<div class="notice">Tin đã hết hạn hiển thị hoặc đã được cho thuê.</div>'
        is_exp, reason = is_listing_expired(alonhadat_expired_html)
        self.assertTrue(is_exp)

    def test_parse_price_variations(self):
        self.assertEqual(parse_price("3.5 triệu/tháng"), 3500000.0)
        self.assertEqual(parse_price("3,5 tr"), 3500000.0)
        self.assertEqual(parse_price("3tr5"), 3500000.0)
        self.assertEqual(parse_price("800 nghìn/tháng"), 800000.0)
        self.assertEqual(parse_price("800k"), 800000.0)
        self.assertEqual(parse_price("Thỏa thuận"), "Thỏa thuận")
        self.assertEqual(parse_price("Liên hệ"), "Liên hệ")
        self.assertEqual(parse_price("Giá thương lượng"), "Thương lượng")

    def test_parse_area_variations(self):
        self.assertEqual(parse_area("25 m²"), 25.0)
        self.assertEqual(parse_area("25m2"), 25.0)
        self.assertEqual(parse_area("30.5 m²"), 30.5)
        self.assertIsNone(parse_area("không rõ"))

    def test_price_filter_limit_6m(self):
        # Listing <= 6M -> Accepted
        valid_rec = {
            "title": "Cho thuê phòng trọ sinh viên Cầu Giấy giá rẻ",
            "price_vnd": 3500000.0,
            "source": "phongtro123",
        }
        is_val, _ = is_valid_rental_room(valid_rec, max_price=6000000.0, allow_negotiable=False)
        self.assertTrue(is_val)

        # Listing with string price ("Thỏa thuận") when allow_negotiable=False -> Excluded
        negotiable_rec = {
            "title": "Phòng trọ giá thỏa thuận",
            "price_vnd": "Thỏa thuận",
            "source": "phongtro123",
        }
        is_val, reason = is_valid_rental_room(negotiable_rec, max_price=6000000.0, allow_negotiable=False)
        self.assertFalse(is_val)
        self.assertIn("negotiable/unspecified", reason)

        # Listing with string price ("Thỏa thuận") when allow_negotiable=True -> Accepted
        is_val_neg, _ = is_valid_rental_room(negotiable_rec, max_price=6000000.0, allow_negotiable=True)
        self.assertTrue(is_val_neg)

        # Listing at exactly 6M -> Accepted
        boundary_rec = {
            "title": "Phòng trọ studio full đồ",
            "price_vnd": 6000000.0,
            "source": "alonhadat",
        }
        is_val, _ = is_valid_rental_room(boundary_rec, max_price=6000000.0)
        self.assertTrue(is_val)

        # Listing > 6M (e.g. 7M, 15M) when max_price is 6M -> Excluded
        expensive_rec = {
            "title": "Phòng trọ cao cấp",
            "price_vnd": 7000000.0,
            "source": "phongtro123",
        }
        is_val, reason = is_valid_rental_room(expensive_rec, max_price=6000000.0)
        self.assertFalse(is_val)
        self.assertIn("exceeds limit", reason)

    def test_property_type_filter(self):
        # Exclude Luxury apartments & Whole houses & Offices
        luxury_apartment = {
            "title": "Cho thuê căn hộ cao cấp 2PN Goldmark City",
            "price_vnd": 5500000.0,
            "source": "alonhadat",
        }
        is_val, _ = is_valid_rental_room(luxury_apartment)
        self.assertFalse(is_val)

        whole_house = {
            "title": "Cho thuê nhà nguyên căn 4 tầng ngõ rộng ô tô đỗ",
            "price_vnd": 5000000.0,
            "source": "alonhadat",
        }
        is_val, _ = is_valid_rental_room(whole_house)
        self.assertFalse(is_val)

        villa = {
            "title": "Cho thuê biệt thự khu đô thị Thanh Hà",
            "price_vnd": 6000000.0,
            "source": "alonhadat",
        }
        is_val, _ = is_valid_rental_room(villa)
        self.assertFalse(is_val)

        office = {
            "title": "Cho thuê văn phòng mặt phố Cầu Giấy",
            "price_vnd": 4000000.0,
            "source": "alonhadat",
        }
        is_val, _ = is_valid_rental_room(office)
        self.assertFalse(is_val)

        # Valid phòng trọ / CCMN / Ở ghép
        phong_tro = {
            "title": "Cho thuê phòng trọ khép kín full đồ Quan Hoa Cầu Giấy",
            "price_vnd": 3200000.0,
            "source": "phongtro123",
        }
        is_val, _ = is_valid_rental_room(phong_tro)
        self.assertTrue(is_val)

    def test_parse_phongtro123_mock_html(self):
        mock_html = """
        <html>
            <body>
                <h1 class="page-h1">Cho thuê phòng trọ Cầu Giấy khép kín</h1>
                <div class="post-attributes">
                    <span class="item price"><span>3.2 triệu/tháng</span></span>
                    <span class="item acreage"><span>22 m²</span></span>
                    <span class="item location"><span>Số 123 Đường Cầu Giấy, Phường Quan Hoa, Quận Cầu Giấy, Hà Nội</span></span>
                    <span class="item published"><span>Hôm nay</span></span>
                </div>
                <section class="section-post-description">
                    <div class="section-content">Phòng đầy đủ điều hòa nóng lạnh, giờ giấc tự do.</div>
                </section>
                <div class="post-images">
                    <img src="https://img.phongtro123.com/sample1.jpg" />
                    <img src="https://img.phongtro123.com/sample2.jpg" />
                </div>
                <a href="tel:0987654321" class="btn-phone">0987654321</a>
            </body>
        </html>
        """
        url = "https://phongtro123.com/phong-tro-cau-giay-pr99999.html"
        result = parse_phongtro123_detail(mock_html, url)

        self.assertEqual(result["listing_id"], "phongtro123_99999")
        self.assertEqual(result["price_vnd"], 3200000.0)
        self.assertNotIn("price_is_negotiable", result)
        self.assertEqual(result["area_m2"], 22.0)
        self.assertIn("Cầu Giấy", result["address_raw"])
        self.assertEqual(result["phone_number"], "0987654321")

    def test_normalizer_features(self):
        from src.parse.normalizer import (
            extract_utilities,
            map_district_and_ward,
            classify_house_type,
            extract_amenities,
            enrich_record,
        )

        # 1. Utilities extraction
        desc = """
        Phòng đẹp khép kín Cầu Giấy.
        - Điện: 4k/số
        - Nước: 100k/người
        - Wifi: 100k/phòng
        - DVC: 150k/người
        - Free xe máy
        """
        utils = extract_utilities(desc)
        self.assertIn("4k/số", utils["electric_price"])
        self.assertIn("100k/người", utils["water_price"])
        self.assertIn("100k/phòng", utils["wifi_price"])
        self.assertIn("150k/người", utils["other_utilities_price"])
        self.assertEqual(utils["parking_fee"], "Miễn phí")

        # 2. District & Ward mapping
        d, w = map_district_and_ward("Số 10 Ngõ 123 Phường Dịch Vọng Hậu, Quận Cầu Giấy, Hà Nội")
        self.assertEqual(d, "Cầu Giấy")
        self.assertEqual(w, "Dịch Vọng Hậu")

        # Fallback to ward mapping
        d2, _ = map_district_and_ward("Gần chợ Khương Đình, đường Khương Đình")
        self.assertEqual(d2, "Thanh Xuân")

        # 3. House Type Classification
        self.assertEqual(classify_house_type("Cho thuê căn hộ mini 1PN 1 khách full đồ"), "1 Phòng Ngủ (1PN/1N1K)")
        self.assertEqual(classify_house_type("Studio ban công thoáng mát"), "Studio khép kín")
        self.assertEqual(classify_house_type("Phòng trọ có gác xép cao ráo"), "Gác xép / Duplex")
        self.assertEqual(classify_house_type("Chung cư mini cao cấp CCMN"), "Chung cư mini (CCMN)")

        # 4. Amenities boolean flags
        amenities = extract_amenities("Phòng full đồ có điều hòa, nóng lạnh, tủ lạnh, máy giặt, thang máy, ban công thoáng, có hệ thống PCCC, cho nuôi pet")
        self.assertTrue(amenities["air_conditioner"])
        self.assertTrue(amenities["water_heater"])
        self.assertTrue(amenities["refrigerator"])
        self.assertTrue(amenities["washing_machine"])
        self.assertTrue(amenities["elevator"])
        self.assertTrue(amenities["balcony_window"])
        self.assertTrue(amenities["fire_safety"])
        self.assertTrue(amenities["pet_allowed"])

        # Pet forbidden checks (including shortened and enumerated restrictions like 'ko nhận xe điện, nuôi thú cưng')
        self.assertFalse(extract_amenities("Không cho nuôi pet, cấm nuôi chó mèo")["pet_allowed"])
        self.assertFalse(extract_amenities("Lưu ý: ko nhận xe điện, nuôi thú cưng.")["pet_allowed"])
        self.assertFalse(extract_amenities("K nhận nuôi chó mèo, miễn thú cưng")["pet_allowed"])
        self.assertFalse(extract_amenities("Quy định toà nhà cấm pet")["pet_allowed"])

        # Pet allowed positive checks
        self.assertTrue(extract_amenities("Phòng rộng thoáng, cho nuôi pet")["pet_allowed"])
        self.assertTrue(extract_amenities("Được nuôi thú cưng, nuôi chó mèo thoải mái")["pet_allowed"])
        self.assertTrue(extract_amenities("Pet friendly, giờ giấc tự do")["pet_allowed"])
        self.assertTrue(extract_amenities("Cho phép nuôi pet thân thiện")["pet_allowed"])

        # 5. Enrich record
        rec = {
            "title": "Phòng Studio 1PN Cầu Giấy",
            "description": "Điện 3.8k/số, nước giá dân. Có điều hòa thang máy.",
            "address_raw": "Đường Dịch Vọng, Quận Cầu Giấy, Hà Nội",
            "city": "hanoi",
        }
        enriched = enrich_record(rec)
        self.assertEqual(enriched["district"], "Cầu Giấy")
        self.assertEqual(enriched["ward"], "Dịch Vọng")
        self.assertIsNotNone(enriched["latitude"])
        self.assertIsNotNone(enriched["longitude"])
        self.assertTrue(20.9 <= enriched["latitude"] <= 21.2)
        self.assertTrue(105.7 <= enriched["longitude"] <= 105.9)
        self.assertEqual(enriched["house_type"], "1 Phòng Ngủ (1PN/1N1K)")
        self.assertTrue(enriched["air_conditioner"])
        self.assertTrue(enriched["elevator"])
        self.assertFalse(enriched["pet_allowed"])
        self.assertEqual(enriched["water_price"], "Nước giá dân")


if __name__ == "__main__":
    unittest.main()
