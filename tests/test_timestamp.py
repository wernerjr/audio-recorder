from audio_recorder.utils.timestamp import format_ts, ts_to_seconds


def test_format_ts_zero():
    assert format_ts(0) == "00:00:00.000"


def test_format_ts_one_hour():
    assert format_ts(3661.5) == "01:01:01.500"


def test_format_ts_ms_precision():
    assert format_ts(0.001) == "00:00:00.001"
    assert format_ts(0.999) == "00:00:00.999"


def test_ts_to_seconds_roundtrip():
    for val in [0.0, 1.5, 3661.5, 7199.999]:
        assert abs(ts_to_seconds(format_ts(val)) - val) < 0.001


def test_ts_to_seconds_basic():
    assert ts_to_seconds("01:01:01.500") == pytest.approx(3661.5)


import pytest  # noqa: E402 — imported after usage above for clarity
