"""
tests/test_parsers.py - Unit tests for price/area parsing and parser functions
"""

from src.parse.phongtro123_parser import (
    parse_price,
    parse_area,
    parse_phongtro123_detail,
)
from src.parse.alonhadat_parser import parse_alonhadat_detail


def test_parse_price_variations():
    assert parse_price("3.5 triệu/tháng") == (3500000.0, False)
    assert parse_price("3,5 tr") == (3500000.0, False)
    assert parse_price("3tr5") == (3500000.0, False)
    assert parse_price("800 nghìn/tháng") == (800000.0, False)
    assert parse_price("800k") == (800000.0, False)
    assert parse_price("Thỏa thuận") == (None, True)
    assert parse_price("Liên hệ") == (None, True)


def test_parse_area_variations():
    assert parse_area("25 m²") == 25.0
    assert parse_area("25m2") == 25.0
    assert parse_area("30.5 m²") == 30.5
    assert parse_area("không rõ") is None


def test_parse_phongtro123_mock_html():
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

    assert result["listing_id"] == "phongtro123_99999"
    assert result["price_vnd_month"] == 3200000.0
    assert result["area_m2"] == 22.0
    assert "Cầu Giấy" in result["address_raw"]
    assert len(result["image_urls"]) == 2
    assert result["phone_hash"] != ""
    assert "0987654321" not in result["phone_hash"]  # Verified salted hash


def test_parse_alonhadat_mock_html():
    mock_html = """
    <html>
        <body>
            <div class="title"><h1>Phòng trọ sinh viên Thanh Xuân giá rẻ</h1></div>
            <div class="moreinfor">
                <div class="price"><span class="value">2,5 triệu/tháng</span></div>
                <div class="square"><span class="value">20 m²</span></div>
                <div class="date"><span class="value">09/09/2026</span></div>
            </div>
            <div class="address"><span class="value">Triều Khúc, Thanh Xuân, Hà Nội</span></div>
            <div class="detail"><div class="content">Nhà gần chợ và đại học Hà Nội.</div></div>
            <div class="gallery">
                <img src="https://alonhadat.com.vn/img1.jpg" />
            </div>
            <div class="contact-info">
                <span class="phone">0912345678</span>
            </div>
        </body>
    </html>
    """
    url = "https://alonhadat.com.vn/phong-tro-thanh-xuan-888888.html"
    result = parse_alonhadat_detail(mock_html, url)

    assert result["listing_id"] == "alonhadat_888888"
    assert result["price_vnd_month"] == 2500000.0
    assert result["area_m2"] == 20.0
    assert "Thanh Xuân" in result["address_raw"]
    assert len(result["image_urls"]) == 1
    assert result["phone_hash"] != ""
