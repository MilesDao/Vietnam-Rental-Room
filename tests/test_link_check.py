import pandas as pd
from src.clean.link_check import is_permalink, parse_images, mark_bad_links, slug


def test_permalinks():
    assert is_permalink("Mogi.vn", "https://mogi.vn/ha-noi/thue-phong-tro/phong-tro-cau-giay-id22046391")
    assert not is_permalink("Mogi.vn", "https://mogi.vn/dummy-id22046391")
    assert is_permalink("ChoTot.com", "https://www.nhatot.com/thue-phong-tro/134126101")
    assert is_permalink("ChoTot.com", "https://nha.chotot.com/thue-phong-tro/134126101")
    assert is_permalink("Alonhadat.vn", "https://alonhadat.com.vn/phong-dep-19042998.html")
    assert is_permalink("Phongtro123.com", "https://phongtro123.com/phong-tro-x-pr588674.html")
    assert is_permalink("YourHome.top", "https://yourhome.top/room/1791207671066")
    assert not is_permalink("YourHome.top", "https://yourhome.top/?city=ha-noi")
    assert is_permalink("Rencity.vn", "https://rencity.vn/post/phong-501-32917")
    assert not is_permalink("Rencity.vn", "https://rencity.vn/search?post_id=1")
    assert not is_permalink("Mogi.vn", None)


def test_parse_images_all_formats():
    want = ["https://a/1.jpg", "https://a/2.jpg"]
    assert parse_images("https://a/1.jpg | https://a/2.jpg") == want
    assert parse_images('["https://a/1.jpg", "https://a/2.jpg"]') == want
    assert parse_images("['https://a/1.jpg', 'https://a/2.jpg']") == want
    assert parse_images(want) == want
    assert parse_images(float("nan")) == [] and parse_images("[]") == []


def test_mark_bad_links_flags_duplicates():
    df = pd.DataFrame({"platform": ["X", "X", "Y"], "listing_url": ["u", "u", "u"]})
    assert mark_bad_links(df, check_shape=False).tolist() == [True, True, False]


def test_slug():
    assert slug("Phòng 501 mới, đủ nội thất") == "phong-501-moi-du-noi-that"


def test_mogi_real_urls(tmp_path):
    import sqlite3
    from src.export.export_mogi_to_sample import real_urls
    db = tmp_path / "m.db"
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE seen_urls (listing_id TEXT, url TEXT)")
        c.execute("INSERT INTO seen_urls VALUES ('mogi_123', 'https://mogi.vn/ha-noi/x/y-id123')")
    u = real_urls(db)["123"]
    assert is_permalink("Mogi.vn", u)


def test_rencity_filter_and_url():
    from src.scrapers.crawl_rencity import is_hanoi_room, post_url
    room = {"id": "32917", "title": "Phòng 501 mới, đủ nội thất", "province_name": "Thành phố Hà Nội"}
    assert is_hanoi_room(room)
    assert not is_hanoi_room({**room, "title": "Văn phòng tầng 1 Vạn Bảo"})
    assert not is_hanoi_room({**room, "province_name": "Thành phố Hồ Chí Minh"})
    assert post_url(room) == "https://rencity.vn/post/phong-501-moi-du-noi-that-32917"
    assert is_permalink("Rencity.vn", post_url(room))


def test_prepare_gate_and_stale():
    from src.recsys.prepare import drop_stale, gate_links
    d = pd.DataFrame({
        "platform": ["Mogi.vn", "YourHome.top", "YourHome.top", "ChoTot.com"],
        "listing_url": ["https://mogi.vn/dummy-id1", "https://yourhome.top/?city=ha-noi",
                        "https://yourhome.top/?city=ha-noi", "https://www.nhatot.com/thue-phong-tro/134126101"],
        "image_urls": ["a", "https://a/1.jpg | https://a/2.jpg", "['https://a/3.jpg']", None],
        "days_old": [None, 400, 10, 5]})
    g = gate_links(d)
    assert g.listing_url.notna().tolist() == [False, False, False, True]
    assert g.image_urls.tolist()[1] == '["https://a/1.jpg", "https://a/2.jpg"]'
    assert g.image_count.tolist() == [0, 2, 1, 0]
    assert drop_stale(d).days_old.tolist()[1:] == [10, 5] and len(drop_stale(d)) == 3   # 400-day ad gone, undated kept


def test_clean_numbers():
    from src.pipelines.merge_fresh import clean_numbers
    d = pd.DataFrame({"latitude": [21.0] * 6, "longitude": [105.8] * 6, "title": ["Phòng đẹp"] * 4 + ["cho thuê mặt bằng kinh doanh", "x"],
                      "price_vnd": [3_000_000, 0, "bad", 800_000_000, 5_000_000, 3], "area_m2": [0, 20, 15, 25, 30, 20]})
    c = clean_numbers(d)
    assert len(c) == 1 and pd.isna(c.area_m2.iloc[0])   # 0 price, text, 800M, shop and "3 VND" rows all gone


def test_posted_and_facebook_links_kept():
    from src.pipelines.merge_fresh import _posted
    from src.recsys.prepare import gate_links
    assert _posted("Thứ 4, 15:44 30/09/2026") == "30/09/2026"
    assert _posted("2026-10-06T03:12:34+00:00") == "06/10/2026"
    fb = "https://www.facebook.com/groups/1/posts/2"
    d = pd.DataFrame({"platform": ["Facebook", "Facebook"], "listing_url": [fb, fb], "image_urls": ["[]", "[]"]})
    assert gate_links(d).listing_url.notna().all()


def test_fallback_point_rows_are_dropped():
    from src.pipelines.merge_fresh import FALLBACK, finish
    d = pd.DataFrame({"title": ["a", "b"], "latitude": [FALLBACK[0], 21.0], "longitude": [FALLBACK[1], 105.8],
                      "price_vnd": [3_000_000, 3_000_000], "area_m2": [20, 20], "district": ["Ba Đình", "Cầu Giấy"], "ward": ["x", "y"],
                      "image_urls": ["[]", "[]"], "listing_url": ["u", "u"]})
    out = finish(d, "Mogi.vn", [], ["Cầu Giấy"])
    assert out.district.tolist() == ["Cầu Giấy"]


def test_hash_phone_never_leaks():
    from src.recsys.prepare import hash_phone
    h = hash_phone("0988050715")
    assert h == hash_phone("988050715") == hash_phone("+84 988 050 715") and h != "0988050715"
    assert hash_phone("not a phone") is None
    assert hash_phone(h) == h


def test_listing_ids_keep_old_convention(tmp_path):
    from src.pipelines.merge_fresh import mogi
    f = tmp_path / "m.csv"
    pd.DataFrame({"listing_id": ["20616816"]}).to_csv(f, index=False)
    assert mogi(f).listing_id.tolist() == ["mogi_20616816"]
    pd.DataFrame({"listing_id": ["mogi_20616816"]}).to_csv(f, index=False)
    assert mogi(f).listing_id.tolist() == ["mogi_20616816"]   # export already prefixes; never mogi_mogi_
