from scripts.backfill_complex_coordinates import _address_key, _cluster_coordinate, _in_korea


def test_address_key_normalizes_same_road_address():
    assert _address_key("서울특별시 서대문구 독립문로8길 54 (천연동)") == _address_key(
        "서울 서대문구 독립문로8길 54 LH아파트"
    )


def test_address_key_keeps_districts_and_building_numbers_separate():
    assert _address_key("서울 강남구 테헤란로 10") != _address_key("서울 강남구 테헤란로 11")
    assert _address_key("서울 강남구 중앙로 10") != _address_key("서울 강동구 중앙로 10")


def test_coordinate_validation_rejects_outside_korea():
    assert _in_korea(37.56, 126.97)
    assert not _in_korea(40.0, 126.97)


def test_cluster_coordinate_accepts_tight_building_group():
    result = _cluster_coordinate([
        {"latitude": 37.5000, "longitude": 127.0000},
        {"latitude": 37.5005, "longitude": 127.0005},
    ])
    assert result is not None
    assert result[2] < 100


def test_cluster_coordinate_rejects_wide_group():
    assert _cluster_coordinate([
        {"latitude": 37.50, "longitude": 127.00},
        {"latitude": 37.60, "longitude": 127.10},
    ]) is None
