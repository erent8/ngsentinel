"""Self-contained HTML QC report (Plotly charts embedded, works offline)."""
from __future__ import annotations

import html
import re
from pathlib import Path

import plotly.graph_objects as go
from jinja2 import Environment, select_autoescape

BEFORE = "#94a3b8"
AFTER = "#0ea5e9"
STATUS_COLORS = {"PASS": "#059669", "REVIEW": "#d97706", "FAIL": "#dc2626", "N/A": "#64748b"}


def _layout(fig: go.Figure, title: str, x: str, y: str) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, font=dict(size=15)),
        template="plotly_white",
        height=340,
        margin=dict(l=55, r=20, t=50, b=45),
        legend=dict(orientation="h", y=-0.22),
        xaxis_title=x,
        yaxis_title=y,
        font=dict(family="Inter, Segoe UI, Arial, sans-serif", size=12),
    )
    return fig


def fig_per_base_quality(before: dict, after: dict | None) -> go.Figure:
    fig = go.Figure()
    for lo, hi, col in ((28, 41, "rgba(16,185,129,0.08)"), (20, 28, "rgba(245,158,11,0.10)"), (0, 20, "rgba(239,68,68,0.08)")):
        fig.add_hrect(y0=lo, y1=hi, fillcolor=col, line_width=0, layer="below")
    for name, m, col in (("raw", before, BEFORE), ("processed", after, AFTER)):
        if not m:
            continue
        pb = m["per_base_quality"]
        x = pb["position"]
        fig.add_trace(go.Scatter(x=x + x[::-1], y=pb["p75"] + pb["p25"][::-1], fill="toself", fillcolor=col, opacity=0.18,
                                 line=dict(width=0), hoverinfo="skip", name=f"{name} IQR", showlegend=False))
        fig.add_trace(go.Scatter(x=x, y=pb["mean"], name=f"{name} mean", line=dict(color=col, width=2.4)))
    fig.update_yaxes(range=[0, 41])
    return _layout(fig, "Per-base sequence quality (mean, interquartile range)", "Position in read (bp)", "Phred score")


def fig_gc(before: dict, after: dict | None) -> go.Figure:
    fig = go.Figure()
    for name, m, col in (("raw", before, BEFORE), ("processed", after, AFTER)):
        if m:
            fig.add_trace(go.Scatter(x=m["gc_content"]["gc"], y=m["gc_content"]["pct"], name=f"{name} observed", line=dict(color=col, width=2.2)))
    ref = after or before
    fig.add_trace(go.Scatter(x=ref["gc_content"]["gc"], y=ref["gc_content"]["theoretical_pct"], name="normal fit",
                             line=dict(color="#0f172a", dash="dash", width=1.4)))
    return _layout(fig, "Per-sequence GC content", "Mean GC content (%)", "% of reads")


def fig_adapter(before: dict, after: dict | None) -> go.Figure:
    fig = go.Figure()
    for name, m, col, dash in (("raw", before, BEFORE, "solid"), ("processed", after, AFTER, "solid")):
        if not m:
            continue
        ac = m["adapter_content"]
        for i, (atype, vals) in enumerate(ac["series"].items()):
            if max(vals or [0]) < 0.01 and atype not in ("Illumina Universal Adapter",):
                continue
            fig.add_trace(go.Scatter(x=ac["position"], y=vals, name=f"{name}: {atype}", line=dict(color=col, width=2, dash=["solid", "dot", "dash", "dashdot", "longdash"][i % 5])))
    return _layout(fig, "Adapter content (cumulative % of reads)", "Position in read (bp)", "% of reads")


def fig_lengths(before: dict, after: dict | None) -> go.Figure:
    fig = go.Figure()
    for name, m, col in (("raw", before, BEFORE), ("processed", after, AFTER)):
        if m:
            ld = m["length_distribution"]
            fig.add_trace(go.Bar(x=ld["length"], y=ld["count"], name=name, marker_color=col, opacity=0.75))
    fig.update_layout(barmode="overlay")
    return _layout(fig, "Read length distribution", "Read length (bp)", "Reads")


def fig_duplication(before: dict, after: dict | None) -> go.Figure:
    fig = go.Figure()
    for name, m, col in (("raw", before, BEFORE), ("processed", after, AFTER)):
        if m:
            d = m["duplication_levels"]
            fig.add_trace(go.Bar(x=[r["level"] for r in d], y=[r["pct_of_reads"] for r in d], name=name, marker_color=col))
    fig.update_layout(barmode="group")
    return _layout(fig, "Sequence duplication levels (sampled reads)", "Copies per sequence", "% of reads")


def fig_n(before: dict, after: dict | None) -> go.Figure:
    fig = go.Figure()
    for name, m, col in (("raw", before, BEFORE), ("processed", after, AFTER)):
        if m:
            fig.add_trace(go.Scatter(x=m["per_base_n"]["position"], y=m["per_base_n"]["pct"], name=name, line=dict(color=col, width=2)))
    return _layout(fig, "Per-base N content", "Position in read (bp)", "% N")


SUMMARY_ROWS = [
    ("total_reads", "Total reads", "{:,.0f}"),
    ("total_bases", "Total bases", "{:,.0f}"),
    ("mean_length", "Mean read length (bp)", "{:.1f}"),
    ("mean_quality", "Mean base quality (Phred)", "{:.2f}"),
    ("q20_pct", "Bases ≥ Q20 (%)", "{:.2f}"),
    ("q30_pct", "Bases ≥ Q30 (%)", "{:.2f}"),
    ("gc_pct", "GC content (%)", "{:.2f}"),
    ("n_pct", "N bases (%)", "{:.3f}"),
    ("adapter_max_pct", "Max adapter content (%)", "{:.2f}"),
    ("duplication_pct", "Duplicate reads, sampled (%)", "{:.2f}"),
    ("gc_deviation_pct", "GC deviation from normal (%)", "{:.2f}"),
]

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NGSentinel QC report — {{ m.sample }}</title>
<style>
:root{--ink:#0f2747;--muted:#64748b;--line:#e2e8f0;--cyan:#0ea5e9}
*{box-sizing:border-box}body{margin:0;font-family:Inter,"Segoe UI",Arial,sans-serif;color:#1e293b;background:#f6f9fc;line-height:1.5}
header{background:linear-gradient(120deg,#020611,#0b1c38);color:#fff;padding:28px 40px}
header h1{margin:0;font-size:26px}header .sub{color:#93c5fd;font-size:14px;margin-top:4px}
main{max-width:1180px;margin:0 auto;padding:24px 40px 60px}
section{background:#fff;border:1px solid var(--line);border-radius:12px;padding:20px 24px;margin:18px 0}
h2{font-size:18px;color:var(--ink);margin:0 0 12px;border-left:4px solid var(--cyan);padding-left:10px}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.04em}
td.num{text-align:right;font-variant-numeric:tabular-nums}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px}
.kv{background:#f1f6fc;border:1px solid #dbe6f3;border-radius:8px;padding:8px 12px}.kv b{display:block;font-size:11px;color:var(--muted);letter-spacing:.05em;text-transform:uppercase;font-weight:600}
.chip{display:inline-block;padding:2px 10px;border-radius:999px;font-weight:700;font-size:12px;letter-spacing:.05em;color:#fff}
.overall{display:flex;align-items:center;gap:18px}.overall .chip{font-size:20px;padding:6px 20px}
.charts{display:grid;grid-template-columns:repeat(auto-fit,minmax(520px,1fr));gap:12px}
code,.mono{font-family:"JetBrains Mono",Consolas,monospace;font-size:12.5px}
.muted{color:var(--muted)}.warn{color:#b45309}.err{color:#b91c1c}
.disclaimer{font-size:12.5px;color:var(--muted)}
</style>
{{ plotly_js|safe }}
</head><body>
<header><h1>NGSentinel QC report — {{ m.sample }}</h1>
<div class="sub">Run {{ m.run_id }} · generated {{ m.finished_at }} · NGSentinel v{{ m.ngsentinel_version }}</div></header>
<main>
<section><h2>QC decision</h2>
<div class="overall"><span class="chip" style="background:{{ colors[d.overall] }}">{{ d.overall }}</span><div>{{ d.summary }}</div></div>
<table style="margin-top:14px"><tr><th>Rule</th><th>Value</th><th>Status</th><th>Explanation</th></tr>
{% for r in d.results %}<tr><td><b>{{ r.label }}</b><div class="muted mono">{{ r.metric }}</div></td>
<td class="num">{{ fmtv(r.value) }}{{ r.unit if r.value is not none else '' }}</td>
<td><span class="chip" style="background:{{ colors[r.status] }}">{{ r.status }}</span></td>
<td>{{ r.explanation }}<div class="muted" style="font-size:12.5px;margin-top:4px">Why it matters: {{ r.rationale }}</div></td></tr>{% endfor %}
</table>
<p class="muted" style="font-size:12.5px">Thresholds come from <span class="mono">{{ rules_name }}</span> and are configurable. They are general starting points, not universal standards.</p>
</section>

<section><h2>Analysis metadata</h2><div class="grid">
<div class="kv"><b>Sample</b>{{ m.sample }}</div><div class="kv"><b>Run ID</b><span class="mono">{{ m.run_id }}</span></div>
<div class="kv"><b>Layout</b>{{ 'paired-end' if m.paired else 'single-end' }}</div>
<div class="kv"><b>Started</b>{{ m.started_at }}</div><div class="kv"><b>Finished</b>{{ m.finished_at }}</div>
<div class="kv"><b>Quality encoding</b>{{ m.validation.r1.encoding }}</div>
<div class="kv"><b>QC read limit</b>{{ '{:,}'.format(m.config.qc_max_reads) if m.config.qc_max_reads else 'all reads' }}</div>
</div></section>

<section><h2>Tools &amp; engines</h2><table><tr><th>Step</th><th>Engine</th><th>Version</th><th>Status</th></tr>
{% for s in m.steps %}<tr><td>{{ s.step }}</td><td>{{ s.engine }}</td><td class="mono">{{ s.version or '—' }}</td><td>{{ s.status }}{% if s.note %}<div class="muted" style="font-size:12.5px">{{ s.note }}</div>{% endif %}</td></tr>{% endfor %}
</table></section>

<section><h2>Input validation</h2>
{% for key, v in m.validation.items() if v and key != 'pair' %}<p><b>{{ key|upper }}</b> <span class="mono">{{ v.path }}</span> — {{ '{:,}'.format(v.reads_checked) }} reads checked,
{{ 'valid' if v.ok else 'INVALID' }}, lengths {{ v.min_length }}–{{ v.max_length }} bp, {{ 'gzip' if v.compressed else 'plain text' }}.
{% for w in v.warnings %}<br><span class="warn">⚠ {{ w }}</span>{% endfor %}{% for e in v.errors %}<br><span class="err">✕ {{ e }}</span>{% endfor %}</p>{% endfor %}
{% if m.validation.pair %}<p><b>Pairing</b> — {{ '{:,}'.format(m.validation.pair.reads_compared) }} read pairs compared: {{ 'IDs consistent' if m.validation.pair.ok else 'PROBLEMS FOUND' }}{% for e in m.validation.pair.errors %}<br><span class="err">✕ {{ e }}</span>{% endfor %}</p>{% endif %}
</section>

<section><h2>Before / after preprocessing</h2>
<table><tr><th>Metric</th><th style="text-align:right">Raw</th><th style="text-align:right">Processed</th><th style="text-align:right">Change</th></tr>
{% for key, label, f in rows %}<tr><td>{{ label }}</td><td class="num">{{ fmt(f, before.get(key)) }}</td><td class="num">{{ fmt(f, after.get(key)) }}</td><td class="num">{{ delta(before.get(key), after.get(key)) }}</td></tr>{% endfor %}
</table>
<h3 style="font-size:15px;margin-top:20px">Preprocessing ({{ t.engine }})</h3>
<div class="grid"><div class="kv"><b>Reads in → out</b>{{ '{:,}'.format(t.reads_in) }} → {{ '{:,}'.format(t.reads_out) }}</div>
<div class="kv"><b>Read retention</b>{{ '%.2f'|format(t.retention_pct) }} %</div>
<div class="kv"><b>Reads lost</b>{{ '{:,}'.format(t.reads_in - t.reads_out) }}</div>
<div class="kv"><b>Adapter-trimmed reads</b>{{ '{:,}'.format(t.adapter_trimmed_reads) }}</div>
<div class="kv"><b>Removed: too short</b>{{ '{:,}'.format(t.filtered_too_short) }}</div>
<div class="kv"><b>Removed: too many N</b>{{ '{:,}'.format(t.filtered_too_many_n) }}</div>
<div class="kv"><b>Removed: low quality</b>{{ '{:,}'.format(t.filtered_low_quality) }}</div></div>
</section>

<section><h2>Quality charts</h2><div class="charts">{% for c in charts %}<div>{{ c|safe }}</div>{% endfor %}</div></section>

{% if over %}<section><h2>Overrepresented sequences (processed, sampled)</h2><table><tr><th>Sequence</th><th style="text-align:right">Count</th><th style="text-align:right">%</th><th>Possible source</th></tr>
{% for o in over %}<tr><td class="mono">{{ o.sequence }}</td><td class="num">{{ o.count }}</td><td class="num">{{ '%.3f'|format(o.pct) }}</td><td>{{ o.possible_source }}</td></tr>{% endfor %}</table></section>{% endif %}

<section><h2>Scientific interpretation</h2><ul>{% for line in interpretation %}<li>{{ line }}</li>{% endfor %}</ul></section>

<section><h2>Provenance</h2>
<table><tr><th>Input</th><th>SHA-256</th><th style="text-align:right">Size</th></tr>
{% for i in m.inputs %}<tr><td class="mono">{{ i.path }}</td><td class="mono">{{ i.sha256 }}</td><td class="num">{{ '{:,}'.format(i.size_bytes) }} B</td></tr>{% endfor %}</table>
<h3 style="font-size:15px">Parameters</h3><pre class="mono" style="background:#f1f5f9;padding:12px;border-radius:8px;white-space:pre-wrap">{{ params }}</pre>
{% if m.commands %}<h3 style="font-size:15px">Commands executed</h3>{% for c in m.commands %}<pre class="mono" style="background:#f1f5f9;padding:10px;border-radius:8px;white-space:pre-wrap">{{ c }}</pre>{% endfor %}{% endif %}
<p class="muted" style="font-size:12.5px">Platform: {{ m.platform }} · Python {{ m.python }}</p>
</section>
<p class="disclaimer">NGSentinel is a research and education tool for sequencing data quality control. It does not provide clinical or diagnostic results.</p>
</main></body></html>"""


def _fmt(f: str, v) -> str:
    if v is None:
        return "—"
    try:
        return f.format(v)
    except (ValueError, TypeError):
        return html.escape(str(v))


def _delta(a, b) -> str:
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        return "—"
    d = b - a
    if abs(d) >= 1000:
        return f"{d:+,.0f}"
    return f"{d:+.2f}"


def interpret(before: dict, after: dict, trimming: dict) -> list[str]:
    """Plain-language statements derived only from this run's numbers."""
    out = []
    b, a = before["summary"], after["summary"]
    pb = before["per_base_quality"]["mean"]
    if len(pb) >= 10:
        head = sum(pb[: len(pb) // 5]) / max(1, len(pb) // 5)
        tail = sum(pb[-max(1, len(pb) // 5):]) / max(1, len(pb) // 5)
        if head - tail >= 3:
            out.append(f"Raw mean quality drops from about Q{head:.0f} at the 5′ end to Q{tail:.0f} at the 3′ end, "
                       "the typical decline of sequencing-by-synthesis chemistry; 3′ quality trimming targets this.")
    if b["adapter_max_pct"] >= 1:
        out.append(f"Adapter sequence was detected in up to {b['adapter_max_pct']:.1f} % of raw reads (by read end) and "
                   f"{a['adapter_max_pct']:.2f} % after preprocessing, consistent with inserts shorter than the read length.")
    out.append(f"Preprocessing retained {trimming['retention_pct']:.1f} % of reads "
               f"({trimming['reads_in'] - trimming['reads_out']:,} reads removed); Q30 changed from {b['q30_pct']:.1f} % to {a['q30_pct']:.1f} %.")
    if a["duplication_pct"] > 30:
        out.append(f"{a['duplication_pct']:.1f} % of sampled reads are duplicates; this can reflect PCR duplication or low complexity, "
                   "but is expected for amplicon or highly expressed transcripts.")
    if a.get("gc_deviation_pct") is not None and a["gc_deviation_pct"] > 15:
        out.append(f"The GC distribution deviates {a['gc_deviation_pct']:.1f} % from a normal shape, which may indicate contamination or library bias.")
    if b.get("truncated"):
        out.append("QC metrics were computed on a subset of reads (read limit), so they are estimates.")
    return out


def build_report(manifest: dict, before: dict, after: dict, trimming: dict, decision: dict, out_path: Path) -> Path:
    figs = [fig_per_base_quality(before, after), fig_adapter(before, after), fig_gc(before, after),
            fig_lengths(before, after), fig_duplication(before, after), fig_n(before, after)]
    charts = [f.to_html(full_html=False, include_plotlyjs=False, config={"displaylogo": False}) for f in figs]
    from plotly.offline import get_plotlyjs  # noqa: WPS433

    env = Environment(autoescape=select_autoescape(["html"]))
    tpl = env.from_string(TEMPLATE)
    import yaml

    page = tpl.render(
        m=manifest, d=decision, colors=STATUS_COLORS, before=before["summary"], after=after["summary"], t=trimming,
        rules_name=re.split(r"[\\/]", manifest.get("rules_file") or "qc_rules.yaml")[-1],  # file name only, no local path
        rows=SUMMARY_ROWS, fmt=_fmt, delta=_delta, fmtv=lambda v: "—" if v is None else (f"{v:,.0f}" if abs(v) >= 1000 else f"{v:.2f}"),
        charts=charts, over=after.get("overrepresented", []), interpretation=interpret(before, after, trimming),
        params=yaml.safe_dump(manifest["config"], sort_keys=False, allow_unicode=True),
        # a literal U+FFFD in plotly.js is written as its JS escape (same behaviour, cleaner text)
        plotly_js="<script>" + get_plotlyjs().replace(chr(0xFFFD), "\\uFFFD") + "</script>",
    )
    out_path.write_text(page, encoding="utf-8")
    return out_path
