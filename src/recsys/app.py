"""Streamlit UI for the recommender:  streamlit run src/recsys/app.py

Layout follows listing sites such as yourhome.top: filters in a left sidebar (pre-filled from the URL, so a
search can be shared), free-text search (TF-IDF, src/recsys/similar.py), "N kết quả phù hợp", sort and page-size
boxes, cards (photo, type badge, price, ML value hint, area, links) with 👍/👎 feedback (src/recsys/feedback.py),
♡ save and ≈ similar rooms, "Trang x/y" pagination; a map view with one- or two-point radius search; and a
saved-rooms view with side-by-side comparison. No phone numbers are shown (project PII rule).
"""
import html
import re
import sys
import uuid
from pathlib import Path

import folium
import numpy as np
import pandas as pd
import streamlit as st
from branca.element import MacroElement, Template
from folium.plugins import FastMarkerCluster
from streamlit_folium import st_folium

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # streamlit puts src/recsys, not the repo root, on sys.path
from src.clean.link_check import parse_images
from src.recsys import feedback
from src.clean.sample_schema import WHOLE_HOUSE
from src.recsys.recommend import load, ranker_info, recommend
from src.recsys.ref_points import UNIVERSITIES
from src.recsys.similar import Index

st.set_page_config(page_title="Tìm phòng trọ Hà Nội", page_icon="🏠", layout="wide")

AMENITY_VI = {"air_conditioner": "Điều hòa", "water_heater": "Nóng lạnh", "refrigerator": "Tủ lạnh",
              "washing_machine": "Máy giặt", "elevator": "Thang máy", "balcony_window": "Ban công / cửa sổ",
              "fire_safety": "PCCC", "pet_allowed": "Nuôi thú cưng"}
SORTS = {"Phù hợp nhất": ("score", False), "Giá thấp → cao": ("price_vnd", True),
         "Giá cao → thấp": ("price_vnd", False), "Diện tích lớn → nhỏ": ("area_est", False),
         "Gần trung tâm": ("distance_to_center_km", True)}
PAGE_SIZES = [8, 12, 24, 48, 100]
MAX_MAP = 5000   # map dots: best-scoring matches first, keeps the page light


@st.cache_data
def data():
    return load()


@st.cache_resource
def text_index():
    return Index(data())   # TF-IDF over all titles/descriptions, built once per server


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
    return parse_images(row.image_urls)[:n]


def price_txt(v):
    return f"{v / 1e6:.2f}".rstrip("0").rstrip(".").replace(".", ",") + " triệu/tháng"


HINT_MIN_GAP = 25   # % ; measured fair-price error (MAPE 25.5%)


def value_txt(row):
    """What the ML fair-price model says about this rent (src/recsys/price_model.py)."""
    v = getattr(row, "value_pct", np.nan)
    if pd.isna(v):
        return ""
    # The model's typical error is ~25% (docs/report_numbers.json), so a smaller gap is within the noise.
    if v <= -HINT_MIN_GAP:
        return f"Rẻ hơn ~{-v:.0f}% so với phòng tương tự"
    if v >= HINT_MIN_GAP:
        return f"Đắt hơn ~{v:.0f}% so với phòng tương tự"
    return f"Giá trong khoảng thường thấy (±{HINT_MIN_GAP}%)"


def popup_html(row):
    """Self-contained map popup: main photo + thumbnails that swap it, key facts, value hint, source link."""
    imgs = images(row, 5)
    parts = ['<div style="width:240px;font:13px system-ui,sans-serif">']
    if imgs:
        parts.append(f'<img src="{esc(imgs[0])}" loading="lazy" '
                     'style="width:100%;height:150px;object-fit:cover;border-radius:8px">')
        if len(imgs) > 1:
            parts.append('<div style="display:flex;gap:4px;margin:4px 0">' + "".join(
                f'<img src="{esc(u)}" loading="lazy" style="width:44px;height:34px;object-fit:cover;border-radius:4px;'
                'cursor:pointer" onclick="this.parentNode.previousSibling.src=this.src">' for u in imgs) + "</div>")
    parts.append(f"<b>{esc(row.title)}</b><br>{esc(price_txt(row.price_vnd))} · {row.area_est:.0f} m²"
                 f"<br>{esc(row.district)}<br><i>{esc(value_txt(row))}</i>")
    if isinstance(row.listing_url, str):
        parts.append(f'<br><a href="{esc(row.listing_url)}" target="_blank">Xem tin gốc (liên hệ ở đó)</a>')
    return "".join(parts) + "</div>"


# ---------------------------------------------------------------- feedback, favourites, similar rooms
SESSION = st.session_state.setdefault("sid", uuid.uuid4().hex)   # random per browser session, no personal data


def on_vote(row, action):
    feedback.log(SESSION, st.session_state.qkey, pd.DataFrame([row]), action)


def on_fav(lid):
    favs = st.session_state.setdefault("favs", [])
    favs.remove(lid) if lid in favs else favs.append(lid)


def card(row, key, votes=None):
    """One listing card. votes=None hides the 👍/👎 buttons (e.g. in the favourites view)."""
    with st.container(border=True):
        imgs = images(row, 5)
        if imgs:
            st.markdown(f'<img src="{esc(imgs[0])}" style="width:100%;height:150px;object-fit:cover;border-radius:8px" '
                        f'alt="ảnh phòng" loading="lazy">', unsafe_allow_html=True)
        else:
            st.markdown('<div style="height:150px;border-radius:8px;background:#8881;display:flex;align-items:center;'
                        'justify-content:center;opacity:.6">Chưa có ảnh</div>', unsafe_allow_html=True)
        st.markdown(f":blue-badge[{row.house_type}]" if isinstance(row.house_type, str) else "")
        st.markdown(f"**{price_txt(row.price_vnd)}**")
        if value_txt(row):
            st.caption(value_txt(row))
        area = f"~{row.area_est:.0f}" if row.area_imputed else f"{row.area_est:.0f}"
        old = f" · đăng {row.days_old:.0f} ngày trước" if pd.notna(getattr(row, "days_old", np.nan)) else ""
        st.caption(f"{area} m² · {row.district if isinstance(row.district, str) else 'Chưa rõ quận'}{old}")
        st.caption(esc(row.address) if isinstance(row.address, str) else "")
        c1, c2 = st.columns(2)
        if isinstance(row.listing_url, str):
            c1.link_button("Xem tin", row.listing_url, width="stretch")
        if pd.notna(row.latitude):
            with c2.popover("Bản đồ", width="stretch"):
                st.map(pd.DataFrame({"lat": [row.latitude], "lon": [row.longitude]}), zoom=15, height=220)
                st.caption("© OpenStreetMap contributors")
        if len(imgs) > 1:
            with st.popover(f"Xem {len(imgs)} ảnh", width="stretch"):
                st.image(imgs[0], width="stretch")
                st.image(imgs[1:], width=72)
        b = st.columns(4)
        if votes is not None:
            mine = votes.get(row.listing_id)
            b[0].button("👍", key=f"{key}up", help="Phòng này phù hợp", type="primary" if mine == "up" else "secondary",
                        on_click=on_vote, args=(row._asdict(), "up"), width="stretch")
            b[1].button("👎", key=f"{key}dn", help="Không phù hợp", type="primary" if mine == "down" else "secondary",
                        on_click=on_vote, args=(row._asdict(), "down"), width="stretch")
        fav = row.listing_id in st.session_state.get("favs", [])
        b[2].button("♥" if fav else "♡", key=f"{key}fv", help="Lưu / bỏ lưu", on_click=on_fav, args=(row.listing_id,),
                    width="stretch")
        b[3].button("≈", key=f"{key}sm", help="Phòng tương tự", width="stretch",
                    on_click=lambda lid=row.listing_id: st.session_state.update(similar_to=lid))


def card_grid(df, prefix, votes=None, cols=4):
    rows = list(df.itertuples(index=False))
    for i in range(0, len(rows), cols):
        for col, row in zip(st.columns(cols), rows[i:i + cols]):
            with col:
                card(row, f"{prefix}{row.listing_id}", votes)


def rows_for(ids):
    """Full listing rows (in the given order) for cards outside the current search."""
    return d.set_index("listing_id").loc[[i for i in ids if i in d_ids]].reset_index()


def qp(name, default, cast=str):
    """Read a filter from the URL (?lo=1&hi=5&dist=Cầu Giấy,Ba Đình...) so a search can be shared."""
    try:
        v = st.query_params.get(name)
        return default if v is None else cast(v)
    except (ValueError, TypeError):
        return default


def qp_list(name, allowed):
    return [x for x in qp(name, "").split(",") if x in allowed]


d = data()
d_ids = set(d.listing_id)
idx = text_index()
UNI_NAMES = [u["name"] for u in UNIVERSITIES]

# ---------------------------------------------------------------- sidebar: filters (pre-filled from the URL)
with st.sidebar:
    st.header("Bộ lọc")
    q = st.text_input("Tìm theo mô tả", qp("q", ""), placeholder="VD: gác xép, ban công, gần chợ")
    lo, hi = st.slider("Khoảng giá (triệu/tháng)", 0.5, 25.0,
                       tuple(sorted(min(max(qp(k, v, float), 0.5), 25.0) for k, v in (("lo", 1.0), ("hi", 5.0)))), 0.5)
    all_types = sorted(d.house_type.dropna().unique())
    types = st.multiselect("Loại phòng", all_types, qp_list("types", all_types),
                           help="Để trống = mọi loại trừ Nhà nguyên căn; chọn Nhà nguyên căn nếu muốn thuê cả nhà.")
    a_lo, a_hi = st.slider("Diện tích (m²)", 0, 120, (0, 120), 5)
    need = st.multiselect("Tiện nghi", list(AMENITY_VI), qp_list("need", AMENITY_VI), format_func=AMENITY_VI.get)
    all_d = sorted(d.district.dropna().unique())
    districts = st.multiselect("Quận / huyện", all_d, qp_list("dist", all_d))
    uni0 = qp("uni", "")
    uni = st.selectbox("Gần trường đại học", [""] + UNI_NAMES, index=([""] + UNI_NAMES).index(uni0) if uni0 in UNI_NAMES else 0,
                       format_func=lambda x: x or "(không chọn)")
    max_uni = st.slider("Cách trường tối đa (km)", 0.5, 10.0, 3.0, 0.5) if uni else None
    fresh = st.selectbox("Đăng trong vòng", [None, 7, 30, 90], format_func=lambda x: "Không giới hạn" if x is None else f"{x} ngày",
                         help="Chỉ khoảng 30% tin có ngày đăng; tin không rõ ngày luôn được giữ.")
    sources = st.multiselect("Nguồn tin", sorted(d.platform.dropna().unique()))
    shared = st.checkbox("Cả tin ở ghép / slot", False)
    RK = ranker_info()
    ranker = "ml"
    if RK:
        ranker = st.radio("Cách xếp hạng", ["ml", "hand"], horizontal=True,
                          format_func={"ml": "Học máy", "hand": "Trọng số tay"}.get,
                          help="Học máy: trọng số học từ các phiếu 👍/👎 (xem README). Trọng số tay: công thức đặt tay "
                               "30/25/25/20. Trên dữ liệu hiện có hai cách chưa phân biệt được tốt/xấu.")
    st.caption("Tin chưa rõ diện tích vẫn được giữ khi lọc diện tích.")
    st.query_params.from_dict({k: v for k, v in {
        "q": q, "lo": lo, "hi": hi, "types": ",".join(types), "need": ",".join(need), "dist": ",".join(districts),
        "uni": uni}.items() if v not in ("", None)})
    st.caption("Địa chỉ trang hiện tại đã chứa bộ lọc — sao chép để chia sẻ.")

# ---------------------------------------------------------------- results
res = recommend(d, hi * 1e6, districts, None, need, uni or None, max_uni, None, None, 10 ** 6,
                include_shared=shared, per_building=0, max_days_old=fresh, ranker=ranker, whole_house=WHOLE_HOUSE in types)
# recommend() returns a trimmed set of columns; bring back what the cards and the map need
extra = d.set_index("listing_id")[["house_type", "address", "latitude", "longitude", "image_urls", "distance_to_center_km"]]
res = res.join(extra, on="listing_id")
res = res[res.price_vnd >= lo * 1e6]
if types:
    res = res[res.house_type.isin(types)]
if sources:
    res = res[res.platform.isin(sources)]
if (a_lo, a_hi) != (0, 120):
    known = res.area_imputed == False  # noqa: E712  (area_est equals the real area when not imputed)
    res = res[~known | ((res.area_est >= a_lo) & (res.area_est <= a_hi))]
res = res.assign(rank_score=res.score)
if q.strip() and len(res):   # free-text: blend the recommender score with TF-IDF similarity to the query
    sim = idx.text_scores(q, res.listing_id.tolist())
    res = res.assign(text_sim=sim, rank_score=0.5 * res.score + 0.5 * sim / max(sim.max(), 1e-9))
    res = res[res.text_sim > 0.01]

st.session_state.qkey = feedback.query_key(dict(q=q, lo=lo, hi=hi, types=types, a=(a_lo, a_hi), need=need,
                                                dist=districts, uni=uni, max_uni=max_uni, fresh=fresh,
                                                src=sources, shared=shared, ranker=ranker))
votes = feedback.votes(SESSION, st.session_state.qkey)

st.title("🏠 Tìm phòng trọ Hà Nội")
n_fav = len(st.session_state.get("favs", []))
# a switch instead of st.tabs: tabs run every body on each rerun, and the map body is the expensive one
view = st.segmented_control("Chế độ xem", ["Trang chủ", "Bản đồ", f"Đã lưu ({n_fav})"], default="Trang chủ",
                            label_visibility="collapsed") or "Trang chủ"

if st.session_state.get("similar_to") in d_ids:   # "≈" pressed on a card
    base = rows_for([st.session_state.similar_to]).iloc[0]
    with st.container(border=True):
        h = st.columns([5, 1])
        h[0].markdown(f"#### Phòng tương tự: {esc(base.title)}")
        if h[1].button("Đóng", key="close_sim"):
            st.session_state.similar_to = None
            st.rerun()
        card_grid(rows_for(idx.similar(base.listing_id, k=8)), "sim")

if view == "Trang chủ":
    top = st.columns([3, 2, 2])
    top[0].markdown(f"### {len(res):,} kết quả phù hợp".replace(",", "."))
    sort_name = top[1].selectbox("Sắp xếp", list(SORTS), label_visibility="collapsed")
    size = top[2].selectbox("Hiển thị", PAGE_SIZES, index=1, format_func=lambda n: f"{n} tin / trang",
                            label_visibility="collapsed")
    col, asc = SORTS[sort_name]
    shown = res.sort_values("rank_score" if col == "score" else col, ascending=asc, na_position="last")
    shown = shown.assign(rank=np.arange(1, len(shown) + 1))
    pages = max(1, -(-len(shown) // size))
    sig = (st.session_state.qkey, sort_name, size)
    if st.session_state.get("sig") != sig:   # any filter change -> back to page 1
        st.session_state.update(sig=sig, page=1)
    page = min(st.session_state.get("page", 1), pages)
    if shown.empty:
        st.warning("Không có tin nào khớp, hãy nới bớt bộ lọc.")
    else:
        page_rows = shown.iloc[(page - 1) * size: page * size]
        feedback.log(SESSION, st.session_state.qkey, page_rows, "impression")
        st.caption("Bấm 👍 / 👎 để đánh giá gợi ý — phản hồi được lưu trên máy này và dùng để học trọng số xếp hạng.")
        card_grid(page_rows, "l", votes)
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

elif view == "Bản đồ":
    st.markdown("#### CHẤM ĐIỂM TRÊN BẢN ĐỒ ĐỂ TÌM PHÒNG XUNG QUANH")
    c1, c2 = st.columns(2)
    radius = c1.selectbox("Bán kính tìm kiếm", [0.5, 1, 2, 3, 5, 10], index=2, format_func=lambda r: f"{r} km")
    two = c2.toggle("Hai điểm (VD: trường + chỗ làm)", help="Bấm điểm thứ nhất rồi điểm thứ hai; phòng phải nằm "
                                                          "trong bán kính của cả hai điểm.")
    on_map = res.dropna(subset=["latitude", "longitude"]).head(MAX_MAP)
    pts = [p for p in (st.session_state.get("click"), st.session_state.get("click2") if two else None) if p]
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
    if pts:
        rings = folium.FeatureGroup(name="Vùng tìm").add_to(m)
        for i, p in enumerate(pts):
            folium.Marker(p, icon=folium.Icon(color="cadetblue", icon="crosshairs", prefix="fa"),
                          tooltip=f"Điểm {'AB'[i]}").add_to(m)
            folium.Circle(p, radius=radius * 1000, color="#0d9488", weight=3, dash_array="8 6", fill=True,
                          fill_color="#14b8a6", fill_opacity=0.10, class_name="area-ring").add_to(rings)
        FlyTo(rings).add_to(m)   # glide from the previous view into the chosen area(s)
    out = st_folium(m, height=520, use_container_width=True, returned_objects=["last_clicked"], key="map")
    pt = out and out.get("last_clicked")
    if pt and [pt["lat"], pt["lng"]] not in pts:
        new = [pt["lat"], pt["lng"]]
        st.session_state.prev_click = new if not pts else pts[-1]
        if two and len(pts) == 1:
            st.session_state.click2 = new
        else:
            st.session_state.update(click=new, click2=None)
        st.rerun()
    st.markdown("Giá/tháng: <span style='background:#bbf7d0;color:#14532d;padding:2px 9px;border-radius:10px'>&lt; 3 triệu</span> "
                "<span style='background:#bfdbfe;color:#1e3a8a;padding:2px 9px;border-radius:10px'>3–5 triệu</span> "
                "<span style='background:#fecdd3;color:#881337;padding:2px 9px;border-radius:10px'>&gt; 5 triệu</span> "
                "· hình tròn xám có số = nhiều phòng gộp lại, bấm để phóng to", unsafe_allow_html=True)
    st.caption(f"Hiển thị tối đa {MAX_MAP} tin phù hợp bộ lọc (gộp nhóm khi thu nhỏ). "
               "Bản đồ: © OpenStreetMap contributors.")
    if pts:
        lat, lon = np.radians(res.latitude.astype(float)), np.radians(res.longitude.astype(float))
        kms = []
        for p in pts:
            a = (np.sin((lat - np.radians(p[0])) / 2) ** 2
                 + np.cos(lat) * np.cos(np.radians(p[0])) * np.sin((lon - np.radians(p[1])) / 2) ** 2)
            kms.append(12742 * np.arcsin(np.sqrt(a)))
        near = res.assign(km=np.maximum.reduce(kms)).query("km <= @radius").sort_values("km")
        where = "cả hai điểm" if len(pts) == 2 else "điểm đã chọn"
        st.markdown(f"### {len(near)} phòng trong bán kính {radius} km quanh {where}")
        if two and len(pts) == 1:
            st.info("Bấm điểm thứ hai trên bản đồ.")
        if near.empty:
            st.info("Không có phòng nào, thử tăng bán kính hoặc nới bộ lọc.")
        else:
            card_grid(near.head(24).assign(rank=np.arange(1, min(len(near), 24) + 1)), "n", votes)
            if len(near) > 24:
                st.caption("Hiển thị 24 phòng gần nhất.")
        if st.button("Xóa điểm đã chọn"):
            st.session_state.update(click=None, click2=None, prev_click=None)
            st.rerun()
    else:
        st.info("Bấm vào một vị trí trên bản đồ để xem các phòng quanh đó.")

else:   # saved rooms + side-by-side comparison
    favs = st.session_state.get("favs", [])
    if not favs:
        st.info("Chưa lưu phòng nào — bấm ♡ trên thẻ phòng để lưu.")
    else:
        fr = rows_for(favs)
        st.markdown("#### So sánh (tối đa 4 phòng)")
        pick = st.multiselect("Chọn phòng để so sánh", fr.listing_id.tolist(), fr.listing_id.tolist()[:4], max_selections=4,
                              format_func=lambda i: fr.set_index("listing_id").title[i][:50])
        if pick:
            c = fr.set_index("listing_id").loc[pick]
            table = pd.DataFrame({
                "Giá (triệu)": (c.price_vnd / 1e6).round(2), "Giá hợp lý ước tính (triệu)": (c.fair_price / 1e6).round(2),
                "So với phòng tương tự": c.value_pct.map(lambda v: f"{v:+.0f}%"),
                "Diện tích (m²)": c.area_est.round(0), "Quận": c.district, "Loại": c.house_type,
                "Cách trung tâm (km)": c.distance_to_center_km.round(1), "Tiện nghi": c.amenities_list,
                "Đăng (ngày trước)": c.days_old}, index=c.title.str[:40]).T
            st.dataframe(table, width="stretch")
        st.markdown("#### Tất cả phòng đã lưu")
        card_grid(fr, "fav")

st.caption("Diện tích có dấu ~ là ước lượng; 'rẻ hơn / đắt hơn' so với giá hợp lý do mô hình học máy ước tính từ "
           "các phòng tương tự. Ảnh lấy từ trang nguồn của tin; tin từ Facebook không hiển thị ảnh. "
           "Số điện thoại không hiển thị — liên hệ qua tin gốc.")
