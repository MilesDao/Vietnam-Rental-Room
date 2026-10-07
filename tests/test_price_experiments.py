import numpy as np
import pandas as pd

from src.recsys import price_experiments as pe


def test_text_features_never_contain_the_price():
    t = pd.DataFrame({"title": ["Phòng trọ Cầu Giấy - 3,5 triệu/tháng"], "description": ["giá 3tr5, điện 4k"]})
    assert not any(ch.isdigit() for ch in pe.text_of(t).iloc[0])   # 52% of titles state the rent


def test_noise_flags_read_the_title_only_and_skip_floor_numbers():
    t = pd.DataFrame({"title": ["Studio Đình Thôn - 4,5-6 triệu/tháng", "Pass phòng 5tr2 Trương Định",
                                "CCMN tầng 4 - 4,1 triệu/tháng", "Phòng 25m2 - 3 triệu/tháng"],
                      "description": ["", "", "", "điện 3.5k-4k"], "house_type": "Phòng trọ", "area_m2": [30, 20, 25, 25]})
    f = pe.noise_flags(t)
    assert f["price range"].tolist() == [True, False, False, False]   # floor number and utility range are not price ranges
    assert f["sublet"].tolist() == [False, True, False, False]


def test_out_of_fold_predictions_are_clipped_to_the_training_range():
    rng = np.random.default_rng(0)
    n = 200
    t = pd.DataFrame({"house_type": "Phòng trọ", "district": rng.choice(["A", "B"], n), "platform": "P",
                      "area_m2": rng.uniform(15, 40, n), "title": "phòng", "description": "",
                      **{a: rng.integers(0, 2, n) for a in pe.pm.AMENITIES}, **{c: rng.uniform(0, 10, n) for c in pe.pm.DIST}})
    t.loc[0, "area_m2"] = 5_000                       # one absurd area: a linear model would extrapolate far
    y = np.log(t.area_m2.clip(upper=40).values * 120_000)
    folds = list(pe.pm._splits(n, None))
    factory, uses_text, kind = pe.models()["Ridge regression"]
    p = pe.oof_predict(factory, uses_text, kind, t, y, folds, pe.text_of(t))
    assert p.max() <= y.max() + 1e-9 and np.isfinite(p).all()
