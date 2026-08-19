from scripts.backfill_complex_coordinates import _address_key, _in_korea


def test_address_key_normalizes_same_road_address():
    assert _address_key("서울특별시 서대문구 독립문로8길 54 (천연동)") == _address_key(
        "서울 서대문구 독립문로8길 54 LH아파트"
    )


def test_address_key_keeps_different_building_numbers_separate():
    assert _address_key("서울 강남구 테스트로 10") != _address_key("서울 강남구 테스트로 11")


def test_coordinate_validation_rejects_outside_korea():
    assert _in_korea(37.56, 126.97)
    assert not _in_korea(40.0, 126.97)
