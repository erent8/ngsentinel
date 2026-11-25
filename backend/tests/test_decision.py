import pytest

from ngsentinel.decision import RulesError, evaluate, evaluate_rule, load_rules, parse_rules

HIGH = {"id": "q", "metric": "after.q30_pct", "label": "Q30", "direction": "higher", "pass": 80, "review": 70, "unit": "%"}
LOW = {"id": "a", "metric": "after.adapter_max_pct", "label": "Adapter", "direction": "lower", "pass": 1, "review": 5, "unit": "%"}


@pytest.mark.parametrize("v,expected", [(85, "PASS"), (80, "PASS"), (75, "REVIEW"), (70, "REVIEW"), (69.9, "FAIL")])
def test_higher_is_better(v, expected):
    assert evaluate_rule(HIGH, {"after": {"q30_pct": v}}).status == expected


@pytest.mark.parametrize("v,expected", [(0.2, "PASS"), (1, "PASS"), (3, "REVIEW"), (5.01, "FAIL")])
def test_lower_is_better(v, expected):
    assert evaluate_rule(LOW, {"after": {"adapter_max_pct": v}}).status == expected


def test_missing_metric_is_not_evaluated():
    r = evaluate_rule(HIGH, {"after": {}})
    assert r.status == "N/A" and r.value is None


def test_overall_is_worst_status_and_explained():
    rules = {"rules": [HIGH, LOW]}
    d = evaluate(rules, {"after": {"q30_pct": 90, "adapter_max_pct": 3}})
    assert d["overall"] == "REVIEW"
    assert d["drivers"] == ["a"]
    assert "Adapter" in d["summary"]
    assert "REVIEW range" in d["results"][1]["explanation"]
    assert evaluate(rules, {"after": {"q30_pct": 50, "adapter_max_pct": 3}})["overall"] == "FAIL"
    assert evaluate(rules, {"after": {"q30_pct": 90, "adapter_max_pct": 0}})["overall"] == "PASS"


def test_default_rules_file_is_valid(rules_file):
    data = load_rules(rules_file)
    assert len(data["rules"]) >= 6


@pytest.mark.parametrize("text,msg", [
    ("rules: []", "non-empty"),
    ("rules:\n  - id: x\n    metric: after.a\n    label: X\n    direction: up\n    pass: 1\n    review: 2", "direction"),
    ("rules:\n  - id: x\n    metric: after.a\n    label: X\n    direction: higher\n    pass: 1\n    review: 2", "pass must be >="),
    ("rules:\n  - id: x\n    metric: other.a\n    label: X\n    direction: lower\n    pass: 1\n    review: 2", "metric must start"),
    ("rules:\n  - id: x\n    label: X", "missing"),
    ("rules: [", "invalid YAML"),
])
def test_invalid_rules(text, msg):
    with pytest.raises(RulesError, match=msg):
        parse_rules(text)
