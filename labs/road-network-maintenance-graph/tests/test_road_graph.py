"""Graph workers and the budget harness."""

import itertools

import networkx as nx
import pytest

from roadgraph import graph_ops as ops
from roadgraph.harness import BudgetExceeded, BudgetGuard, select_plan


@pytest.fixture(scope="module")
def world():
    g = ops.build_graph()
    dem = ops.demand()
    base = ops.trip_minutes(g, dem)
    impacts = {d["id"]: ops.closure_impact(g, d["id"], dem, base) for _, _, d in g.edges(data=True)}
    return g, dem, base, impacts


@pytest.fixture(scope="module")
def ranked(world):
    g, dem, *_ = world
    return ops.priority(g, ops.features(g, dem))


def test_osm_fixture_builds_connected_graph_offline(world):
    g, *_ = world
    assert g.number_of_nodes() == 22 and nx.is_connected(g)
    assert g.nodes["E2"]["amenity"] == "hospital"
    assert g.edges[ops.edge_by_id(g, "w-W13-E0")]["bridge"] is True


def test_edge_lengths_come_from_coordinates(world):
    g, *_ = world
    assert 150 < g.edges["W00", "W01"]["length_m"] < 200
    assert 190 < g.edges["W00", "W10"]["length_m"] < 210


def test_shortest_path_to_hospital_uses_a_bridge(world):
    g, *_ = world
    path = nx.shortest_path(g, "W30", "E2", weight="minutes")
    edges = {g.edges[a, b]["id"] for a, b in itertools.pairwise(path)}
    assert edges & {"w-W13-E0", "w-W33-E3"}


def test_cul_de_sac_is_a_graph_bridge_river_bridges_are_not(world):
    g, *_ = world
    cut = {g.edges[e]["id"] for e in nx.bridges(g)}
    assert "w-C1-C2" in cut and "w-W13-E0" not in cut


def test_closing_cul_de_sac_strands_hospital_trips(world):
    *_, impacts = world
    imp = impacts["w-C1-C2"]
    assert imp["disconnected"] and imp["hospital_access_lost"] and imp["stranded_trips"] > 0


def test_closing_north_bridge_costs_detour_but_keeps_access(world):
    *_, impacts = world
    imp = impacts["w-W13-E0"]
    assert not imp["disconnected"] and imp["extra_vehicle_minutes"] > 1000


def test_priority_respects_connectivity_not_just_potholes(ranked):
    ids = [r["segment_id"] for r in ranked]
    worst_potholes = max(ranked, key=lambda r: r["potholes"])["segment_id"]
    assert worst_potholes == "w-C1-C2"
    assert ids.index("w-W13-E0") < ids.index("w-C1-C2")
    assert ids[0] != worst_potholes


def test_budget_guard_raises_on_overspend():
    g = BudgetGuard(100)
    g.commit({"segment_id": "a", "cost_usd": 60})
    with pytest.raises(BudgetExceeded):
        g.commit({"segment_id": "b", "cost_usd": 50})


def test_worker_call_budget():
    g = BudgetGuard(1, max_worker_calls=2)
    g.worker("a")
    g.worker("b")
    with pytest.raises(BudgetExceeded):
        g.worker("c")


def test_plan_never_exceeds_budget_and_records_skips(world, ranked):
    *_, impacts = world
    for budget in (30_000, 120_000, 400_000):
        plan = select_plan(ranked, impacts, BudgetGuard(budget))
        assert plan["total_cost_usd"] <= budget
        assert plan["skipped"] or plan["total_cost_usd"] <= budget


def test_bridges_are_staged_in_different_weeks(world, ranked):
    *_, impacts = world
    plan = select_plan(ranked, impacts, BudgetGuard(5_000_000), min_score=0.0)
    weeks = [i["week"] for i in plan["items"] if i["bridge"]]
    assert len(weeks) == 2 and len(set(weeks)) == 2


def test_critical_closures_get_lane_open_method(world, ranked):
    *_, impacts = world
    plan = select_plan(ranked, impacts, BudgetGuard(5_000_000), min_score=0.0)
    cul = next(i for i in plan["items"] if i["segment_id"] == "w-C1-C2")
    assert cul["method"].startswith("night work")


def test_graph_features_include_centrality_and_cut_edges(world):
    g, dem, *_ = world
    f = ops.features(g, dem)
    assert f["w-C1-C2"]["cut_edge"] and f["w-C1-C2"]["trips_served_if_cut"] > 0
    assert f["w-W13-E0"]["critical_usage"] > f["w-C1-C2"]["critical_usage"]
    assert max(f, key=lambda s: f[s]["betweenness"]) in {
        "w-W11-W12",
        "w-W12-W13",
        "w-W13-E0",
        "w-E0-E1",
        "w-W10-W11",
    }


def test_maintenance_records_and_incidents_raise_need(world):
    g, *_ = world
    d = dict(g.edges[ops.edge_by_id(g, "w-W13-E0")])
    assert d["incidents"] == 1 and d["failed_patches"] == 3
    assert ops.need(d) > ops.need({**d, "incidents": 0, "failed_patches": 0, "last_resurfaced": 2026})


def test_closure_impact_lists_affected_segments_and_reroutes(world):
    *_, impacts = world
    imp = impacts["w-W13-E0"]
    assert "w-W33-E3" in imp["affected_segments"]
    assert any(r["dest"] == "E2" and "E3" in r["new_path"] for r in imp["critical_reroutes"])


def test_road_health_report(world):
    g, dem, *_ = world
    h = ops.road_health(g, ops.features(g, dem))
    assert h["segments"] == g.number_of_edges() and sum(h["condition_bands"].values()) == h["segments"]
    assert h["river_crossings"] == ["w-W13-E0", "w-W33-E3"] and "w-C1-C2" in h["cut_edges"]
