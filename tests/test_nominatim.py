"""NominatimGeocoder against a fake session: caching, pacing, blocking, the fallback cascade."""
import json

import pytest
import requests

from src.geo.address import build_candidates
from src.geo.nominatim import MIN_INTERVAL_S, NominatimBlocked, NominatimGeocoder

DONG_DA = {
    "category": "boundary", "type": "historic", "name": "Quận Đống Đa", "lat": "21.01", "lon": "105.82",
    "boundingbox": ["21.00", "21.03", "105.80", "105.84"], "display_name": "Quận Đống Đa, Hà Nội",
}


class FakeResponse:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
        self.text = json.dumps(payload, ensure_ascii=False)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


class FakeSession:
    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((params, headers))
        answer = self.answers.get(params["q"], [])
        return answer if isinstance(answer, FakeResponse) else FakeResponse(200, answer)


class FakeClock:
    def __init__(self):
        self.now = 1000.0
        self.slept = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


def make(tmp_path, answers, **kwargs):
    session = FakeSession(answers)
    clock = FakeClock()
    geocoder = NominatimGeocoder(tmp_path / "cache.sqlite", "test-agent/1.0", session=session,
                                 sleep=clock.sleep, clock=clock, **kwargs)
    return geocoder, session, clock


def test_responses_are_cached_across_instances(tmp_path):
    geocoder, session, _ = make(tmp_path, {"Quận Đống Đa, Hà Nội": [DONG_DA]})
    assert geocoder.search("Quận Đống Đa, Hà Nội")[0]["name"] == "Quận Đống Đa"
    geocoder.close()
    again, session2, _ = make(tmp_path, {})
    assert again.search("Quận Đống Đa, Hà Nội")[0]["name"] == "Quận Đống Đa"
    assert session2.calls == [] and again.n_cache_hits == 1


def test_requests_are_paced_and_identify_themselves(tmp_path):
    geocoder, session, clock = make(tmp_path, {})
    geocoder.search("a, Hà Nội")
    geocoder.search("b, Hà Nội")
    assert clock.slept == [pytest.approx(MIN_INTERVAL_S)]
    assert all(headers["User-Agent"] == "test-agent/1.0" for _, headers in session.calls)


def test_429_stops_instead_of_retrying_and_is_not_cached(tmp_path):
    geocoder, session, _ = make(tmp_path, {"a, Hà Nội": FakeResponse(429, {"error": "rate limited"})})
    with pytest.raises(NominatimBlocked):
        geocoder.search("a, Hà Nội")
    assert len(session.calls) == 1
    offline, _, _ = make(tmp_path, {}, offline=True)
    assert offline.search("a, Hà Nội") is None


def test_cascade_falls_back_past_wrong_alley_and_non_road(tmp_path):
    answers = {
        "Quận Đống Đa, Hà Nội": [DONG_DA],
        "Ngõ 580 Trường Chinh, Hà Nội": [
            {"category": "highway", "name": "Ngõ 120 Đường Trường Chinh", "lat": "21.0014", "lon": "105.8354"},
        ],
        "Trường Chinh, Hà Nội": [
            {"category": "amenity", "name": "Trường THPT Nhân Chính", "lat": "21.003", "lon": "105.806"},
            {"category": "highway", "name": "Đường Trường Chinh", "lat": "20.9999", "lon": "105.8324"},
        ],
    }
    geocoder, session, _ = make(tmp_path, answers)
    result, complete = geocoder.geocode(build_candidates("Ngõ 580 Trường Chinh", None, "Quận Đống Đa"))
    assert complete
    assert (result.level, result.lat, result.lon) == ("street", 20.9999, 105.8324)
    street_params = next(p for p, _ in session.calls if p["q"] == "Trường Chinh, Hà Nội")
    assert street_params["viewbox"] == "105.795000,21.035000,105.845000,20.995000"
    assert street_params["bounded"] == "1"


def test_nothing_matches_gives_complete_none_and_budget_gives_incomplete(tmp_path):
    geocoder, _, _ = make(tmp_path, {"Quận Đống Đa, Hà Nội": [DONG_DA]})
    assert geocoder.geocode(build_candidates("Khu tập thể", None, "Quận Đống Đa"))[0].level == "district"

    empty, _, _ = make(tmp_path, {})
    assert empty.geocode(build_candidates("Khu tập thể", None, None)) == (None, True)

    capped, session, _ = make(tmp_path, {}, max_requests=0)
    assert capped.geocode(build_candidates("Nguyễn Trãi", None, "Quận Thanh Xuân")) == (None, False)
    assert session.calls == []
