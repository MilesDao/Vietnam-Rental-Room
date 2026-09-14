from src.geo.address import Candidate, accept_result, build_candidates, detect_city, parse_street


def test_parse_street_formats_seen_in_the_data():
    cases = {
        # mogi / alonhadat: street first, then ward, district, city
        "Tạ Quang Bửu, Phường Bách Khoa, Quận Hai Bà Trưng, Hà Nội": ("Tạ Quang Bửu", None, None),
        "12/3, Phố Xã Đàn, Phường Kim Liên, Quận Đống Đa, Hà Nội": ("Xã Đàn", "Phố", "3"),
        "Xã Đàn, Phường Kim Liên, Quận Đống Đa, Hà Nội": ("Xã Đàn", None, None),
        # PhongTot
        "Đường Đường Láng, Quận Đống Đa, Hà Nội": ("Láng", "Đường", None),
        "Ngõ Hoàng An, Quận Đống Đa, Hà Nội": ("Ngõ Hoàng An", None, None),
        # Rencity / YourHome
        "Ngõ 580 Trường Chinh": ("Trường Chinh", None, "580"),
        "Số 104 ngách 49/25 ngõ 165 dương quảng hàm": ("dương quảng hàm", None, "165"),
        "Số nhà 21, ngõ 2/27, đường Phương Canh": ("Phương Canh", "Đường", "2"),
        "19A/15/100/250 KIM GIANG": ("KIM GIANG", None, "250"),
        "số nhà 25 ngách 46 Linh Quang": ("Linh Quang", None, None),
        "Số 33B Mặt phố Tôn Đức Thắng": ("Tôn Đức Thắng", "Phố", None),
        "102 Khuất Duy Tiến": ("Khuất Duy Tiến", None, None),
        "Tổ 12 Yên Nghĩa": ("Yên Nghĩa", None, None),
        "Số 21/5 Hoàng Cầu": ("Hoàng Cầu", None, "5"),
        "số 6 ngõ 16 khu tập thể thủy sản (đi ngõ 94 Cầu Bươu vào)": ("khu tập thể thủy sản", None, "16"),
    }
    for address, expected in cases.items():
        parts = parse_street(address)
        assert (parts.street, parts.prefix, parts.alley) == expected, address


def test_build_candidates_order_and_no_house_numbers():
    candidates = build_candidates("Ngõ 580 Trường Chinh", "Phường Kim Liên", "Quận Đống Đa")
    assert [(c.level, c.query) for c in candidates] == [
        ("alley", "Ngõ 580 Trường Chinh, Hà Nội"),
        ("street", "Trường Chinh, Hà Nội"),
        ("street", "Phố Trường Chinh"),
        ("street", "Đường Trường Chinh"),
        ("ward", "Phường Kim Liên, Hà Nội"),
        ("ward", "Kim Liên, Hà Nội"),
        ("district", "Quận Đống Đa, Hà Nội"),
    ]
    assert all(c.district == "Quận Đống Đa" for c in candidates[:-1])
    assert candidates[-1].district is None
    queries = [c.query for c in build_candidates("Số 104 ngách 49/25 ngõ 165 dương quảng hàm",
                                                 None, "Quận Cầu Giấy")]
    assert not any("104" in q or "49" in q for q in queries)
    assert build_candidates(None, None, None) == []


def test_street_fallbacks_and_district_suffix():
    def street_queries(address, district):
        return [c.query for c in build_candidates(address, None, district) if c.level == "street"]

    # "Đường" as written first (with city), then "Phố", no city; glued-on district dropped
    assert street_queries("Đường Lê Trọng Tấn Thanh Xuân, Quận Thanh Xuân, Hà Nội", "Quận Thanh Xuân") == [
        "Đường Lê Trọng Tấn, Hà Nội", "Phố Lê Trọng Tấn",
    ]
    assert street_queries("Phố Kim Mã, Quận Ba Đình, Hà Nội", "Quận Ba Đình") == [
        "Phố Kim Mã, Hà Nội", "Đường Kim Mã",
    ]
    # a street that is just the district's name is left alone
    assert street_queries("Cầu Giấy", "Quận Cầu Giấy")[0] == "Cầu Giấy, Hà Nội"


def test_addresses_outside_hanoi_are_searched_in_their_own_city():
    assert detect_city("số 35 Lê Văn Chí, Linh Xuân, Hồ Chí Minh") == "Hồ Chí Minh"
    assert detect_city("Trần Phú, Phường Mộ Lao, Quận Hà Đông, Hà Nội") == "Hà Nội"
    assert detect_city("102 Khuất Duy Tiến") == "Hà Nội"      # no province named
    assert detect_city("12 Nguyễn Huệ, TP.HCM") == "Hồ Chí Minh"

    candidates = build_candidates("số 35 Lê Văn Chí, Linh Xuân, Hồ Chí Minh", "Linh Xuân", None)
    assert [(c.level, c.query) for c in candidates] == [
        ("street", "Lê Văn Chí, Hồ Chí Minh"),
        ("street", "Phố Lê Văn Chí"),
        ("street", "Đường Lê Văn Chí"),
        ("ward", "Linh Xuân, Hồ Chí Minh"),
        ("city", "Hồ Chí Minh, Việt Nam"),
    ]
    assert all(c.city == "Hồ Chí Minh" and c.district is None for c in candidates)
    # a Hanoi district never bounds a non-Hanoi address
    assert all(c.district is None for c in build_candidates("Lê Văn Chí, Hồ Chí Minh", None, "Quận Đống Đa"))


def road(name):
    return {"category": "highway", "type": "residential", "name": name}


def area(name, category="boundary"):
    return {"category": category, "type": "historic", "name": name}


def test_accept_result_rejects_the_probe_near_misses():
    alley = Candidate("alley", "Ngõ 73 Phùng Khoang, Hà Nội", "phung khoang", "73", "Quận Thanh Xuân")
    assert not accept_result(alley, road("Ngõ 30 Đường Phùng Khoang"))
    assert not accept_result(alley, road("Ngõ 730 Phùng Khoang"))
    assert accept_result(alley, road("Ngõ 73 Phùng Khoang"))

    street = Candidate("street", "Đường Láng, Hà Nội", "lang", None, "Quận Đống Đa")
    assert accept_result(street, road("Đường Láng"))
    assert accept_result(street, road("Ngõ 850 Đường Láng"))
    assert not accept_result(street, road("Đường Láng Hạ"))
    assert not accept_result(street, {"category": "office", "type": "company", "name": "Đường Láng"})

    # a street whose own name starts with "Dương"
    dqh = Candidate("street", "dương quảng hàm, Hà Nội", "duong quang ham", None, "Quận Cầu Giấy")
    assert accept_result(dqh, road("Phố Dương Quảng Hàm"))
    assert accept_result(dqh, road("Ngõ 165 Dương Quảng Hàm"))

    ward = Candidate("ward", "Thanh Xuân Bắc, Hà Nội", "thanh xuan bac", None, "Quận Thanh Xuân")
    assert accept_result(ward, area("Phường Thanh Xuân Bắc"))
    assert accept_result(ward, area("Thanh Xuân Bắc", category="place"))
    assert not accept_result(ward, {"category": "leisure", "type": "park", "name": "Vườn hoa Thanh Xuân Bắc"})
    assert not accept_result(ward, area("Phường Thanh Xuân Nam"))
