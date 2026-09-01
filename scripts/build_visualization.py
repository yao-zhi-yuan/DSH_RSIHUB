#!/usr/bin/env python3
"""Render a completed run's ``summary.json`` into one shareable HTML page.

This reader consumes only the certified ``reports/<experiment-id>/summary.json``
that ``build_report.py`` writes; it makes no model calls and never touches the
workspace. The output is a single self-contained ``visualization.html`` with
inline SVG and CSS (no external CDN) presenting five regions:

- ``score-chart``: baseline to gen1/gen2/gen3 Gate and Sealed score lines with
  the champion marked;
- ``generation-overview``: per-generation parent/child, gate decision, and
  whether it became champion;
- ``candidate-diff`` (one per generation): each generation's target/prompt.md
  text diff;
- ``resource-consumption``: comparative bars for target/mutator tokens, request
  count, wall-time, and disk;
- ``improvement-hypothesis``: each generation's hypothesis and expected effect
  against the actual Gate outcome.

It applies the same redaction ``build_report.py`` uses and, on any missing data,
raises :class:`VisualizationError` naming the missing key rather than emitting a
partial page.
"""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|token|secret|password|authorization|auth)\b"
    r"(\s*[:=]\s*)([^\s,;}]+)"
)


class VisualizationError(RuntimeError):
    """The summary is missing data required to render a complete page."""


def _redact(text: str) -> str:
    text = _BEARER.sub("Bearer [REDACTED]", text)
    return _SECRET_ASSIGNMENT.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", text)


def _esc(value: Any) -> str:
    """Redact then HTML-escape a scalar for safe inline embedding."""
    return html.escape(_redact(str(value)))


def load_summary(path: Path) -> dict[str, Any]:
    """Load and minimally validate a ``summary.json`` document."""
    path = Path(path)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise VisualizationError(f"missing summary.json: {path}") from None
    except json.JSONDecodeError as exc:
        raise VisualizationError(f"malformed summary.json: {exc}") from None
    if not isinstance(value, dict):
        raise VisualizationError("summary.json must contain a JSON object")
    return value


def _require(mapping: Any, key: str, where: str) -> Any:
    if not isinstance(mapping, dict) or key not in mapping:
        raise VisualizationError(f"summary missing required key: {where}{key}")
    return mapping[key]


def _score_points(baseline_score: float, gen_scores: list[float | None], width: int, height: int) -> str:
    """Return an SVG polyline points string for a score series in [0,1]."""
    pad = 30
    span = width - 2 * pad
    steps = len(gen_scores)  # baseline is x0, then one x per generation
    points = []
    series = [baseline_score, *gen_scores]
    for index, score in enumerate(series):
        if score is None:
            continue
        x = pad + (span * index / max(1, steps))
        y = (height - pad) - (height - 2 * pad) * float(score)
        points.append(f"{x:.1f},{y:.1f}")
    return " ".join(points)


def _render_score_chart(summary: dict[str, Any]) -> str:
    baseline = _require(summary, "baseline", "")
    gate_base = float(_require(_require(baseline, "gate", "baseline."), "score", "baseline.gate."))
    sealed_base = float(_require(_require(baseline, "sealed", "baseline."), "score", "baseline.sealed."))
    generations = _require(summary, "generations", "")
    final = _require(summary, "final", "")
    champion_genid = str(_require(final, "champion_genid", "final."))

    gate_scores: list[float | None] = []
    sealed_scores: list[float | None] = []
    labels = ["baseline"]
    for generation in generations:
        name = str(_require(generation, "generation", "generations[]."))
        gate_scores.append(float(_require(_require(generation, "gate", f"gen {name}."), "score", f"gen {name}.gate.")))
        # Only the champion generation carries a Sealed anchor score.
        if generation.get("became_champion"):
            sealed_scores.append(float(_require(_require(final, "sealed", "final."), "score", "final.sealed.")))
        else:
            sealed_scores.append(None)
        labels.append(f"gen-{name}")

    width, height = 520, 220
    gate_line = _score_points(gate_base, gate_scores, width, height)
    sealed_line = _score_points(sealed_base, sealed_scores, width, height)

    # Mark the champion point on the gate line.
    pad, span = 30, width - 60
    champion_marker = ""
    for index, generation in enumerate(generations, start=1):
        if str(generation.get("generation")) == champion_genid:
            score = float(generation["gate"]["score"])
            x = pad + (span * index / max(1, len(generations)))
            y = (height - pad) - (height - 2 * pad) * score
            champion_marker = (
                f'<circle class="champion" cx="{x:.1f}" cy="{y:.1f}" r="6"/>'
                f'<text x="{x:.1f}" y="{y - 12:.1f}" class="champion-label" text-anchor="middle">champion</text>'
            )

    label_tags = "".join(
        f'<text x="{30 + (width - 60) * i / max(1, len(labels) - 1):.1f}" y="{height - 8}" '
        f'class="axis" text-anchor="middle">{html.escape(label)}</text>'
        for i, label in enumerate(labels)
    )

    return f"""<section id="score-chart" class="card">
  <h2>Score curve</h2>
  <svg viewBox="0 0 {width} {height}" role="img" aria-label="score curve">
    <line class="grid" x1="30" y1="{height - 30}" x2="{width - 30}" y2="{height - 30}"/>
    <line class="grid" x1="30" y1="30" x2="30" y2="{height - 30}"/>
    <polyline class="gate" points="{gate_line}"/>
    <polyline class="sealed" points="{sealed_line}"/>
    {champion_marker}
    {label_tags}
  </svg>
  <p class="legend"><span class="swatch gate"></span>Gate&nbsp;&nbsp;<span class="swatch sealed"></span>Sealed (champion anchor)</p>
</section>"""


def _render_generation_overview(summary: dict[str, Any]) -> str:
    generations = _require(summary, "generations", "")
    rows = []
    for generation in generations:
        name = str(_require(generation, "generation", "generations[]."))
        parent = _esc(_require(generation, "parent", f"gen {name}."))
        verdict = _esc(_require(generation, "verdict", f"gen {name}."))
        champion = "yes" if generation.get("became_champion") else "no"
        score = _esc(_require(_require(generation, "gate", f"gen {name}."), "score", f"gen {name}.gate."))
        decision_class = "keep" if str(generation.get("verdict")) == "keep" else "discard"
        rows.append(
            f'<tr><td>gen-{html.escape(name)}</td><td>{parent}</td><td>{score}</td>'
            f'<td class="{decision_class}">{verdict}</td><td>{champion}</td></tr>'
        )
    body = "\n".join(rows)
    return f"""<section id="generation-overview" class="card">
  <h2>Generation overview</h2>
  <table>
    <thead><tr><th>Generation</th><th>Parent</th><th>Gate</th><th>Decision</th><th>Champion</th></tr></thead>
    <tbody>
{body}
    </tbody>
  </table>
</section>"""


def _render_candidate_diffs(summary: dict[str, Any]) -> str:
    generations = _require(summary, "generations", "")
    blocks = []
    for generation in generations:
        name = str(_require(generation, "generation", "generations[]."))
        diff = _require(generation, "diff", f"gen {name}.")
        commit = _esc(generation.get("candidate_commit", ""))
        lines = []
        for line in str(diff).splitlines():
            css = "ctx"
            if line.startswith("+") and not line.startswith("+++"):
                css = "add"
            elif line.startswith("-") and not line.startswith("---"):
                css = "del"
            lines.append(f'<span class="{css}">{_esc(line)}</span>')
        pre = "\n".join(lines)
        blocks.append(
            f'<article class="candidate-diff diff-card">\n'
            f"  <h3>gen-{html.escape(name)} <span class=\"commit\">{commit}</span></h3>\n"
            f'  <pre class="diff">{pre}</pre>\n'
            f"</article>"
        )
    body = "\n".join(blocks)
    return f"""<section id="region-diffs" class="card">
  <h2>Candidate diffs</h2>
{body}
</section>"""


def _bar(label: str, value: float, maximum: float, display: str) -> str:
    pct = 0.0 if maximum <= 0 else min(100.0, 100.0 * value / maximum)
    return (
        f'<div class="bar-row"><span class="bar-label">{html.escape(label)}</span>'
        f'<span class="bar-track"><span class="bar-fill" style="width:{pct:.1f}%"></span></span>'
        f'<span class="bar-value">{html.escape(display)}</span></div>'
    )


def _render_resources(summary: dict[str, Any]) -> str:
    resources = _require(summary, "resources", "")
    target = _require(resources, "target", "resources.")
    mutator = _require(resources, "mutator", "resources.")
    target_tokens = int(_require(target, "total_tokens", "resources.target."))
    mutator_tokens = int(_require(mutator, "total_tokens", "resources.mutator."))
    requests = int(_require(mutator, "request_count", "resources.mutator."))
    wall_s = float(_require(resources, "wall_s", "resources."))
    disk_bytes = int(_require(resources, "disk_bytes", "resources."))

    token_max = max(target_tokens, mutator_tokens, 1)
    disk_mb = disk_bytes / (1024 * 1024)
    bars = "\n".join(
        [
            _bar("target tokens", target_tokens, token_max, f"{target_tokens:,}"),
            _bar("mutator tokens", mutator_tokens, token_max, f"{mutator_tokens:,}"),
            _bar("mutator requests", requests, max(requests, 1), str(requests)),
            _bar("wall time (s)", wall_s, max(wall_s, 1.0), f"{wall_s:,.0f}"),
            _bar("disk (MB)", disk_mb, max(disk_mb, 1.0), f"{disk_mb:,.1f}"),
        ]
    )
    return f"""<section id="resource-consumption" class="card">
  <h2>Resource consumption</h2>
  <div class="bars">
{bars}
  </div>
</section>"""


def _render_hypotheses(summary: dict[str, Any]) -> str:
    generations = _require(summary, "generations", "")
    items = []
    for generation in generations:
        name = str(_require(generation, "generation", "generations[]."))
        mutation = _require(generation, "mutation", f"gen {name}.")
        hypothesis = _esc(_require(mutation, "hypothesis", f"gen {name}.mutation."))
        expected = _esc(_require(mutation, "expected_effect", f"gen {name}.mutation."))
        gate_score = _esc(_require(_require(generation, "gate", f"gen {name}."), "score", f"gen {name}.gate."))
        verdict = _esc(_require(generation, "verdict", f"gen {name}."))
        outcome_class = "keep" if str(generation.get("verdict")) == "keep" else "discard"
        items.append(
            f'<article class="hypothesis">\n'
            f"  <h3>gen-{html.escape(name)} &rarr; Gate {gate_score} "
            f'(<span class="{outcome_class}">{verdict}</span>)</h3>\n'
            f'  <p class="hyp"><strong>Hypothesis:</strong> {hypothesis}</p>\n'
            f'  <p class="exp"><strong>Expected:</strong> {expected}</p>\n'
            f"</article>"
        )
    body = "\n".join(items)
    return f"""<section id="improvement-hypothesis" class="card">
  <h2>Improvement hypotheses</h2>
{body}
</section>"""


_CSS = """
:root { color-scheme: light dark; --bg:#0f1419; --card:#171d26; --fg:#e6edf3; --muted:#8b949e;
  --gate:#4c8dff; --sealed:#f0a020; --keep:#3fb950; --discard:#f85149; --add:#2ea043; --del:#da3633; }
* { box-sizing: border-box; }
body { margin:0; padding:24px; background:var(--bg); color:var(--fg);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }
header h1 { margin:0 0 4px; font-size:22px; }
header .meta { color:var(--muted); font-size:13px; margin-bottom:20px; }
.grid-2 { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
@media (max-width:820px){ .grid-2 { grid-template-columns:1fr; } }
.card { background:var(--card); border:1px solid #21262d; border-radius:10px; padding:16px; margin-bottom:16px; }
.card h2 { margin:0 0 12px; font-size:16px; }
svg { width:100%; height:auto; }
.grid { stroke:#30363d; stroke-width:1; }
polyline { fill:none; stroke-width:2.5; }
polyline.gate { stroke:var(--gate); }
polyline.sealed { stroke:var(--sealed); stroke-dasharray:5 4; }
circle.champion { fill:var(--keep); stroke:#fff; stroke-width:1.5; }
.champion-label { fill:var(--keep); font-size:11px; font-weight:600; }
text.axis { fill:var(--muted); font-size:11px; }
.legend { color:var(--muted); font-size:12px; margin:8px 0 0; }
.swatch { display:inline-block; width:12px; height:12px; border-radius:2px; vertical-align:middle; margin-right:4px; }
.swatch.gate { background:var(--gate); } .swatch.sealed { background:var(--sealed); }
table { width:100%; border-collapse:collapse; font-size:13px; }
th,td { text-align:left; padding:6px 8px; border-bottom:1px solid #21262d; }
th { color:var(--muted); font-weight:600; }
td.keep { color:var(--keep); font-weight:600; } td.discard { color:var(--discard); font-weight:600; }
.diff-card { margin-bottom:14px; } .diff-card h3 { font-size:14px; margin:0 0 6px; }
pre.diff { margin:0; padding:10px; background:#0d1117; border-radius:6px; overflow-x:auto;
  font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12px; line-height:1.5; }
pre.diff span { display:block; white-space:pre-wrap; }
pre.diff .add { color:var(--add); } pre.diff .del { color:var(--del); } pre.diff .ctx { color:var(--muted); }
.bars { display:flex; flex-direction:column; gap:8px; }
.bar-row { display:grid; grid-template-columns:130px 1fr 90px; align-items:center; gap:8px; font-size:12px; }
.bar-label { color:var(--muted); } .bar-value { text-align:right; font-variant-numeric:tabular-nums; }
.bar-track { background:#0d1117; border-radius:4px; height:14px; overflow:hidden; }
.bar-fill { display:block; height:100%; background:linear-gradient(90deg,var(--gate),var(--sealed)); }
.hypothesis { border-left:3px solid #30363d; padding:2px 0 2px 12px; margin-bottom:12px; }
.hypothesis h3 { font-size:13px; margin:0 0 4px; }
.hypothesis p { margin:2px 0; font-size:13px; color:var(--fg); }
.keep { color:var(--keep); } .discard { color:var(--discard); }
"""


def render_html(summary: dict[str, Any]) -> str:
    """Render the full self-contained visualization page from a summary dict."""
    experiment = _require(summary, "experiment", "")
    experiment_id = _esc(_require(experiment, "experiment_id", "experiment."))
    target_model = _esc(experiment.get("target_model", ""))
    mutator = _esc(experiment.get("mutator_operator", ""))
    final = _require(summary, "final", "")
    champion = _esc(_require(final, "champion_genid", "final."))
    champion_score = _esc(_require(final, "champion_score", "final."))

    score_chart = _render_score_chart(summary)
    overview = _render_generation_overview(summary)
    diffs = _render_candidate_diffs(summary)
    resources = _render_resources(summary)
    hypotheses = _render_hypotheses(summary)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Evolution results: {experiment_id}</title>
<style>{_CSS}</style>
</head>
<body>
<header>
  <h1>Evolution results: {experiment_id}</h1>
  <div class="meta">target <code>{target_model}</code> &middot; mutator <code>{mutator}</code>
    &middot; champion gen-{champion} (score {champion_score})</div>
</header>
{score_chart}
<div class="grid-2">
{overview}
{resources}
</div>
{hypotheses}
{diffs}
</body>
</html>
"""


def write_visualization(report_dir: Path) -> Path:
    """Render ``<report_dir>/summary.json`` to ``<report_dir>/visualization.html``."""
    report_dir = Path(report_dir)
    summary = load_summary(report_dir / "summary.json")
    output = report_dir / "visualization.html"
    output.write_text(render_html(summary), encoding="utf-8")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, help="(unused; accepted for plan symmetry)")
    parser.add_argument("--report", type=Path, required=True, help="report bundle directory")
    args = parser.parse_args(argv)
    output = write_visualization(args.report)
    print(f"visualization: wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
