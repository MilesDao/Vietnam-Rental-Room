"""Contract every source must meet: a per-listing permalink and a clean image list."""
import ast
import json
import re
import unicodedata

import pandas as pd

# A permalink = the URL shape that identifies ONE ad on that site.
PERMALINK = {
    "Mogi.vn": r"^https://mogi\.vn/(?!dummy-id).+-id\d+/?$",
    "Alonhadat.vn": r"^https://alonhadat\.com\.vn/.+-\d+\.html$",
    "Phongtro123.com": r"^https://phongtro123\.com/.+-pr\d+\.html$",
    "ChoTot.com": r"^https://(www\.nhatot\.com|nha\.chotot\.com)/.+/\d+$",   # old links redirect to nhatot.com
    "Rencity.vn": r"^https://rencity\.vn/post/.+-\d+$",
    "YourHome.top": r"^https://yourhome\.top/room/\d+$",
    "Facebook": r"^https://www\.facebook\.com/groups/\d+/posts/\d+",
}


def is_permalink(platform, url):
    pat = PERMALINK.get(platform)
    return bool(pat and isinstance(url, str) and re.match(pat, url))


def slug(text):
    s = unicodedata.normalize("NFKD", str(text).lower().replace("đ", "d"))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def parse_images(value):
    if isinstance(value, list):
        return [str(x) for x in value]
    if not isinstance(value, str) or not value.strip():
        return []
    s = value.strip()
    if s.startswith("["):
        for loader in (json.loads, ast.literal_eval):
            try:
                return [str(x) for x in loader(s)]
            except (ValueError, SyntaxError):
                pass
        return []
    return [p.strip() for p in s.split("|") if p.strip().startswith("http")]


def mark_bad_links(df, check_shape=True):
    """True where listing_url is not a permalink or is shared by several rows of the same platform."""
    dup = df.duplicated(["platform", "listing_url"], keep=False)
    if not check_shape:
        return dup
    shape = pd.Series([is_permalink(p, u) for p, u in zip(df.platform, df.listing_url)], index=df.index)
    return dup | ~shape
