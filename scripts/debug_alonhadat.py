"""
scripts/debug_alonhadat.py - Test /cho-thue-phong-tro-nha-tro
"""
import re
import httpx
from bs4 import BeautifulSoup

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
}

client = httpx.Client(headers=headers, follow_redirects=True, timeout=20.0)

test_url = "https://alonhadat.com.vn/cho-thue-phong-tro-nha-tro"
print(f"Fetching {test_url} ...")
r = client.get(test_url)

soup = BeautifulSoup(r.text, "html.parser")
print(f"Status: {r.status_code} | Size: {len(r.text)} bytes")
print("Title:", soup.title.string.strip() if soup.title else "None")

h1 = soup.find("h1")
print("H1:", h1.get_text(strip=True) if h1 else "None")

all_a = soup.find_all("a", href=True)
print(f"Total <a> tags: {len(all_a)}")

# Check for listing detail URLs (ending with -12345678.html)
detail_urls = []
city_urls = []
for a in all_a:
    href = a["href"]
    text = a.get_text(strip=True)
    if re.search(r"-\d{6,}\.html", href):
        detail_urls.append((text, href))
    elif any(c in href for c in ["ha-noi", "ho-chi-minh", "da-nang"]) and ("cho-thue" in href or "phong-tro" in href):
        city_urls.append((text, href))

print(f"\n--- DETAIL LISTING LINKS FOUND ({len(detail_urls)}) ---")
for text, href in detail_urls[:10]:
    print(f"  [{text[:40]}] -> {href}")

print(f"\n--- CITY FILTER LINKS FOUND ({len(city_urls)}) ---")
for text, href in city_urls[:10]:
    print(f"  [{text}] -> {href}")
