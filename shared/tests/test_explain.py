from labcore.explain import contributions, render


def test_ablation_attributes_linear_model_exactly():
    c = contributions(
        lambda v: 2 * v[0] - v[1], [3.0, 1.0, 5.0], [0.0, 0.0, 0.0], ["a", "b", "c"], method="ablation"
    )
    got = {r["feature"]: r["contribution"] for r in c["features"]}
    assert got == {"a": 6.0, "b": -1.0, "c": 0.0} and c["method"] == "ablation"
    assert render(c, 2) == ["a +6.000", "b -1.000"]
