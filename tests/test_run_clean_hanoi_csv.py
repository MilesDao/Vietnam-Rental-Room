"""write_back(): filling coordinates into the original CSVs without disturbing them."""
import pandas as pd
import pytest

from src.clean.run_clean_hanoi_csv import write_back

ORIGINAL = (
    "listing_id,price_vnd,latitude,longitude\n"
    "a,3000000.0,,\n"                      # never had a coordinate
    "b,4000000.0,10.7720300,106.6983200\n"  # placeholder: central Ho Chi Minh City
    "c,,21.0300000,105.8000000\n"           # the platform's own coordinate
)


def cleaned_frame(name="x.csv"):
    return pd.DataFrame({
        "source_file": [name] * 3,
        "latitude": [21.0123456, 20.9876543, 21.03],
        "longitude": [105.8, 105.7, 105.8],
        "geo_confidence": ["street", "ward", "listing"],
    })


def test_write_back_fills_coordinates_and_keeps_other_columns(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text(ORIGINAL, encoding="utf-8")

    written = write_back(cleaned_frame(), tmp_path, ["x.csv"])

    assert written == [path]
    out = pd.read_csv(path, dtype=str, keep_default_na=False)
    assert out["latitude"].tolist() == ["21.0123456", "20.9876543", "21.0300000"]
    assert out["geo_confidence"].tolist() == ["street", "ward", "listing"]
    # untouched: the placeholder row was replaced, and other columns keep their text
    assert out["price_vnd"].tolist() == ["3000000.0", "4000000.0", ""]
    assert out["listing_id"].tolist() == ["a", "b", "c"]
    assert (tmp_path / "x.csv.bak").read_text(encoding="utf-8") == ORIGINAL


def test_write_back_keeps_the_first_backup_and_preserves_a_bom(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text(ORIGINAL, encoding="utf-8-sig")
    write_back(cleaned_frame(), tmp_path, ["x.csv"])
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")

    # a second run must not overwrite the pristine backup with the filled file
    frame = cleaned_frame()
    frame["latitude"] = [20.0, 20.0, 20.0]
    write_back(frame, tmp_path, ["x.csv"])
    assert (tmp_path / "x.csv.bak").read_text(encoding="utf-8-sig") == ORIGINAL


def test_write_back_refuses_a_row_count_mismatch(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text(ORIGINAL, encoding="utf-8")
    with pytest.raises(ValueError, match="rows on disk"):
        write_back(cleaned_frame().head(2), tmp_path, ["x.csv"])
    assert path.read_text(encoding="utf-8") == ORIGINAL
