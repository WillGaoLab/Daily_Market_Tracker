"""Add accessible interaction targets to the original Matplotlib SVG figure.

The radar/heatmap geometry, labels, colors and scale still come exclusively
from generate_fingerprint.generate; this module does not redraw the chart.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import tempfile
import threading
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    from .generate_fingerprint import INSTRUMENTS, generate, load_record
    from .history import read_history
except ImportError:
    from generate_fingerprint import INSTRUMENTS, generate, load_record
    from history import read_history

import matplotlib

ROOT = Path(__file__).resolve().parents[1]
SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
RENDER_LOCK = threading.RLock()


def values_for(row: dict[str, str]) -> list[float]:
    try:
        values = [float(row[f"{key}_{field}"]) for key, _, _, field in INSTRUMENTS]
    except (ValueError, KeyError) as error:
        raise ValueError("This date has unavailable migrated values; a complete fingerprint cannot be drawn.") from error
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Fingerprint values must be finite.")
    return values


def render_svg(target_date: str, history_path: Path = ROOT / "data/history.csv") -> str:
    row = load_record(target_date, history_path)
    values = values_for(row)
    with RENDER_LOCK, tempfile.TemporaryDirectory() as directory, matplotlib.rc_context({"svg.hashsalt": "market-fingerprint"}):
        path = generate(target_date, Path(directory) / "fingerprint.svg", history_path)
        svg = ET.parse(path).getroot()
    # Remove variable timestamps and RDF metadata; keep the original drawing.
    for child in list(svg):
        if child.tag == f"{{{SVG_NS}}}metadata":
            svg.remove(child)
    svg.set("data-fingerprint-date", target_date)
    svg.set("data-fingerprint-values", json.dumps(values, separators=(",", ":")))
    svg.set("role", "group")
    svg.set("aria-label", f"Overnight Market Fingerprint for {target_date}. Nine radar points and nine heatmap tiles; focus or tap for details.")
    svg.set("width", "100%")
    svg.set("height", "100%")
    elements = {element.get("id"): element for element in svg.iter() if element.get("id")}
    markers = list(elements["fingerprint-radar"].iter(f"{{{SVG_NS}}}use"))[:9]
    if len(markers) != 9:
        raise ValueError("The original radar must expose nine marker positions.")
    heatmap = elements["axes_2"]
    patch = heatmap.find(f"{{{SVG_NS}}}g/{{{SVG_NS}}}path")
    coordinates = [float(number) for number in re.findall(r"-?\d+(?:\.\d+)?", patch.get("d", ""))]
    if len(coordinates) != 8:
        raise ValueError("Cannot locate the original heatmap boundary.")
    x0, x1 = min(coordinates[::2]), max(coordinates[::2])
    y0, y1 = min(coordinates[1::2]), max(coordinates[1::2])
    svg.set("data-radar-view", "20 63 440 385")
    svg.set("data-heatmap-view", f"{x0 - 24} {y0 - 65} {x1 - x0 + 48} {y1 - y0 + 150}")
    overlay = ET.SubElement(svg, f"{{{SVG_NS}}}g", {"id": "fingerprint-targets"})
    for index, ((key, label, reverse, _), value, marker) in enumerate(zip(INSTRUMENTS, values, markers)):
        adjusted = -value if reverse else value
        attrs = {
            "data-indicator": key, "tabindex": "0", "role": "button",
            "aria-label": f"{label}: raw {value:+.3f}%, direction-adjusted {adjusted:+.3f}%. Show details.",
            "fill": "transparent", "stroke": "transparent", "pointer-events": "all",
        }
        for tag, geometry in (
            ("circle", {"cx": marker.get("x"), "cy": marker.get("y"), "r": "8"}),
            ("rect", {"x": str(x0 + index * (x1 - x0) / 9), "y": str(y0), "width": str((x1 - x0) / 9), "height": str(y1 - y0)}),
        ):
            target = ET.SubElement(overlay, f"{{{SVG_NS}}}{tag}", {**attrs, **geometry})
            ET.SubElement(target, f"{{{SVG_NS}}}title").text = attrs["aria-label"]
    return "\n".join(line.rstrip() for line in ET.tostring(svg, encoding="unicode").splitlines()) + "\n"


def export_svg(target_date: str, history_path: Path = ROOT / "data/history.csv", output_dir: Path = ROOT / "figures") -> Path:
    output = output_dir / f"{target_date}.svg"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_svg(target_date, history_path), encoding="utf-8")
    return output


def component_html(row: dict[str, str], svg: str) -> str:
    """Self-contained Streamlit viewer; no CDN or remote data dependency."""
    def safe_json(value: object) -> str:
        return json.dumps(value).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    css = (ROOT / "web/fingerprint.css").read_text()
    js = (ROOT / "web/fingerprint.js").read_text()
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><style>{css}</style><body style="margin:0"><div data-fingerprint-explorer></div><script>{js}</script><script>FingerprintExplorer.mount(document.querySelector('[data-fingerprint-explorer]'), {{rows: {safe_json([row])}, initialDate: {safe_json(row['date'])}, selectable: false, loadSvg: async () => {safe_json(svg)}}});</script></body></html>'''


def main() -> None:
    parser = argparse.ArgumentParser(description="Export interactive SVGs using the existing fingerprint plotting code.")
    parser.add_argument("--date")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    rows = read_history(ROOT / "data/history.csv")
    dates = [row["date"] for row in rows] if args.all else [args.date or max(row["date"] for row in rows)]
    for day in dates:
        try:
            values_for(load_record(day))
        except ValueError as error:
            if not args.all:
                raise
            print(f"Skipped {day}: {error}", flush=True)
            continue
        print(f"Wrote {export_svg(day)}", flush=True)


if __name__ == "__main__":
    main()
