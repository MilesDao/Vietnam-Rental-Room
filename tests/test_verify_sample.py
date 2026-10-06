from src.crawl.verify_sample import looks_expired, rencity_title_ok


def test_expired_markers():
    assert looks_expired("<h1>Tin đăng đã hết hạn</h1>")
    assert looks_expired("Không tìm thấy trang")
    assert not looks_expired("<h1>Phòng trọ Cầu Giấy 3tr</h1>")
    assert looks_expired("<title>404 - Not found</title>")
    assert not looks_expired("<title>Cho thuê phòng P404 - 714041</title>")   # 404 inside other digits/words


def test_rencity_title():
    assert rencity_title_ok("<title>Rencity - Phòng 501 mới, đủ nội thất tại Miếu Đầm</title>", "Phòng 501 mới, đủ nội thất tại Miếu Đầm – 5,5 triệu/tháng")
    assert not rencity_title_ok("<title>Rencity - </title>", "Phòng 501 mới")
    assert not rencity_title_ok("<title>Rencity - Tìm kiếm</title>", "Phòng 501 mới đủ nội thất")


def test_image_bytes():
    from src.crawl.verify_sample import is_image_bytes
    assert is_image_bytes(b"RIFF\x00\x00\x00\x00WEBP", "application/octet-stream")
    assert is_image_bytes(b"\xff\xd8\xff\xe0abcdefgh", "application/octet-stream")
    assert is_image_bytes(b"<html>", "image/jpeg")
    assert not is_image_bytes(b"<!DOCTYPE h", "text/html")
