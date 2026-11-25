"""Configurable, explainable QC decision engine (PASS / REVIEW / FAIL)."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

import yaml

STATUSES = ("PASS", "REVIEW", "FAIL")
REQUIRED = ("id", "metric", "label", "direction", "pass", "review")


class RulesError(ValueError):
    pass


def load_rules(path: str | Path) -> dict:
    return parse_rules(Path(path).read_text(encoding="utf-8"))


def parse_rules(text: str) -> dict:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise RulesError(f"invalid YAML: {e}") from e
    if not isinstance(data, dict) or not isinstance(data.get("rules"), list) or not data["rules"]:
        raise RulesError("the file must contain a non-empty 'rules' list")
    seen = set()
    for i, r in enumerate(data["rules"]):
        if not isinstance(r, dict):
            raise RulesError(f"rule {i + 1} must be a mapping")
        missing = [k for k in REQUIRED if k not in r]
        if missing:
            raise RulesError(f"rule {r.get('id', i + 1)}: missing {', '.join(missing)}")
        if r["direction"] not in ("higher", "lower"):
            raise RulesError(f"rule {r['id']}: direction must be 'higher' or 'lower'")
        if not all(isinstance(r[k], (int, float)) for k in ("pass", "review")):
            raise RulesError(f"rule {r['id']}: pass/review must be numbers")
        if r["direction"] == "higher" and r["pass"] < r["review"]:
            raise RulesError(f"rule {r['id']}: for 'higher' rules pass must be >= review")
        if r["direction"] == "lower" and r["pass"] > r["review"]:
            raise RulesError(f"rule {r['id']}: for 'lower' rules pass must be <= review")
        if not str(r["metric"]).split(".")[0] in ("before", "after", "trimming"):
            raise RulesError(f"rule {r['id']}: metric must start with before., after. or trimming.")
        if r["id"] in seen:
            raise RulesError(f"duplicate rule id {r['id']}")
        seen.add(r["id"])
    return data


@dataclass
class RuleResult:
    id: str
    label: str
    metric: str
    value: Optional[float]
    status: str  # PASS / REVIEW / FAIL / N/A
    pass_threshold: float
    review_threshold: float
    direction: str
    unit: str
    explanation: str
    rationale: str

    def to_dict(self) -> dict:
        return asdict(self)


def _lookup(context: dict, path: str) -> Any:
    cur: Any = context
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _fmt(v: float) -> str:
    if abs(v) >= 1000:
        return f"{v:,.0f}"
    return f"{v:.2f}".rstrip("0").rstrip(".")


def evaluate_rule(rule: dict, context: dict) -> RuleResult:
    unit = rule.get("unit", "")
    raw = _lookup(context, rule["metric"])
    value = float(raw) if isinstance(raw, (int, float)) and not (isinstance(raw, float) and math.isnan(raw)) else None
    p, rv, d = float(rule["pass"]), float(rule["review"]), rule["direction"]
    op_pass, op_rev = (">=", ">=") if d == "higher" else ("<=", "<=")
    if value is None:
        status = "N/A"
        expl = "Metric not available for this run; the rule was not evaluated."
    else:
        good = (lambda x, t: x >= t) if d == "higher" else (lambda x, t: x <= t)
        if good(value, p):
            status = "PASS"
            expl = f"{_fmt(value)}{unit} meets the PASS threshold ({op_pass} {_fmt(p)}{unit})."
        elif good(value, rv):
            status = "REVIEW"
            expl = (f"{_fmt(value)}{unit} misses the PASS threshold ({op_pass} {_fmt(p)}{unit}) "
                    f"but is within the REVIEW range ({op_rev} {_fmt(rv)}{unit}).")
        else:
            status = "FAIL"
            expl = f"{_fmt(value)}{unit} is outside the acceptable range (REVIEW requires {op_rev} {_fmt(rv)}{unit})."
    return RuleResult(rule["id"], rule["label"], rule["metric"], value, status, p, rv, d, unit, expl,
                      " ".join(str(rule.get("rationale", "")).split()))


def evaluate(rules: dict, context: dict) -> dict:
    """context = {'before': summary, 'after': summary, 'trimming': stats}"""
    results = [evaluate_rule(r, context) for r in rules["rules"]]
    statuses = {r.status for r in results}
    overall = "FAIL" if "FAIL" in statuses else "REVIEW" if "REVIEW" in statuses else "PASS"
    drivers = [r.id for r in results if r.status == overall] if overall != "PASS" else []
    counts = {s: sum(1 for r in results if r.status == s) for s in (*STATUSES, "N/A")}
    if overall == "PASS":
        summary = "All evaluated rules are within their PASS thresholds."
    else:
        labels = [r.label for r in results if r.status == overall]
        summary = f"{overall} driven by: " + "; ".join(labels) + "."
    return {"overall": overall, "summary": summary, "drivers": drivers, "counts": counts,
            "results": [r.to_dict() for r in results]}
