"""Reference points copied verbatim from the unified-crawl-data branch (src/pipelines/clean_and_visualize_unified.py)
so distance features can be recomputed for rows whose coordinates were fixed."""

METRO_STATIONS = [
    # Line 2A (Cát Linh - Hà Đông)
    {"line": "Line 2A", "name": "Cát Linh", "lat": 21.0287, "lng": 105.8277},
    {"line": "Line 2A", "name": "La Thành", "lat": 21.0205, "lng": 105.8235},
    {"line": "Line 2A", "name": "Thái Hà", "lat": 21.0125, "lng": 105.8196},
    {"line": "Line 2A", "name": "Láng", "lat": 21.0051, "lng": 105.8143},
    {"line": "Line 2A", "name": "Thượng Đình", "lat": 20.9972, "lng": 105.8118},
    {"line": "Line 2A", "name": "Vành Đai 3", "lat": 20.9902, "lng": 105.8033},
    {"line": "Line 2A", "name": "Phùng Khoang", "lat": 20.9839, "lng": 105.7925},
    {"line": "Line 2A", "name": "Văn Quán", "lat": 20.9781, "lng": 105.7828},
    {"line": "Line 2A", "name": "Hà Đông", "lat": 20.9715, "lng": 105.7745},
    {"line": "Line 2A", "name": "La Khê", "lat": 20.9632, "lng": 105.7638},
    {"line": "Line 2A", "name": "Văn Khê", "lat": 20.9547, "lng": 105.7533},
    {"line": "Line 2A", "name": "Yên Nghĩa", "lat": 20.9497, "lng": 105.7447},
    # Line 3 (Nhổn - Ga Hà Nội, Elevated section)
    {"line": "Line 3", "name": "Nhổn", "lat": 21.0538, "lng": 105.7335},
    {"line": "Line 3", "name": "Minh Khai", "lat": 21.0503, "lng": 105.7441},
    {"line": "Line 3", "name": "Phú Diễn", "lat": 21.0475, "lng": 105.7552},
    {"line": "Line 3", "name": "Cầu Diễn", "lat": 21.0425, "lng": 105.7677},
    {"line": "Line 3", "name": "Lê Đức Thọ", "lat": 21.0381, "lng": 105.7766},
    {"line": "Line 3", "name": "Đại học Quốc gia", "lat": 21.0360, "lng": 105.7830},
    {"line": "Line 3", "name": "Chùa Hà", "lat": 21.0336, "lng": 105.7944},
    {"line": "Line 3", "name": "Cầu Giấy", "lat": 21.0298, "lng": 105.8048},
]

UNIVERSITIES = [
    # Cầu Giấy Cluster
    {"name": "ĐH Quốc gia (VNU)", "cluster": "Cầu Giấy", "lat": 21.0378, "lng": 105.7818},
    {"name": "ĐH Sư phạm (HNUE)", "cluster": "Cầu Giấy", "lat": 21.0366, "lng": 105.7839},
    {"name": "ĐH Thương mại (TMU)", "cluster": "Cầu Giấy", "lat": 21.0365, "lng": 105.7725},
    {"name": "HV Báo chí (AJC)", "cluster": "Cầu Giấy", "lat": 21.0372, "lng": 105.7925},
    {"name": "ĐH Giao thông Vận tải (UTC)", "cluster": "Cầu Giấy", "lat": 21.0289, "lng": 105.8038},
    # Đống Đa - Chùa Láng Cluster
    {"name": "ĐH Ngoại thương (FTU)", "cluster": "Chùa Láng", "lat": 21.0232, "lng": 105.8055},
    {"name": "ĐH Luật Hà Nội (HLU)", "cluster": "Chùa Láng", "lat": 21.0185, "lng": 105.8115},
    # Đống Đa - Chùa Bộc Cluster
    {"name": "HV Ngân hàng (BA)", "cluster": "Chùa Bộc", "lat": 21.0092, "lng": 105.8290},
    {"name": "ĐH Thủy lợi (TLU)", "cluster": "Chùa Bộc", "lat": 21.0075, "lng": 105.8242},
    {"name": "ĐH Y Hà Nội (HMU)", "cluster": "Chùa Bộc", "lat": 21.0028, "lng": 105.8315},
    # Bách - Kinh - Xây Cluster (Hai Bà Trưng)
    {"name": "ĐH Bách khoa (HUST)", "cluster": "Bách - Kinh - Xây", "lat": 21.0051, "lng": 105.8432},
    {"name": "ĐH Kinh tế Quốc dân (NEU)", "cluster": "Bách - Kinh - Xây", "lat": 20.9965, "lng": 105.8425},
    {"name": "ĐH Xây dựng (HUCE)", "cluster": "Bách - Kinh - Xây", "lat": 21.0035, "lng": 105.8428},
    {"name": "ĐH Mở Hà Nội (HOU)", "cluster": "Bách - Kinh - Xây", "lat": 21.0055, "lng": 105.8475},
    # Thanh Xuân - Hà Đông Corridor
    {"name": "ĐH Hà Nội (HANU)", "cluster": "Thanh Xuân", "lat": 20.9885, "lng": 105.7942},
    {"name": "ĐH KHXH&NV / KHTN (VNU)", "cluster": "Thanh Xuân", "lat": 20.9990, "lng": 105.8090},
    {"name": "HV Bưu chính (PTIT)", "cluster": "Hà Đông", "lat": 20.9805, "lng": 105.7875},
    {"name": "ĐH Kiến trúc (HAU)", "cluster": "Hà Đông", "lat": 20.9825, "lng": 105.7895},
    {"name": "ĐH Thăng Long", "cluster": "Hoàng Mai", "lat": 20.9765, "lng": 105.8165},
    # Bắc Từ Liêm Cluster
    {"name": "ĐH Công nghiệp (HaUI)", "cluster": "Bắc Từ Liêm", "lat": 21.0542, "lng": 105.7355},
    {"name": "HV Tài chính (AOF)", "cluster": "Bắc Từ Liêm", "lat": 21.0745, "lng": 105.7725},
    {"name": "ĐH Mỏ - Địa chất (HUMG)", "cluster": "Bắc Từ Liêm", "lat": 21.0725, "lng": 105.7745},
]
HANOI_CENTER = (21.0285, 105.8542)  # Hoàn Kiếm Lake / Post Office
