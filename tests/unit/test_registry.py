from backend.app.collectors.registry import load_registry


def test_all_requested_datasets_are_registered():
    registry = load_registry()
    assert len(registry) == 15
    assert "lh_complexes" in registry
    assert "ngii_dem" in registry
    assert "elevator_corrective_actions" in registry

def test_every_dataset_has_input_contract():
    for spec in load_registry().values():
        assert spec.name and spec.mode in {"file", "api", "file_or_api"}
        assert spec.formats

