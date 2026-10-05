"""Streamlit UI for the recommender:  streamlit run src/recsys/app.py  (from the repo root)."""
import sys
from pathlib import Path

import folium
import streamlit as st
from streamlit_folium import st_folium

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # streamlit puts src/recsys, not the repo root, on sys.path
from src.recsys.recommend import AMENITIES, load, recommend
from src.recsys.ref_points import METRO_STATIONS, UNIVERSITIES

st.set_page_config(page_title="Tìm phòng trọ Hà Nội", layout="wide")


@st.cache_data
def data():
    return load()


d = data()
with st.sidebar:
    st.header("Bộ lọc")
    budget = st.slider("Ngân sách tối đa (triệu/tháng)", 1.0, 25.0, 4.0, 0.5) * 1e6
    districts = st.multiselect("Quận", sorted(d.district.dropna().unique()))
    unis = sorted(d.nearest_university.dropna().unique())
    uni = st.selectbox("Gần trường", [""] + unis, format_func=lambda x: x or "(không)")
    max_uni = st.slider("Cách trường tối đa (km)", 0.5, 10.0, 3.0, 0.5) if uni else None
    max_metro = st.slider("Cách metro tối đa (km)", 0.5, 10.0, 10.0, 0.5)
    min_area = st.number_input("Diện tích tối thiểu (m²)", 0, 100, 0)
    types = sorted(d.house_type.dropna().unique())
    house_type = st.selectbox("Loại phòng", [""] + types, format_func=lambda x: x or "(tất cả)")
    need = st.multiselect("Tiện nghi bắt buộc", AMENITIES)
    refs = st.checkbox("Hiện ga metro và trường đại học trên bản đồ", True)
    shared = st.checkbox("Cả tin ở ghép / slot", False)
    top = st.slider("Số kết quả", 5, 50, 15)

r = recommend(d, budget, districts, min_area or None, need, uni or None, max_uni,
              None if max_metro >= 10 else max_metro, house_type or None, top, include_shared=shared)
st.title("Gợi ý phòng trọ Hà Nội")
if r.empty:
    st.warning("Không có tin nào khớp, hãy nới bớt bộ lọc.")
    st.stop()

# recommend() drops lat/lon from its output; join them back by id
ll = d.set_index("listing_id")[["latitude", "longitude"]]
r = r.join(ll, on="listing_id")
pts = r.dropna(subset=["latitude", "longitude"])
c1, c2 = st.columns([3, 2])
with c1:
    m = folium.Map(location=[pts.latitude.mean(), pts.longitude.mean()] if len(pts) else [21.03, 105.82],
                   zoom_start=13)
    for i, x in enumerate(pts.itertuples(), 1):
        link = f'<a href="{x.listing_url}" target="_blank">mở tin</a>' if isinstance(x.listing_url, str) else ""
        area = f"~{x.area_est:.0f}" if x.area_imputed else f"{x.area_est:.0f}"
        folium.Marker([x.latitude, x.longitude],
                      tooltip=f"#{i} {x.price_vnd / 1e6:.1f} tr",
                      popup=folium.Popup(f"<b>{x.title}</b><br>{x.price_vnd / 1e6:.2f} tr/tháng · {area} m²<br>"
                                         f"{x.district}, {x.ward}<br>{link}", max_width=300)).add_to(m)
    if refs:
        for u in UNIVERSITIES:
            folium.Marker([u["lat"], u["lng"]], tooltip=u["name"],
                          icon=folium.Icon(color="green", icon="graduation-cap", prefix="fa")).add_to(m)
        for s_ in METRO_STATIONS:
            folium.CircleMarker([s_["lat"], s_["lng"]], radius=6, color="#7c3aed", fill=True, fill_opacity=0.9,
                                tooltip=f"Ga {s_['name']} ({s_['line']})").add_to(m)
    st_folium(m, height=520, use_container_width=True, returned_objects=[])
    if len(pts) < len(r):
        st.caption(f"{len(r) - len(pts)} tin thiếu tọa độ nên chưa có trên bản đồ (vẫn có trong bảng).")
with c2:
    st.dataframe(r.drop(columns=["latitude", "longitude", "amenities_list"], errors="ignore"),
                 hide_index=True, column_config={"listing_url": st.column_config.LinkColumn("tin")})
st.caption("Bản đồ: © OpenStreetMap contributors. Diện tích có dấu ~ là ước lượng. Xanh lá = trường đại học, chấm tím = ga metro. Mỗi tòa nhà (cùng số nhà/ngõ) chỉ hiện phòng tốt nhất.")
