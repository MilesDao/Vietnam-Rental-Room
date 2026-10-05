import pandas as pd

from src.recsys.regeocode_fallback import fallback_mask, haversine, nearest, tier
from src.recsys.ref_points import UNIVERSITIES


def test_fallback_mask_flags_only_shared_multi_ward_point():
    wards = ["Phường A", "Xã B", "Xã C", "Phường D", "Xã E"]
    df = pd.DataFrame({
        "latitude": [1.0] * 5 + [2.0] * 3, "longitude": [1.0] * 5 + [2.0] * 3,
        "address": [f"1 Đường X, {w}, Hà Nội" for w in wards] + ["2 Đường Y, Phường Z, Hà Nội"] * 3,
    })
    bad, _ = fallback_mask(df)
    assert bad[:5].all() and not bad[5:].any()


def test_nearest_and_tier():
    utc = next(u for u in UNIVERSITIES if "UTC" in u["name"])
    i, km = nearest(utc["lat"], utc["lng"], UNIVERSITIES, ("lat", "lng"))
    assert UNIVERSITIES[i] is utc and km < 0.01
    assert haversine(21.0, 105.8, 21.0, 105.8) == 0
    assert tier(0.4, "far").startswith("< 500m") and tier(5, "far") == "far"
