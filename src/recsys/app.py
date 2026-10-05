"""Streamlit UI for the recommender:  streamlit run src/recsys/app.py

Layout and usage follow listing sites such as yourhome.top: filters in a left sidebar, "N kết quả phù hợp",
a sort box, a page-size box, cards (photo, type badge, price, address, area, "Bản đồ" link) with
"Trang x/y" pagination, and a map tab where you click a point to find rooms within a chosen radius.
"""
import html
import os
import re
import sys
from pathlib import Path

import folium
import numpy as np
import pandas as pd
import streamlit as st
from branca.element import MacroElement, Template
from folium.plugins import FastMarkerCluster
from streamlit_folium import st_folium

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # streamlit puts src/recsys, not the repo root, on sys.path
from src.recsys.recommend import load, recommend

st.set_page_config(page_title="Tìm phòng trọ Hà Nội", page_icon="🏠", layout="wide")

AMENITY_VI = {"air_conditioner": "Điều hòa", "water_heater": "Nóng lạnh", "refrigerator": "Tủ lạnh",
              "washing_machine": "Máy giặt", "elevator": "Thang máy", "balcony_window": "Ban công / cửa sổ",
              "fire_safety": "PCCC", "pet_allowed": "Nuôi thú cưng"}
SORTS = {"Phù hợp nhất": ("score", False), "Giá thấp → cao": ("price_vnd", True),
         "Giá cao → thấp": ("price_vnd", False), "Diện tích lớn → nhỏ": ("area_est", False),
         "Gần trung tâm": ("distance_to_center_km", True)}
PAGE_SIZES = [8, 12, 24, 48, 100]
MAX_MAP = 5000   # map dots: best-scoring matches first, keeps the page light
# Phone numbers: set RECSYS_SHOW_PHONE=0 to hide them. Only numbers already present in the data are shown
# (Phongtro123 mostly); hashed values and Facebook posts (personal data, docs/PLAN.md Phase 2B) never are.
SHOW_PHONE = os.environ.get("RECSYS_SHOW_PHONE", "1") != "0"


@st.cache_data
def data():
    return load()


# price-pill markers: readable at a glance (label = price, colour = price band); clusters = dark numbered discs
DOT_JS = """function (row) {
  var icon = L.divIcon({className: 'pin-wrap', iconSize: [52, 26], iconAnchor: [26, 13],
    html: '<div class="pin" style="background:' + row[4] + ';color:' + row[5] + '">' + row[3] + '</div>'});
  return L.marker(new L.LatLng(row[0], row[1]), {icon: icon}).bindPopup(row[2]);
}"""
CLUSTER_JS = """function (cluster) {
  var n = cluster.getChildCount(), s = n < 10 ? 38 : n < 100 ? 46 : 56;
  return L.divIcon({className: 'cl-wrap', iconSize: [s, s],
    html: '<div class="cl" style="width:' + s + 'px;height:' + s + 'px;line-height:' + (s - 4) + 'px">' + n + '</div>'});
}"""
MAP_CSS = """<style>
.pin{font:600 13px/22px system-ui,sans-serif;text-align:center;border:2px solid #fff;border-radius:13px;
     box-shadow:0 1px 3px rgba(15,23,42,.30);white-space:nowrap}
.cl{color:#fff;background:#64748b;font:600 15px system-ui,sans-serif;text-align:center;border:3px solid #fff;
    border-radius:50%;box-shadow:0 1px 4px rgba(15,23,42,.35)}
.area-ring{animation:breathe 2.6s ease-in-out infinite}
@keyframes breathe{0%,100%{fill-opacity:.06;stroke-opacity:.55}50%{fill-opacity:.16;stroke-opacity:1}}
</style>"""
# soft pastel fill + dark text of the same hue: < 3 tr green, 3-5 tr blue, > 5 tr rose
BANDS = [(3e6, "#bbf7d0", "#14532d"), (5e6, "#bfdbfe", "#1e3a8a"), (float("inf"), "#fecdd3", "#881337")]


def band(price):
    return next((bg, fg) for cap, bg, fg in BANDS if price < cap)


def short_price(v):
    return f"{v / 1e6:.1f}".rstrip("0").rstrip(".").replace(".", ",") + "tr"


class ClusterFly(MacroElement):
    """Click a numbered disc -> glide and zoom into the area its rooms cover (spiderfy if they share one spot)."""
    _template = Template("{% macro script(this, kwargs) %}"
                         "{{ this.cluster }}.on('clusterclick', function (e) {"
                         "var b = e.layer.getBounds();"
                         "if (b.getNorthEast().equals(b.getSouthWest())) { e.layer.spiderfy(); return; }"
                         "{{ this._parent.get_name() }}.flyToBounds(b, {duration: 0.9, padding: [60, 60], maxZoom: 18});"
                         "});{% endmacro %}")

    def __init__(self, cluster):
        super().__init__()
        self.cluster = cluster.get_name()


class FlyTo(MacroElement):
    """Glide the map into a layer's bounds. A plain Element would be emitted before the map exists."""
    _template = Template("{% macro script(this, kwargs) %}"
                         "{{ this._parent.get_name() }}.flyToBounds({{ this.layer }}.getBounds(), "
                         "{duration: 1.8, padding: [24, 24]});{% endmacro %}")

    def __init__(self, layer):
        super().__init__()
        self.layer = layer.get_name()


def esc(x):
    """HTML-escape and neutralise {{ }}: folium renders popups through a Jinja template."""
    return html.escape(str(x)).replace("{", "&#123;").replace("}", "&#125;")


def images(row, n=6):
    """Up to n photo URLs. Facebook posts are personal data (docs/PLAN.md Phase 2B): never show their images."""
    if row.platform == "Facebook" or not isinstance(row.image_urls, str):
        return []
    return re.findall(r"https?://[^\s|;,]+", row.image_urls)[:n]


def first_image(row):
    imgs = images(row, 1)
    return imgs[0] if imgs else None


def phone(row):
    """(digits, '0392 860 288') when the data holds a real Vietnamese number, else None."""
    if not SHOW_PHONE or row.platform == "Facebook" or not isinstance(row.contact_phone, str):
        return None
    digits = re.sub(r"\D", "", row.contact_phone)
    if not re.fullmatch(r"0\d{9,10}", digits):    # hashed values (16 hex chars) fail this
        return None
    return digits, f"{digits[:4]} {digits[4:7]} {digits[7:]}"


def popup_html(row):
    """Self-contained map popup: main photo + thumbnails that swap it, key facts, click-to-reveal phone."""
    imgs = images(row, 5)
    parts = ['<div style="width:240px;font:13px system-ui,sans-serif">']
    if imgs:
        parts.append(f'<img class="pp-main" src="{esc(imgs[0])}" loading="lazy" '
                     'style="width:100%;height:150px;object-fit:cover;border-radius:8px">')
        if len(imgs) > 1:
            parts.append('<div style="display:flex;gap:4px;margin:4px 0">' + "".join(
                f'<img src="{esc(u)}" loading="lazy" style="width:44px;height:34px;object-fit:cover;border-radius:4px;'
                'cursor:pointer" onclick="this.parentNode.previousSibling.src=this.src">' for u in imgs) + "</div>")
    parts.append(f"<b>{esc(row.title)}</b><br>{esc(price_txt(row.price_vnd))} · {row.area_est:.0f} m²"
                 f"<br>{esc(row.district)}")
    ph = phone(row)
    if ph:
        parts.append(f'<br><button data-p="{ph[0]}" data-f="{ph[1]}" style="margin-top:6px;padding:4px 10px;'
                     'border-radius:8px;border:1px solid #94a3b8;background:#f1f5f9;cursor:pointer" '
                     "onclick=\"this.replaceWith(Object.assign(document.createElement('a'),"
                     "{href:'tel:'+this.dataset.p,textContent:this.dataset.f,style:'font-weight:700'}))\">"
                     "Hiện số điện thoại</button>")
    if isinstance(row.listing_url, str):
        parts.append(f'<br><a href="{esc(row.listing_url)}" target="_blank">Xem tin gốc</a>')
    return "".join(parts) + "</div>"


def price_txt(v):
    return f"{v / 1e6:.2f}".rstrip("0").rstrip(".").replace(".", ",") + " triệu/tháng"


def card(row, key):
    with st.container(border=True):
        img = first_image(row)
        if img:
            st.markdown(f'<img src="{esc(img)}" style="width:100%;height:150px;object-fit:cover;border-radius:8px" '
                        f'alt="ảnh phòng" loading="lazy">', unsafe_allow_html=True)
        else:
            st.markdown('<div style="height:150px;border-radius:8px;background:#8881;display:flex;align-items:center;'
                        'justify-content:center;opacity:.6">Chưa có ảnh</div>', unsafe_allow_html=True)
        st.markdown(f":blue-badge[{row.house_type}]" if isinstance(row.house_type, str) else "")
        st.markdown(f"**{price_txt(row.price_vnd)}**")
        area = f"~{row.area_est:.0f}" if row.area_imputed else f"{row.area_est:.0f}"
        st.caption(f"{area} m² · {row.district if isinstance(row.district, str) else 'Chưa rõ quận'}")
        st.caption(esc(row.address) if isinstance(row.address, str) else "")
        c1, c2 = st.columns(2)
        if isinstance(row.listing_url, str):
            c1.link_button("Xem tin", row.listing_url, width="stretch")
        if pd.notna(row.latitude):
            with c2.popover("Bản đồ", width="stretch"):
                st.map(pd.DataFrame({"lat": [row.latitude], "lon": [row.longitude]}), zoom=15, height=220)
                st.caption("© OpenStreetMap contributors")
        with st.popover("Ảnh & liên hệ", width="stretch"):   # opening it is the "click" that reveals the phone
            imgs = images(row, 5)
            if imgs:
                st.image(imgs[0], width="stretch")
                if len(imgs) > 1:
                    st.image(imgs[1:], width=72)
            else:
                st.caption("Chưa có ảnh cho tin này.")
            ph = phone(row)
            if ph:
                st.markdown("**Số điện thoại**")
                st.code(ph[1], language=None)   # st.code has a copy button
            else:
                st.caption("Dữ liệu không có số điện thoại của tin này, hãy xem trong tin gốc.")


def card_grid(df, prefix, cols=4):
    rows = list(df.itertuples())
    for i in range(0, len(rows), cols):
        for col, row in zip(st.columns(cols), rows[i:i + cols]):
            with col:
                card(row, f"{prefix}{row.listing_id}")


d = data()

# ---------------------------------------------------------------- sidebar: filters
with st.sidebar:
    st.header("Bộ lọc")
    lo, hi = st.slider("Khoảng giá (triệu/tháng)", 0.5, 25.0, (1.0, 5.0), 0.5)
    types = st.multiselect("Loại phòng", sorted(d.house_type.dropna().unique()))
    a_lo, a_hi = st.slider("Diện tích (m²)", 0, 120, (0, 120), 5)
    need = st.multiselect("Tiện nghi", list(AMENITY_VI), format_func=AMENITY_VI.get)
    districts = st.multiselect("Quận / huyện", sorted(d.district.dropna().unique()))
    uni = st.selectbox("Gần trường đại học", [""] + sorted(d.nearest_university.dropna().unique()),
                       format_func=lambda x: x or "(không chọn)")
    max_uni = st.slider("Cách trường tối đa (km)", 0.5, 10.0, 3.0, 0.5) if uni else None
    sources = st.multiselect("Nguồn tin", sorted(d.platform.dropna().unique()))
    shared = st.checkbox("Cả tin ở ghép / slot", False)
    st.caption("Tin chưa rõ diện tích vẫn được giữ khi lọc diện tích.")

# ---------------------------------------------------------------- results
res = recommend(d, hi * 1e6, districts, None, need, uni or None, max_uni, None, None, 10 ** 6,
                include_shared=shared, per_building=0)
# recommend() returns a trimmed set of columns; bring back what the cards and the map need
extra = d.set_index("listing_id")[["house_type", "address", "latitude", "longitude", "image_urls", "contact_phone", "distance_to_center_km"]]
res = res.join(extra, on="listing_id")
res = res[res.price_vnd >= lo * 1e6]
if types:
    res = res[res.house_type.isin(types)]
if sources:
    res = res[res.platform.isin(sources)]
if (a_lo, a_hi) != (0, 120):
    known = res.area_imputed == False  # noqa: E712  (area_est equals the real area when not imputed)
    res = res[~known | ((res.area_est >= a_lo) & (res.area_est <= a_hi))]

st.title("🏠 Tìm phòng trọ Hà Nội")
# a switch instead of st.tabs: tabs run both bodies on every rerun, and the map body is the expensive one
view = st.segmented_control("Chế độ xem", ["Trang chủ", "Bản đồ"], default="Trang chủ", label_visibility="collapsed") or "Trang chủ"

if view == "Trang chủ":
    top = st.columns([3, 2, 2])
    top[0].markdown(f"### {len(res):,} kết quả phù hợp".replace(",", "."))
    sort_name = top[1].selectbox("Sắp xếp", list(SORTS), label_visibility="collapsed")
    size = top[2].selectbox("Hiển thị", PAGE_SIZES, index=1, format_func=lambda n: f"{n} tin / trang",
                            label_visibility="collapsed")
    col, asc = SORTS[sort_name]
    shown = res.sort_values(col, ascending=asc, na_position="last")
    pages = max(1, -(-len(shown) // size))
    sig = (lo, hi, tuple(types), a_lo, a_hi, tuple(need), tuple(districts), uni, max_uni, tuple(sources), shared,
           sort_name, size)
    if st.session_state.get("sig") != sig:   # any filter change -> back to page 1
        st.session_state.update(sig=sig, page=1)
    page = min(st.session_state.get("page", 1), pages)
    if shown.empty:
        st.warning("Không có tin nào khớp, hãy nới bớt bộ lọc.")
    else:
        card_grid(shown.iloc[(page - 1) * size: page * size], "l")
        nav = st.columns([1, 1, 2, 1, 1])
        if nav[0].button("« Đầu", disabled=page == 1):
            st.session_state.page = 1
            st.rerun()
        if nav[1].button("‹ Trước", disabled=page == 1):
            st.session_state.page = page - 1
            st.rerun()
        nav[2].markdown(f"<div style='text-align:center;padding-top:.4rem'>Trang {page}/{pages}</div>",
                        unsafe_allow_html=True)
        if nav[3].button("Sau ›", disabled=page == pages):
            st.session_state.page = page + 1
            st.rerun()
        if nav[4].button("Cuối »", disabled=page == pages):
            st.session_state.page = pages
            st.rerun()

else:
    st.markdown("#### CHẤM MỘT ĐIỂM TRÊN BẢN ĐỒ ĐỂ TÌM PHÒNG XUNG QUANH")
    radius = st.selectbox("Bán kính tìm kiếm", [0.5, 1, 2, 3, 5, 10], index=2, format_func=lambda r: f"{r} km")
    on_map = res.dropna(subset=["latitude", "longitude"]).head(MAX_MAP)
    click = st.session_state.get("click")
    prev = st.session_state.get("prev_click")   # start where the user was looking, so a new click is one continuous glide
    m = folium.Map(location=prev or [on_map.latitude.mean() if len(on_map) else 21.03,
                                    on_map.longitude.mean() if len(on_map) else 105.82],
                   zoom_start=13 if prev else 12, zoomSnap=0.25, zoomDelta=0.5, wheelPxPerZoomLevel=90,
                   zoomAnimation=True, fadeAnimation=True, markerZoomAnimation=True)
    m.get_root().header.add_child(folium.Element(MAP_CSS))
    rows = [[x.latitude, x.longitude, popup_html(x), short_price(x.price_vnd), *band(x.price_vnd)]
            for x in on_map.itertuples()]
    # FastMarkerCluster builds the markers in the browser: ~10x faster than one folium object per room
    cl = FastMarkerCluster(rows, callback=DOT_JS, icon_create_function=CLUSTER_JS, animate=True,
                           animateAddingMarkers=False, showCoverageOnHover=False, maxClusterRadius=45,
                           zoomToBoundsOnClick=False).add_to(m)
    ClusterFly(cl).add_to(m)   # added after the cluster so the script is emitted after it is defined
    if click:
        folium.Marker(click, icon=folium.Icon(color="cadetblue", icon="crosshairs", prefix="fa"),
                      tooltip="Điểm đã chọn").add_to(m)
        ring = folium.Circle(click, radius=radius * 1000, color="#0d9488", weight=3, dash_array="8 6", fill=True,
                             fill_color="#14b8a6", fill_opacity=0.10, class_name="area-ring").add_to(m)
        FlyTo(ring).add_to(m)   # the map opens on the whole city, then glides into the chosen area
    out = st_folium(m, height=520, use_container_width=True, returned_objects=["last_clicked"], key="map")
    pt = out and out.get("last_clicked")
    if pt and [pt["lat"], pt["lng"]] != click:
        st.session_state.prev_click = click
        st.session_state.click = [pt["lat"], pt["lng"]]
        st.rerun()
    st.markdown("Giá/tháng: <span style='background:#bbf7d0;color:#14532d;padding:2px 9px;border-radius:10px'>&lt; 3 triệu</span> "
                "<span style='background:#bfdbfe;color:#1e3a8a;padding:2px 9px;border-radius:10px'>3–5 triệu</span> "
                "<span style='background:#fecdd3;color:#881337;padding:2px 9px;border-radius:10px'>&gt; 5 triệu</span> "
                "· hình tròn xám có số = nhiều phòng gộp lại, bấm để phóng to", unsafe_allow_html=True)
    st.caption(f"Hiển thị tối đa {MAX_MAP} tin phù hợp bộ lọc (gộp nhóm khi thu nhỏ). "
               "Bản đồ: © OpenStreetMap contributors.")
    if click:
        p1, p2 = np.radians(click[0]), np.radians(res.latitude.astype(float))
        a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(
            np.radians(res.longitude.astype(float) - click[1]) / 2) ** 2
        near = res.assign(km=12742 * np.arcsin(np.sqrt(a))).query("km <= @radius").sort_values("km")
        st.markdown(f"### {len(near)} phòng trong bán kính {radius} km")
        if near.empty:
            st.info("Không có phòng nào trong bán kính này, thử tăng bán kính hoặc nới bộ lọc.")
        else:
            card_grid(near.head(24), "n")
            if len(near) > 24:
                st.caption("Hiển thị 24 phòng gần nhất.")
        if st.button("Xóa điểm đã chọn"):
            st.session_state.update(click=None, prev_click=None)
            st.rerun()
    else:
        st.info("Bấm vào một vị trí trên bản đồ để xem các phòng quanh đó.")

st.caption("Diện tích có dấu ~ là ước lượng. Ảnh lấy từ trang nguồn của tin; tin từ Facebook không hiển thị ảnh.")
