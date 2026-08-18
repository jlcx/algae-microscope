from server.neighborhood.witnesses import WitnessWeights, witness_set_ops

LSJBOT = [["ceb", "war", "sv", "vi"]]


def test_effective_count_caps_family():
    w = WitnessWeights(families=LSJBOT, family_cap=1)
    assert w.effective_count(["ceb", "war", "sv", "vi", "en"]) == 2.0
    assert w.effective_count(["ceb"]) == 1.0
    assert w.effective_count(["en", "de", "fr"]) == 3.0
    assert w.effective_count([]) == 0.0


def test_effective_count_multiple_families():
    w = WitnessWeights(families=[["a", "b"], ["c", "d"]], family_cap=1)
    assert w.effective_count(["a", "b", "c", "d", "e"]) == 3.0


def test_family_cap_above_one():
    w = WitnessWeights(families=LSJBOT, family_cap=2)
    assert w.effective_count(["ceb", "war", "sv"]) == 2.0
    assert w.effective_count(["ceb"]) == 1.0


def test_per_language_weights_generalization():
    w = WitnessWeights(families=[], weights={"ceb": 0.1, "en": 1.0})
    assert w.effective_count(["ceb", "en", "de"]) == 2.1


def test_weights_inside_family():
    # weighted family sum below the cap passes through un-capped
    w = WitnessWeights(families=LSJBOT, family_cap=1,
                       weights={"ceb": 0.2, "war": 0.3})
    assert w.effective_count(["ceb", "war"]) == 0.5


def test_witness_set_ops():
    ops = witness_set_ops(["en", "de", "fr"], ["de", "pl"])
    assert ops == {"shared": ["de"], "only_a": ["en", "fr"], "only_b": ["pl"]}
