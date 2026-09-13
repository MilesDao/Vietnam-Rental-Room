"""
src/parse/normalizer.py - Normalization, Feature Engineering, Geocoding, and Data Cleaning Engine

Extracts:
1. Utility Prices (electric, water, wifi, service, parking)
2. Canonical District & Ward mapping for Hanoi & HCM
3. Geocoding: Latitude & Longitude (via Geopy Nominatim + Offline Geo-Centroid Database)
4. Canonical House Type classification
5. Boolean Amenity Flags (AC, heater, fridge, washer, elevator, balcony, fire safety, pet)
6. Cleaned and normalized text
"""

import html
import logging
import re
import socket
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# ==============================================================================
# 1. GEO MAPPING DICTIONARIES (HANOI & HCM)
# ==============================================================================

HANOI_DISTRICTS = [
    "Ba Đình", "Bắc Từ Liêm", "Cầu Giấy", "Đống Đa", "Hà Đông", "Hai Bà Trưng",
    "Hoàn Kiếm", "Hoàng Mai", "Long Biên", "Nam Từ Liêm", "Tây Hồ", "Thanh Xuân",
    "Sơn Tây", "Ba Vì", "Chương Mỹ", "Đan Phượng", "Đông Anh", "Gia Lâm",
    "Hoài Đức", "Mê Linh", "Mỹ Đức", "Phú Xuyên", "Phúc Thọ", "Quốc Oai",
    "Sóc Sơn", "Thạch Thất", "Thanh Oai", "Thanh Trì", "Thường Tín", "Ứng Hòa"
]

HCM_DISTRICTS = [
    "Quận 1", "Quận 3", "Quận 4", "Quận 5", "Quận 6", "Quận 7", "Quận 8",
    "Quận 10", "Quận 11", "Quận 12", "Bình Thạnh", "Gò Vấp", "Phú Nhuận",
    "Tân Bình", "Tân Phú", "Bình Tân", "Thủ Đức", "Bình Chánh", "Cần Giờ",
    "Củ Chi", "Hóc Môn", "Nhà Bè"
]

# Common Hanoi Ward / Landmark -> District lookup
HANOI_WARD_DISTRICT_MAP = {
    # Cầu Giấy
    "dịch vọng": "Cầu Giấy", "dịch vọng hậu": "Cầu Giấy", "mai dịch": "Cầu Giấy",
    "nghĩa đô": "Cầu Giấy", "nghĩa tân": "Cầu Giấy", "quan hoa": "Cầu Giấy",
    "trung hòa": "Cầu Giấy", "yên hòa": "Cầu Giấy", "trần thái tông": "Cầu Giấy",
    "duy tân": "Cầu Giấy", "xuân thủy": "Cầu Giấy", "hoàng quốc việt": "Cầu Giấy",
    # Đống Đa
    "cát linh": "Đống Đa", "hàng bột": "Đống Đa", "khâm thiên": "Đống Đa",
    "khương thượng": "Đống Đa", "kim liên": "Đống Đa", "láng hạ": "Đống Đa",
    "láng thượng": "Đống Đa", "nam đồng": "Đống Đa", "ngã tư sở": "Đống Đa",
    "ô chợ dừa": "Đống Đa", "phương liên": "Đống Đa", "phương mai": "Đống Đa",
    "quang trung": "Đống Đa", "quốc tử giám": "Đống Đa", "thịnh quang": "Đống Đa",
    "thổ quan": "Đống Đa", "trung liệt": "Đống Đa", "trung phụng": "Đống Đa",
    "trung tự": "Đống Đa", "văn chương": "Đống Đa", "văn miếu": "Đống Đa",
    "chùa bộc": "Đống Đa", "thái hà": "Đống Đa", "xã đàn": "Đống Đa",
    # Thanh Xuân
    "hạ đình": "Thanh Xuân", "khương đình": "Thanh Xuân", "khương mai": "Thanh Xuân",
    "khương trung": "Thanh Xuân", "kim giang": "Thanh Xuân", "nhân chính": "Thanh Xuân",
    "phương liệt": "Thanh Xuân", "thanh xuân bắc": "Thanh Xuân", "thanh xuân nam": "Thanh Xuân",
    "thanh xuân trung": "Thanh Xuân", "thượng đình": "Thanh Xuân", "nguyễn trãi": "Thanh Xuân",
    "quan nhân": "Thanh Xuân", "triều khúc": "Thanh Xuân",
    # Nam Từ Liêm
    "cầu diễn": "Nam Từ Liêm", "đại mỗ": "Nam Từ Liêm", "mễ trì": "Nam Từ Liêm",
    "mỹ đình 1": "Nam Từ Liêm", "mỹ đình 2": "Nam Từ Liêm", "mỹ đình": "Nam Từ Liêm",
    "phú đô": "Nam Từ Liêm", "tây mỗ": "Nam Từ Liêm", "trung văn": "Nam Từ Liêm",
    "xuân phương": "Nam Từ Liêm", "lê đức thọ": "Nam Từ Liêm", "đình thôn": "Nam Từ Liêm",
    # Bắc Từ Liêm
    "cổ nhuế 1": "Bắc Từ Liêm", "cổ nhuế 2": "Bắc Từ Liêm", "cổ nhuế": "Bắc Từ Liêm",
    "đức thắng": "Bắc Từ Liêm", "đông ngạc": "Bắc Từ Liêm", "thụy phương": "Bắc Từ Liêm",
    "liên mạc": "Bắc Từ Liêm", "minh khai": "Bắc Từ Liêm", "phú diễn": "Bắc Từ Liêm",
    "phúc diễn": "Bắc Từ Liêm", "tây tựu": "Bắc Từ Liêm", "thượng cát": "Bắc Từ Liêm",
    "xuân đỉnh": "Bắc Từ Liêm", "xuân tảo": "Bắc Từ Liêm", "nhổn": "Bắc Từ Liêm",
    # Hai Bà Trưng
    "bách khoa": "Hai Bà Trưng", "bạch đằng": "Hai Bà Trưng", "bạch mai": "Hai Bà Trưng",
    "cầu dền": "Hai Bà Trưng", "đống mác": "Hai Bà Trưng", "đồng nhân": "Hai Bà Trưng",
    "đồng tâm": "Hai Bà Trưng", "lê đại hành": "Hai Bà Trưng", "minh khai": "Hai Bà Trưng",
    "nguyễn du": "Hai Bà Trưng", "phạm đình hổ": "Hai Bà Trưng", "phố huế": "Hai Bà Trưng",
    "quỳnh lôi": "Hai Bà Trưng", "quỳnh mai": "Hai Bà Trưng", "thanh lương": "Hai Bà Trưng",
    "thanh nhàn": "Hai Bà Trưng", "trương định": "Hai Bà Trưng", "vĩnh tuy": "Hai Bà Trưng",
    "tạ quang bửu": "Hai Bà Trưng", "đại la": "Hai Bà Trưng",
    # Ba Đình
    "cống vị": "Ba Đình", "điện biên": "Ba Đình", "đội cấn": "Ba Đình",
    "giảng võ": "Ba Đình", "kim mã": "Ba Đình", "liễu giai": "Ba Đình",
    "ngọc hà": "Ba Đình", "ngọc khánh": "Ba Đình", "nguyễn trung trực": "Ba Đình",
    "phúc xá": "Ba Đình", "quán thánh": "Ba Đình", "thành công": "Ba Đình",
    "trúc bạch": "Ba Đình", "vĩnh phúc": "Ba Đình",
    # Hà Đông
    "biên giang": "Hà Đông", "đồng mai": "Hà Đông", "dương nội": "Hà Đông",
    "hà cầu": "Hà Đông", "kiến hưng": "Hà Đông", "la khê": "Hà Đông",
    "mộ lao": "Hà Đông", "nguyễn trãi": "Hà Đông", "phú la": "Hà Đông",
    "phú lãm": "Hà Đông", "phú lương": "Hà Đông", "phúc la": "Hà Đông",
    "quang trung": "Hà Đông", "vạn phúc": "Hà Đông", "văn quán": "Hà Đông",
    "yên nghĩa": "Hà Đông", "yết kiêu": "Hà Đông", "xa la": "Hà Đông",
    # Hoàng Mai
    "đại kim": "Hoàng Mai", "định công": "Hoàng Mai", "giáp bát": "Hoàng Mai",
    "hoàng liệt": "Hoàng Mai", "hoàng văn thụ": "Hoàng Mai", "lĩnh nam": "Hoàng Mai",
    "mai động": "Hoàng Mai", "tân mai": "Hoàng Mai", "thanh trì": "Hoàng Mai",
    "thịnh liệt": "Hoàng Mai", "trần phú": "Hoàng Mai", "tương mai": "Hoàng Mai",
    "vĩnh hưng": "Hoàng Mai", "yên sở": "Hoàng Mai", "linh đàm": "Hoàng Mai",
    # Tây Hồ
    "bưởi": "Tây Hồ", "nhật tân": "Tây Hồ", "phú thượng": "Tây Hồ",
    "quảng an": "Tây Hồ", "thụy khuê": "Tây Hồ", "tứ liên": "Tây Hồ",
    "xuân la": "Tây Hồ", "yên phụ": "Tây Hồ", "lạc long quân": "Tây Hồ",
    # Long Biên
    "bồ đề": "Long Biên", "cự khối": "Long Biên", "đức giang": "Long Biên",
    "gia thụy": "Long Biên", "giang biên": "Long Biên", "long biên": "Long Biên",
    "ngọc lâm": "Long Biên", "ngọc thụy": "Long Biên", "phúc đồng": "Long Biên",
    "phúc lợi": "Long Biên", "sài đồng": "Long Biên", "thạch bàn": "Long Biên",
    "thượng thanh": "Long Biên", "việt hưng": "Long Biên",
    # Hoàn Kiếm
    "chương dương": "Hoàn Kiếm", "cửa đông": "Hoàn Kiếm", "cửa nam": "Hoàn Kiếm",
    "đồng xuân": "Hoàn Kiếm", "hàng bạc": "Hoàn Kiếm", "hàng bài": "Hoàn Kiếm",
    "hàng bồ": "Hoàn Kiếm", "hàng bông": "Hoàn Kiếm", "hàng buồm": "Hoàn Kiếm",
    "hàng đào": "Hoàn Kiếm", "hàng gai": "Hoàn Kiếm", "hàng mã": "Hoàn Kiếm",
    "hàng trống": "Hoàn Kiếm", "lý thái tổ": "Hoàn Kiếm", "phan chu trinh": "Hoàn Kiếm",
    "phúc tân": "Hoàn Kiếm", "trần hưng đạo": "Hoàn Kiếm", "tràng tiền": "Hoàn Kiếm",
}

# ==============================================================================
# 2. PRECISE GEO-COORDINATE DATABASE (CENTROIDS OF WARDS & DISTRICTS)
# ==============================================================================

GEO_COORDINATES_MAP: Dict[str, Tuple[float, float]] = {
    # Cầu Giấy
    "dịch vọng hậu": (21.033282, 105.784405),
    "dịch vọng": (21.035411, 105.793214),
    "mai dịch": (21.040183, 105.775834),
    "nghĩa đô": (21.047802, 105.796791),
    "nghĩa tân": (21.041695, 105.793856),
    "quan hoa": (21.036662, 105.799754),
    "trung hòa": (21.011855, 105.797534),
    "yên hòa": (21.020583, 105.790924),
    "trần thái tông": (21.031500, 105.786200),
    "duy tân": (21.031000, 105.783000),
    "xuân thủy": (21.036700, 105.781200),
    "hoàng quốc việt": (21.046000, 105.794000),
    "cầu giấy": (21.036237, 105.790583),

    # Đống Đa
    "cát linh": (21.029800, 105.828500),
    "hàng bột": (21.025500, 105.832000),
    "khâm thiên": (21.018500, 105.835000),
    "khương thượng": (21.008000, 105.824000),
    "kim liên": (21.011000, 105.836000),
    "láng hạ": (21.016000, 105.815000),
    "láng thượng": (21.025000, 105.803000),
    "nam đồng": (21.013500, 105.828000),
    "ngã tư sở": (21.002000, 105.821000),
    "ô chợ dừa": (21.021000, 105.827000),
    "phương liên": (21.012000, 105.840000),
    "phương mai": (21.005000, 105.839000),
    "quang trung": (21.020000, 105.830000),
    "quốc tử giám": (21.028000, 105.834000),
    "thịnh quang": (21.006000, 105.818000),
    "thổ quan": (21.017000, 105.833000),
    "trung liệt": (21.012500, 105.822000),
    "trung phụng": (21.016500, 105.836500),
    "trung tự": (21.009000, 105.833000),
    "văn chương": (21.023000, 105.834500),
    "văn miếu": (21.028500, 105.835500),
    "chùa bộc": (21.007500, 105.827500),
    "thái hà": (21.013000, 105.819000),
    "xã đàn": (21.015500, 105.833500),
    "đống đa": (21.018072, 105.829949),

    # Thanh Xuân
    "hạ đình": (20.990000, 105.810000),
    "khương đình": (20.985000, 105.816000),
    "khương mai": (20.999000, 105.826000),
    "khương trung": (20.997000, 105.818000),
    "kim giang": (20.980000, 105.817000),
    "nhân chính": (21.004000, 105.803000),
    "phương liệt": (20.996000, 105.840000),
    "thanh xuân bắc": (20.994000, 105.799000),
    "thanh xuân nam": (20.989000, 105.799500),
    "thanh xuân trung": (20.995000, 105.806000),
    "thượng đình": (20.998000, 105.812000),
    "nguyễn trãi": (20.992000, 105.805000),
    "triều khúc": (20.982000, 105.798000),
    "thanh xuân": (20.993748, 105.807504),

    # Nam Từ Liêm
    "cầu diễn": (21.042000, 105.762000),
    "đại mỗ": (20.995000, 105.755000),
    "mễ trì": (21.013000, 105.780000),
    "mỹ đình 1": (21.022000, 105.772000),
    "mỹ đình 2": (21.031000, 105.771000),
    "mỹ đình": (21.026000, 105.771500),
    "phú đô": (21.010000, 105.768000),
    "tây mỗ": (21.002000, 105.742000),
    "trung văn": (20.998000, 105.787000),
    "xuân phương": (21.035000, 105.743000),
    "đình thôn": (21.018000, 105.776000),
    "lê đức thọ": (21.028000, 105.769000),
    "nam từ liêm": (21.015243, 105.765435),

    # Bắc Từ Liêm
    "cổ nhuế 1": (21.055000, 105.778000),
    "cổ nhuế 2": (21.065000, 105.765000),
    "cổ nhuế": (21.060000, 105.770000),
    "đông ngạc": (21.082000, 105.775000),
    "đức thắng": (21.077000, 105.772000),
    "liên mạc": (21.095000, 105.750000),
    "minh khai": (21.050000, 105.740000),
    "phú diễn": (21.046000, 105.756000),
    "phúc diễn": (21.048000, 105.748000),
    "tây tựu": (21.060000, 105.720000),
    "thượng cát": (21.098000, 105.735000),
    "thụy phương": (21.090000, 105.770000),
    "xuân đỉnh": (21.068000, 105.789000),
    "xuân tảo": (21.064000, 105.795000),
    "nhổn": (21.054000, 105.733000),
    "bắc từ liêm": (21.066465, 105.757049),

    # Hai Bà Trưng
    "bách khoa": (21.006450, 105.845320),
    "bạch đằng": (21.015000, 105.865000),
    "bạch mai": (21.001000, 105.850000),
    "cầu dền": (21.009000, 105.850000),
    "đống mác": (21.013000, 105.860000),
    "đồng nhân": (21.012000, 105.858000),
    "đồng tâm": (20.999000, 105.844000),
    "lê đại hành": (21.012500, 105.848000),
    "nguyễn du": (21.018000, 105.847000),
    "phạm đình hổ": (21.015500, 105.856000),
    "phố huế": (21.015000, 105.852000),
    "quỳnh lôi": (20.999500, 105.856000),
    "quỳnh mai": (21.002000, 105.857000),
    "thanh lương": (21.006000, 105.867000),
    "thanh nhàn": (21.005000, 105.855000),
    "trương định": (20.995000, 105.850000),
    "vĩnh tuy": (21.001000, 105.870000),
    "đại la": (20.998000, 105.847000),
    "hai bà trưng": (21.006688, 105.851978),

    # Ba Đình
    "cống vị": (21.036000, 105.811000),
    "điện biên": (21.031000, 105.839000),
    "đội cấn": (21.036500, 105.823000),
    "giảng võ": (21.026000, 105.822000),
    "kim mã": (21.031000, 105.822000),
    "liễu giai": (21.038000, 105.815000),
    "ngọc hà": (21.038500, 105.830000),
    "ngọc khánh": (21.030000, 105.813000),
    "nguyễn trung trực": (21.044000, 105.845000),
    "phúc xá": (21.046000, 105.848000),
    "quán thánh": (21.042000, 105.841000),
    "thành công": (21.022000, 105.818000),
    "trúc bạch": (21.044500, 105.839000),
    "vĩnh phúc": (21.041000, 105.808000),
    "ba đình": (21.034138, 105.824208),

    # Hà Đông
    "biên giang": (20.930000, 105.720000),
    "đồng mai": (20.935000, 105.740000),
    "dương nội": (20.985000, 105.745000),
    "hà cầu": (20.965000, 105.772000),
    "kiến hưng": (20.948000, 105.790000),
    "la khê": (20.978000, 105.762000),
    "mộ lao": (20.982000, 105.782000),
    "phú la": (20.963000, 105.760000),
    "phú lãm": (20.942000, 105.755000),
    "phú lương": (20.938000, 105.765000),
    "phúc la": (20.968000, 105.787000),
    "vạn phúc": (20.977000, 105.775000),
    "văn quán": (20.976000, 105.789000),
    "yên nghĩa": (20.956000, 105.740000),
    "yết kiêu": (20.972000, 105.777000),
    "xa la": (20.962000, 105.792000),
    "hà đông": (20.963272, 105.765180),

    # Hoàng Mai
    "đại kim": (20.975000, 105.822000),
    "định công": (20.988000, 105.833000),
    "giáp bát": (20.986000, 105.845000),
    "hoàng liệt": (20.961000, 105.835000),
    "hoàng văn thụ": (20.990000, 105.856000),
    "lĩnh nam": (20.978000, 105.882000),
    "mai động": (20.994000, 105.863000),
    "tân mai": (20.984000, 105.856000),
    "thịnh liệt": (20.974000, 105.845000),
    "trần phú": (20.986000, 105.885000),
    "tương mai": (20.990000, 105.848000),
    "vĩnh hưng": (20.987000, 105.878000),
    "yên sở": (20.965000, 105.865000),
    "linh đàm": (20.963000, 105.831000),
    "hoàng mai": (20.976077, 105.852492),

    # Tây Hồ
    "bưởi": (21.045000, 105.808000),
    "nhật tân": (21.085000, 105.820000),
    "phú thượng": (21.092000, 105.805000),
    "quảng an": (21.065000, 105.828000),
    "thụy khuê": (21.044000, 105.820000),
    "tứ liên": (21.062000, 105.840000),
    "xuân la": (21.058000, 105.805000),
    "yên phụ": (21.050000, 105.838000),
    "tây hồ": (21.071760, 105.823000),

    # Long Biên
    "bồ đề": (21.033000, 105.875000),
    "cự khối": (20.995000, 105.910000),
    "đức giang": (21.062000, 105.890000),
    "gia thụy": (21.042000, 105.883000),
    "giang biên": (21.065000, 105.915000),
    "ngọc lâm": (21.042000, 105.872000),
    "ngọc thụy": (21.055000, 105.868000),
    "phúc đồng": (21.036000, 105.905000),
    "phúc lợi": (21.040000, 105.935000),
    "sài đồng": (21.032000, 105.912000),
    "thạch bàn": (21.018000, 105.918000),
    "thượng thanh": (21.060000, 105.880000),
    "việt hưng": (21.055000, 105.900000),
    "long biên": (21.036081, 105.894270),

    # Hoàn Kiếm
    "chương dương": (21.028000, 105.862000),
    "cửa đông": (21.033000, 105.845000),
    "cửa nam": (21.026000, 105.842000),
    "đồng xuân": (21.038000, 105.849000),
    "hàng bạc": (21.034000, 105.852000),
    "hàng bài": (21.022000, 105.852000),
    "hàng bồ": (21.034000, 105.848000),
    "hàng bông": (21.030000, 105.846000),
    "hàng buồm": (21.036000, 105.852000),
    "hàng đào": (21.033000, 105.851000),
    "hàng gai": (21.031000, 105.850000),
    "hàng mã": (21.037000, 105.847000),
    "hàng trống": (21.030000, 105.851000),
    "lý thái tổ": (21.030000, 105.856000),
    "phan chu trinh": (21.020000, 105.856000),
    "phúc tân": (21.036000, 105.858000),
    "trần hưng đạo": (21.022000, 105.847000),
    "tràng tiền": (21.024000, 105.858000),
    "hồ hoàn kiếm": (21.028774, 105.852185),
    "hoàn kiếm": (21.030790, 105.852390),

    # Huyện Ngoại Thành Hà Nội
    "gia lâm": (21.020610, 105.943920),
    "đông anh": (21.137250, 105.845870),
    "sóc sơn": (21.282900, 105.849100),
    "thanh trì": (20.941600, 105.852500),
    "thường tín": (20.873200, 105.864700),
    "hoài đức": (21.026700, 105.707200),
    "đan phượng": (21.096300, 105.673800),
    "thạch thất": (21.002800, 105.534200),
    "quốc oai": (20.985600, 105.642000),
    "chương mỹ": (20.892000, 105.688000),
    "sơn tây": (21.135000, 105.505000),
    "mê linh": (21.183300, 105.716700),
    "ba vì": (21.233300, 105.383300),
    "phú xuyên": (20.733300, 105.916700),
    "phúc thọ": (21.100000, 105.583300),
    "thanh oai": (20.866700, 105.783300),
    "ứng hòa": (20.733300, 105.783300),
    "mỹ đức": (20.683300, 105.733300),
    "hà nội": (21.028511, 105.804817),

    # TP. Hồ Chí Minh
    "quận 1": (10.775659, 106.700424),
    "quận 3": (10.784360, 106.684400),
    "quận 4": (10.760000, 106.703000),
    "quận 5": (10.755400, 106.666700),
    "quận 6": (10.748000, 106.635000),
    "quận 7": (10.734030, 106.721780),
    "quận 8": (10.724000, 106.628000),
    "quận 10": (10.774590, 106.667400),
    "quận 11": (10.763000, 106.650000),
    "quận 12": (10.867000, 106.641000),
    "bình thạnh": (10.801800, 106.711100),
    "gò vấp": (10.838300, 106.665300),
    "phú nhuận": (10.799700, 106.680600),
    "tân bình": (10.799200, 106.654000),
    "tân phú": (10.790000, 106.628000),
    "bình tân": (10.765000, 106.605000),
    "thủ đức": (10.849409, 106.753706),
    "bình chánh": (10.687000, 106.593000),
    "hóc môn": (10.887000, 106.593000),
    "củ chi": (11.006000, 106.498000),
    "nhà bè": (10.695000, 106.733000),
    "cần giờ": (10.411000, 106.954000),
    "hồ chí minh": (10.776889, 106.700806),
    "tp hcm": (10.776889, 106.700806),
}

# Pre-sorted keys for longest-first matching
SORTED_GEO_KEYS = sorted(GEO_COORDINATES_MAP.keys(), key=lambda x: len(x), reverse=True)


# ==============================================================================
# 3. GEOCODING ENGINE
# ==============================================================================

_NOMINATIM_GEOLOCATOR = None
_ONLINE_CHECKED = False
_IS_ONLINE = False


def _get_nominatim():
    global _NOMINATIM_GEOLOCATOR, _ONLINE_CHECKED, _IS_ONLINE
    if not _ONLINE_CHECKED:
        _ONLINE_CHECKED = True
        try:
            socket.setdefaulttimeout(1.0)
            socket.gethostbyname("nominatim.openstreetmap.org")
            from geopy.geocoders import Nominatim
            _NOMINATIM_GEOLOCATOR = Nominatim(user_agent="vietnam_rental_geocoder_v2026", timeout=2)
            _IS_ONLINE = True
        except Exception:
            _NOMINATIM_GEOLOCATOR = None
            _IS_ONLINE = False
    return _NOMINATIM_GEOLOCATOR if _IS_ONLINE else None


def resolve_coordinates(
    address_raw: str = "",
    district: Optional[str] = None,
    ward: Optional[str] = None,
    city: str = "hanoi",
    try_online: bool = False
) -> Tuple[Optional[float], Optional[float]]:
    """
    Resolve latitude and longitude for a listing address.
    Matches Ward/Landmark first -> District centroid -> City centroid.
    Optionally queries Geopy Nominatim when available.
    """
    # 1. Check Ward first (most granular offline match)
    if ward:
        w_lower = ward.lower().strip()
        for k in SORTED_GEO_KEYS:
            if k == w_lower or k in w_lower or w_lower in k:
                return GEO_COORDINATES_MAP[k]

    # 2. Check full address_raw text
    if address_raw:
        addr_lower = address_raw.lower().strip()
        for k in SORTED_GEO_KEYS:
            if k in addr_lower:
                return GEO_COORDINATES_MAP[k]

    # 3. Check District centroid
    if district:
        d_lower = district.lower().strip()
        for k in SORTED_GEO_KEYS:
            if k == d_lower or k in d_lower:
                return GEO_COORDINATES_MAP[k]

    # 4. Optional Geopy Online lookup if requested
    if try_online:
        geolocator = _get_nominatim()
        if geolocator and address_raw:
            try:
                loc = geolocator.geocode(f"{address_raw}, Vietnam", timeout=2)
                if loc:
                    return round(loc.latitude, 6), round(loc.longitude, 6)
            except Exception:
                pass

    # 5. Fallback to City centroid
    if "hcm" in city.lower() or "hồ chí minh" in city.lower():
        return GEO_COORDINATES_MAP["hồ chí minh"]
    return GEO_COORDINATES_MAP["hà nội"]


# ==============================================================================
# 4. DATA CLEANING UTILS
# ==============================================================================

def clean_text(text: str) -> str:
    """Unescape HTML entities, strip excessive whitespace and redundant newlines."""
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"[\r\t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    text = re.sub(r"[ ]{2,}", " ", text)
    return text.strip()


# ==============================================================================
# 5. UTILITY FEES EXTRACTION (REGEX ENGINE)
# ==============================================================================

def extract_utilities(text: str) -> Dict[str, Optional[str]]:
    """
    Extract utility pricing specifications from Vietnamese listing text.
    Returns:
        electric_price, water_price, wifi_price, other_utilities_price, parking_fee
    """
    if not text:
        return {
            "electric_price": None,
            "water_price": None,
            "wifi_price": None,
            "other_utilities_price": None,
            "parking_fee": None,
        }

    t = text.lower()

    # 1. Electric Price
    electric_price = None
    if re.search(r"điện\s*(?:nước\s*)?giá\s*dân|giá\s*nhà\s*nước|công\s*tơ\s*riêng\s*giá\s*dân", t):
        electric_price = "Điện giá dân"
    elif re.search(r"miễn\s*phí\s*điện|free\s*điện", t):
        electric_price = "Miễn phí"
    else:
        m_elec = re.search(r"(?:điện|tiền điện|giá điện)[\s\:\-\=]*([\d\.,]+(?:\s*k|\s*nghìn|\s*ngàn|\s*đ|\s*vnd)?\s*[\/\-]\s*(?:số|kwh|kw|tháng|người))", t)
        if not m_elec:
            m_elec = re.search(r"([\d\.,]+(?:\s*k|\s*nghìn)?\s*[\/\-]\s*(?:số|kwh|kw))", t)
        if m_elec:
            electric_price = m_elec.group(1).strip()

    # 2. Water Price
    water_price = None
    if re.search(r"nước\s*giá\s*dân|nước\s*nhà\s*nước|đồng\s*hồ\s*nước\s*riêng\s*giá\s*dân", t):
        water_price = "Nước giá dân"
    elif re.search(r"miễn\s*phí\s*nước|free\s*nước", t):
        water_price = "Miễn phí"
    else:
        m_water = re.search(r"(?:nước|tiền nước|giá nước)[\s\:\-\=]*([\d\.,]+(?:\s*k|\s*nghìn|\s*ngàn|\s*đ|\s*vnd)?\s*[\/\-]\s*(?:người|khối|m3|m³|phòng|tháng))", t)
        if not m_water:
            m_water = re.search(r"([\d\.,]+(?:\s*k|\s*nghìn)?\s*[\/\-]\s*(?:khối|m3|m³))", t)
        if m_water:
            water_price = m_water.group(1).strip()

    # 3. WiFi / Internet Price
    wifi_price = None
    if re.search(r"(?:wifi|mạng|internet)[\s\:\-\=]*(?:free|miễn\s*phí|tặng|bao\s*mạng)", t) or re.search(r"miễn\s*phí\s*(?:wifi|mạng|internet)", t):
        wifi_price = "Miễn phí"
    else:
        m_wifi = re.search(r"(?:wifi|mạng|internet)[\s\:\-\=]*([\d\.,]+(?:\s*k|\s*nghìn|\s*đ|\s*vnd)?\s*[\/\-]\s*(?:phòng|người|tháng))", t)
        if m_wifi:
            wifi_price = m_wifi.group(1).strip()

    # 4. Other Utilities / Service Fee (DVC, vệ sinh, thang máy, rác, máy giặt)
    other_utilities_price = None
    m_dvc = re.search(r"(?:dvc|dịch vụ chung|phí dịch vụ|dịch vụ|thang máy và rác|vệ sinh)[\s\:\-\=]*([\d\.,]+(?:\s*k|\s*nghìn|\s*đ|\s*vnd)?\s*[\/\-]\s*(?:người|phòng|tháng|hộ))", t)
    if m_dvc:
        other_utilities_price = m_dvc.group(1).strip()

    # 5. Parking Fee (Phí gửi xe / Để xe)
    parking_fee = None
    if re.search(r"(?:free|miễn\s*phí)\s*(?:để\s*)?xe|(?:gửi\s*xe|để\s*xe)[\s\:\-\=]*(?:free|miễn\s*phí)", t):
        parking_fee = "Miễn phí"
    else:
        m_park = re.search(r"(?:gửi xe|để xe|phí xe|vé xe)[\s\:\-\=]*([\d\.,]+(?:\s*k|\s*nghìn|\s*đ|\s*vnd)?\s*[\/\-]\s*(?:xe|người|tháng))", t)
        if m_park:
            parking_fee = m_park.group(1).strip()

    return {
        "electric_price": electric_price,
        "water_price": water_price,
        "wifi_price": wifi_price,
        "other_utilities_price": other_utilities_price,
        "parking_fee": parking_fee,
    }


# ==============================================================================
# 6. DISTRICT & WARD GEO-MAPPING
# ==============================================================================

def map_district_and_ward(address_raw: str, text: str = "", city: str = "hanoi") -> Tuple[Optional[str], Optional[str]]:
    """
    Extract canonical district and ward from address text or description.
    Prioritizes address_raw before searching broader text/description.
    """
    addr_lower = (address_raw or "").lower().strip()
    target_text = f"{address_raw} {text}".lower().strip()
    districts = HANOI_DISTRICTS if ("hanoi" in city.lower() or "hà nội" in city.lower()) else HCM_DISTRICTS

    # 1. Match District directly from address_raw first, then target_text
    matched_district = None
    for search_str in [addr_lower, target_text]:
        if matched_district or not search_str:
            break
        for d in districts:
            d_lower = d.lower()
            patterns = [
                rf"\bquận\s+{re.escape(d_lower)}\b",
                rf"\bhuyện\s+{re.escape(d_lower)}\b",
                rf"\btp\s+{re.escape(d_lower)}\b",
                rf"\bthị\s*xã\s+{re.escape(d_lower)}\b",
                rf"\b{re.escape(d_lower)}\b",
            ]
            if any(re.search(p, search_str) for p in patterns):
                matched_district = d
                break

    # 2. Extract Ward directly from address_raw first, then target_text
    matched_ward = None
    for search_str in [addr_lower, target_text]:
        if matched_ward or not search_str:
            break
        m_ward = re.search(r"(?:phường|p\.|xã|thị trấn)\s*([a-zà-ỹ0-9\s]{2,20}?)(?:,|\.|\-|quận|huyện|tp|$)", search_str)
        if m_ward:
            w_candidate = m_ward.group(1).strip().title()
            if len(w_candidate) >= 2 and not any(skip in w_candidate.lower() for skip in ["hà nội", "hồ chí minh", "quận", "huyện"]):
                matched_ward = w_candidate

    # 3. Infer Ward & District from Ward lookup map if missing (Hanoi only)
    if "hanoi" in city.lower() or "hà nội" in city.lower():
        for search_str in [addr_lower, target_text]:
            if matched_district and matched_ward:
                break
            if not search_str:
                continue
            for w_key, d_val in HANOI_WARD_DISTRICT_MAP.items():
                if re.search(rf"\b{re.escape(w_key)}\b", search_str):
                    if not matched_district:
                        matched_district = d_val
                    if not matched_ward:
                        matched_ward = w_key.title()
                    break

    return matched_district, matched_ward


# ==============================================================================
# 7. HOUSING CLASSIFICATION
# ==============================================================================

def classify_house_type(title: str, description: str = "", room_type_raw: str = "") -> str:
    """
    Classifies the listing into a canonical housing category.
    """
    t = f"{title} {description} {room_type_raw}".lower()

    if re.search(r"\b(?:2pn|2n1k|2 ngủ|2 phòng ngủ|2n)\b", t):
        return "2 Phòng Ngủ (2PN/2N1K)"
    if re.search(r"\b(?:1pn|1n1k|1 ngủ|1 phòng ngủ|1n|1 ngủ 1 khách)\b", t):
        return "1 Phòng Ngủ (1PN/1N1K)"
    if re.search(r"\b(?:studio|khép kín|khep kin|self-contained)\b", t):
        return "Studio khép kín"
    if re.search(r"\b(?:gác xép|gác lửng|duplex|gac xep|gac lung)\b", t):
        return "Gác xép / Duplex"
    if re.search(r"\b(?:ccmn|chung cư mini|căn hộ mini|can ho mini)\b", t):
        return "Chung cư mini (CCMN)"
    if re.search(r"\b(?:nguyên căn|nhà nguyên căn|nhà riêng)\b", t):
        return "Nhà nguyên căn"
    if re.search(r"\b(?:wc chung|vệ sinh chung|ve sinh chung|ko khép kín|không khép kín)\b", t):
        return "Phòng trọ WC chung"

    return "Phòng trọ khép kín"


# ==============================================================================
# 8. BOOLEAN AMENITY FLAGS
# ==============================================================================

def extract_amenities(text: str) -> Dict[str, bool]:
    """
    Extract boolean amenity indicators from title, description, or features list.
    """
    if not text:
        return {
            "air_conditioner": False,
            "water_heater": False,
            "refrigerator": False,
            "washing_machine": False,
            "elevator": False,
            "balcony_window": False,
            "fire_safety": False,
            "pet_allowed": False,
        }

    t = text.lower()

    # Air Conditioner
    has_ac = bool(re.search(r"điều\s*hòa|máy\s*lạnh|dieu\s*hoa|may\s*lanh|\bac\b", t))

    # Water Heater
    has_heater = bool(re.search(r"nóng\s*lạnh|bình\s*nóng\s*lạnh|nong\s*lanh|nóng\s*lạnh\s*nl", t))

    # Refrigerator
    has_fridge = bool(re.search(r"tủ\s*lạnh|tu\s*lanh|fridge", t))

    # Washing Machine
    has_washer = bool(re.search(r"máy\s*giặt|may\s*giat|máy\s*sấy", t))

    # Elevator
    has_elevator = bool(re.search(r"thang\s*máy|thang\s*may|\blift\b|\belevator\b", t))

    # Balcony / Window / Airy
    has_balcony = bool(re.search(r"ban\s*công|cửa\s*sổ|ban\s*cong|cua\s*so|thoáng\s*sáng|thoáng\s*mát|view\s*đẹp", t))

    # Fire Safety (PCCC, bình chữa cháy, thang thoát hiểm, báo khói)
    has_fire_safety = bool(re.search(r"pccc|phòng\s*cháy|chữa\s*cháy|thang\s*thoát\s*hiểm|báo\s*cháy|bình\s*cứu\s*hỏa|báo\s*khói", t))

    # Pet Allowed (requiring positive affirmation and strictly ensuring no negation/restriction)
    has_pet = False
    pos_pet = bool(re.search(r"\b(?:cho|được|cho phép|thoải mái|ok|chấp nhận)\s*(?:cho\s*)?(?:nuôi\s*)?(?:pet|thú\s*cưng|chó\s*mèo|chó|mèo|vật\s*nuôi)\b|\bpet\s*friendly\b|\bok\s*pet\b|\bnuôi\s*(?:pet|thú\s*cưng|chó\s*mèo)\s*(?:thoải mái|ok|được)\b", t))
    neg_pet = bool(re.search(r"\b(?:cấm|không|ko|k|miễn|chặn|hạn chế)\b\s*(?:cho|nhận|được|đc|phép)?\s*[^.\n;]*?\b(?:pet|thú\s*cưng|chó\s*mèo|chó|mèo|vật\s*nuôi)\b|\b(?:không|ko|k|cấm)\s*nuôi\b", t))
    if pos_pet and not neg_pet:
        has_pet = True

    return {
        "air_conditioner": has_ac,
        "water_heater": has_heater,
        "refrigerator": has_fridge,
        "washing_machine": has_washer,
        "elevator": has_elevator,
        "balcony_window": has_balcony,
        "fire_safety": has_fire_safety,
        "pet_allowed": has_pet,
    }


# ==============================================================================
# 9. MASTER ENRICHMENT PIPELINE
# ==============================================================================

def enrich_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enrich a raw parsed listing record with cleaned text, utilities, location mapping,
    geocoded latitude/longitude, housing classification, and boolean amenity flags.
    """
    title = clean_text(record.get("title", ""))
    description = clean_text(record.get("description", ""))
    address_raw = clean_text(record.get("address_raw", ""))
    # 0. City resolution
    addr_lower = address_raw.lower()
    if any(k in addr_lower for k in ["hồ chí minh", "tp hcm", "tp.hcm", "tphcm", "sài gòn"]):
        city = "hcm"
        record["city"] = "hồ chí minh"
    elif any(k in addr_lower for k in ["hà nội", "ha noi", "hn"]):
        city = "hanoi"
        record["city"] = "hà nội"
    else:
        city = record.get("city", "hà nội")

    # 1. Cleaned core text
    record["title"] = title
    record["description"] = description
    record["address_raw"] = address_raw
    combined_text = f"{title}\n{address_raw}\n{description}"

    # 2. Location Enrichment
    district, ward = map_district_and_ward(address_raw, combined_text, city=city)
    record["district"] = district
    record["ward"] = ward

    # 3. Geocoding: Latitude & Longitude
    lat = record.get("latitude")
    lon = record.get("longitude")
    if lat is None or lon is None or lat == "" or lon == "":
        lat, lon = resolve_coordinates(address_raw, district=district, ward=ward, city=city)
    record["latitude"] = lat
    record["longitude"] = lon

    # 4. House Type Classification
    record["house_type"] = classify_house_type(title, description, record.get("room_type", ""))

    # 5. Utility Fees
    utilities = extract_utilities(combined_text)
    record.update(utilities)

    # 6. Boolean Amenity Flags
    amenities = extract_amenities(combined_text)
    record.update(amenities)

    return record
