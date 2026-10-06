"""Live check that a sample of listing links and images really work.

    python -m src.crawl.verify_sample data/unified_hanoi_rentals_dedup.csv [--n 25]

Link ok  : HTTP 200, final URL still holds the listing id, no expiry text in the page.
Image ok : first image answers 200 with an image/* content type, sent with NO Referer.
Exceptions (reported, not counted as failures): YourHome pages are client-rendered shells
(any id gives 200), www.nhatot.com answers scripts with 403.  Exit 1 if any platform < 95 %.
"""
import argparse
import re
import sys
import time

import pandas as pd
import requests

from src.clean.link_check import is_permalink, parse_images

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
EXPIRED = ("hết hạn", "đã bán", "đã cho thuê", "không tìm thấy", "không tồn tại", "đã bị xóa")   # plus the number 404 as a whole word
UNVERIFIABLE = {"YourHome.top", "ChoTot.com"}   # YourHome: client-rendered, 200 for any id; nhatot.com: 403 to scripts


def looks_expired(html):
    """Only the <title> and <h1> count: expiry words also sit in menus/footers of live pages."""
    head = " ".join(re.findall(r"<(?:title|h1)[^>]*>(.*?)</(?:title|h1)>", html, flags=re.S | re.I)).lower()
    if not re.search(r"<(?:title|h1)", html, flags=re.I):
        head = html.lower()   # bare fragment: judge all of it
    return any(m in head for m in EXPIRED) or re.search(r"\b404\b", head) is not None


def rencity_title_ok(html, title):
    m = re.search(r"<title>\s*Rencity\s*-\s*([^<]*)</title>", html)
    if not m or not m.group(1).strip():
        return False
    words = lambda t: set(re.findall(r"\w+", t.lower()))
    return len(words(m.group(1)) & words(str(title))) >= 3


_MAGIC = (bytes([0xFF, 0xD8, 0xFF]), bytes([0x89]) + b"PNG", b"GIF8")   # jpeg, png, gif


def is_image_bytes(head, content_type=""):
    return content_type.startswith("image/") or head.startswith(_MAGIC) or (head[:4] == b"RIFF" and head[8:12] == b"WEBP")


def link_ok(row):
    url = row.listing_url
    if not is_permalink(row.platform, url):
        return False
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=20, allow_redirects=True)
    except requests.RequestException:
        return False
    if r.status_code != 200:
        return False
    if row.platform == "Rencity.vn":
        return rencity_title_ok(r.text, row.title)
    native = re.search(r"(\d{5,})(?:\.html|/)?$", url)
    return not looks_expired(r.text) and (not native or native.group(1) in r.url)


def image_ok(row):
    imgs = parse_images(row.image_urls)
    if not imgs:
        return False
    try:
        r = requests.get(imgs[0], headers={"User-Agent": UA}, timeout=20, stream=True)
    except requests.RequestException:
        return False
    if r.status_code != 200:
        return False
    # some CDNs (rencity S3) serve webp as octet-stream; a browser still shows it unless nosniff is set
    head = next(r.iter_content(12), b"")
    return is_image_bytes(head, r.headers.get("content-type", "")) and "nosniff" not in r.headers.get("x-content-type-options", "").lower()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--n", type=int, default=25)
    ap.add_argument("--skip", nargs="*", default=[], help="platforms not to request (e.g. one that has CAPTCHA-blocked us)")
    a = ap.parse_args()
    d = pd.read_csv(a.csv, low_memory=False)
    d = d[(d.platform != "Facebook") & ~d.platform.isin(a.skip)]
    bad = False
    print(f"{'platform':16} {'n':>3} {'link_ok%':>9} {'image_ok%':>10}")
    for p, g in d.groupby("platform"):
        s = g.sample(min(a.n, len(g)), random_state=0)
        links, imgs = [], []
        for row in s.itertuples():
            links.append(None if p in UNVERIFIABLE else link_ok(row))
            imgs.append(image_ok(row))
            time.sleep(1)
        lk = "n/a" if p in UNVERIFIABLE else f"{100 * sum(links) / len(s):.0f}"
        im = 100 * sum(imgs) / len(s)
        print(f"{p:16} {len(s):>3} {lk:>9} {im:>10.0f}")
        bad |= im < 95 or (lk != "n/a" and float(lk) < 95)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
