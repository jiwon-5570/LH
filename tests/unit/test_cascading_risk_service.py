from backend.app.services.cascading_risk_service import build_risk_graph, evaluate_nodes


def base_features():
    return {
        "dynamic": {"rain_1h_mm": 42, "rain_1h_empirical_index": 95},
        "terrain": {"dem_coverage_ratio_300m": 1.0, "lowland_index_300m": 24},
        "flood": {"historical_flood_count_300m": 2, "historical_flood_area_ratio_300m": .12,
                  "expected_flood_overlap": None, "distance_to_nearest_pump_station_m": 2200},
        "historical": {"hit_years_300m": [2022, 2024]},
        "facility": {"elevator_count": 3}, "facility_vulnerability": 72,
    }


def test_single_environmental_node_does_not_invent_compound_path():
    features = {"dynamic":{"rain_1h_mm":40,"rain_1h_empirical_index":95}}
    result = build_risk_graph(features)
    assert result["cascade_level"] == 1
    assert result["paths"] == []


def test_two_source_rain_lowland_activates_compound_and_flood_path():
    result = build_risk_graph(base_features())
    nodes = {x["node_id"]: x for x in result["nodes"]}
    assert nodes["COMPOUND_HYDROLOGIC_STRESS"]["status"] == "ACTIVE"
    assert nodes["FLOOD_EXPOSURE"]["status"] == "ACTIVE"
    assert result["cascade_level"] >= 4


def test_rain_and_sewer_compound_path_uses_relative_reference():
    features = base_features()
    features["dynamic"].update({"sewer_level_current": 1.1, "sewer_level_p95": 1.0})
    nodes = evaluate_nodes(features)
    assert nodes["SEWER_STRESS"]["status"] == "ACTIVE"
    assert nodes["COMPOUND_HYDROLOGIC_STRESS"]["status"] == "ACTIVE"


def test_historical_and_expected_evidence_are_preserved():
    features = base_features()
    features["flood"].update({"expected_flood_overlap": True, "expected_flood_area_ratio_300m": .2})
    nodes = evaluate_nodes(features)
    assert nodes["HISTORICAL_FLOOD_EXPOSURE"]["evidence"][0]["value"] == 2
    assert nodes["EXPECTED_FLOOD_EXPOSURE"]["status"] == "ACTIVE"


def test_drainage_distance_is_context_not_failure_probability():
    nodes = evaluate_nodes(base_features())
    assert nodes["DRAINAGE_LIMITATION"]["status"] == "WATCH"
    assert all("probability" not in e for e in nodes["DRAINAGE_LIMITATION"]["evidence"])


def test_elevator_impact_requires_actual_elevator_link():
    features = base_features(); features["facility"] = {"elevator_count": 0}
    assert evaluate_nodes(features)["ELEVATOR_SERVICE_IMPACT"]["status"] == "INACTIVE"
    features["facility"] = {"elevator_count": 2}
    assert evaluate_nodes(features)["ELEVATOR_SERVICE_IMPACT"]["status"] == "REVIEW_REQUIRED"


def test_internal_equipment_is_review_required_and_no_failures_are_invented():
    nodes = evaluate_nodes(base_features())
    assert nodes["UNDERGROUND_EQUIPMENT_REVIEW"]["status"] == "REVIEW_REQUIRED"
    forbidden = {"ELECTRICAL_FAILURE", "ELEVATOR_FAILURE"}
    assert forbidden.isdisjoint(nodes)


def test_missing_features_are_explicitly_insufficient():
    nodes = evaluate_nodes({})
    assert nodes["HEAVY_RAIN"]["status"] == "INSUFFICIENT"
    assert nodes["LOWLAND_EXPOSURE"]["status"] == "INSUFFICIENT"
    assert nodes["EXPECTED_FLOOD_EXPOSURE"]["status"] == "INSUFFICIENT"


def test_path_order_and_level_follow_deepest_valid_path():
    result = build_risk_graph(base_features())
    elevator = next(x for x in result["paths"] if x["path_name"] == "승강기 영향 점검")
    assert elevator["nodes"] == ["HEAVY_RAIN","COMPOUND_HYDROLOGIC_STRESS","FLOOD_EXPOSURE","ELEVATOR_SERVICE_IMPACT"]
    assert result["cascade_level"] >= 4
