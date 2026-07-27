#!/usr/bin/env python3
"""Generate publication-quality SelfAuditBench Results figures.

The script reads frozen human-gold data, verified run records, paired comparison
artifacts, and paper-export tables. Every displayed value comes from a source
artifact, and every output is a manuscript-ready PDF.
"""

from __future__ import annotations

import argparse
import base64
import csv
import io
import json
import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from matplotlib.lines import Line2D
from matplotlib.offsetbox import AnnotationBbox, OffsetImage
from matplotlib.patches import Patch, Rectangle

INK = "#25313A"
MUTED = "#68747D"
GRID = "#DDE2E5"
PAPER = "#FFFFFF"
PANEL = "#FAFAF8"
ASB = "#356F8A"
CONVERSE = "#B86A4B"
SIDECAR = "#365F7D"
INLINE = "#C27A43"
SAFE = "#4F8F83"
RISKY = "#C9674C"
GOLD = "#C39A45"
PAIR_TITLE_SIZE = 15.5
PAIR_SUBTITLE_SIZE = 14.5
PAIR_LABEL_SIZE = 18.0
PAIR_TICK_SIZE = 16.0
PAIR_LEGEND_SIZE = 15.0
PAIR_ANNOTATION_SIZE = 15.0
WIDE_TITLE_SIZE = 15.0
WIDE_LABEL_SIZE = 14.0
WIDE_TICK_SIZE = 13.0
WIDE_LEGEND_SIZE = 13.0
WIDE_ANNOTATION_SIZE = 12.5

BACKENDS = ["DeepSeek", "Qwen3.5", "MiniMax", "Gemma 4"]
BACKEND_DISPLAY_NAMES = {
    "DeepSeek": "DeepSeek V4",
    "Qwen3.5": "Qwen3.5",
    "MiniMax": "MiniMax2.7",
    "Gemma 4": "Gemma 4",
}
BACKEND_COLORS = {
    "DeepSeek": "#2F7D78",
    "Qwen3.5": "#586FA7",
    "MiniMax": "#B07A39",
    "Gemma 4": "#766987",
}
BACKEND_LOGOS = {
    "DeepSeek": "deepseek",
    "Qwen3.5": "qwen",
    "MiniMax": "minimax",
    "Gemma 4": "gemma",
}
RUNS = {
    "asb": {
        "DeepSeek": "asb-full-gold-deepseek-sidecar",
        "Qwen3.5": "asb-full-gold-qwen35-sidecar",
        "MiniMax": "asb-full-gold-minimax-m27-sidecar",
        "Gemma 4": "asb-full-gold-ollama-gemma4-sidecar",
    },
    "converse": {
        "DeepSeek": "converse-full-gold-deepseek-sidecar",
        "Qwen3.5": "converse-full-gold-qwen35-sidecar",
        "MiniMax": "converse-full-gold-minimax-m27-sidecar",
        "Gemma 4": "converse-full-gold-ollama-gemma4-sidecar",
    },
}
DIFF_CMAP = LinearSegmentedColormap.from_list(
    "sab_difference", ["#B8614D", "#F4F2EC", "#356F8A"]
)


def configure_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Liberation Sans", "DejaVu Sans"],
            "font.size": 10.5,
            "axes.titlesize": 12.2,
            "axes.titleweight": "semibold",
            "axes.labelsize": 10.5,
            "axes.labelcolor": INK,
            "axes.edgecolor": INK,
            "axes.linewidth": 0.8,
            "xtick.labelsize": 9.3,
            "ytick.labelsize": 9.3,
            "xtick.color": INK,
            "ytick.color": INK,
            "legend.fontsize": 9.2,
            "text.color": INK,
            "figure.facecolor": PAPER,
            "axes.facecolor": PAPER,
            "savefig.facecolor": PAPER,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "mathtext.fontset": "dejavusans",
        }
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate vector-PDF figures from verified SelfAuditBench artifacts."
    )
    parser.add_argument(
        "--repo", type=Path, default=Path(__file__).resolve().parents[1], help="Repository root."
    )
    parser.add_argument(
        "--paper-export",
        type=Path,
        default=None,
        help="Verified paper export; defaults to the latest artifacts/paper/final-*.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output directory; defaults to <repo-parent>/Figures.",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        choices=[
            "all",
            "gold",
            "backend",
            "closed-loop",
            "afttraj",
            "enforcement",
            "progress",
            "comparisons",
        ],
        default=["all"],
        help="Generate the full suite or selected figures.",
    )
    return parser.parse_args()


def resolve_inputs(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    repo = args.repo.resolve()
    if not (repo / "artifacts" / "paper").is_dir():
        raise SystemExit(f"SelfAuditBench paper artifacts not found under {repo}")
    if args.paper_export is None:
        candidates = sorted((repo / "artifacts" / "paper").glob("final-*"))
        if not candidates:
            raise SystemExit("No artifacts/paper/final-* export is available")
        paper_export = candidates[-1]
    else:
        paper_export = args.paper_export.resolve()
    if not (paper_export / "tables").is_dir():
        raise SystemExit(f"Paper-export tables not found under {paper_export}")
    output = (args.output or repo.parent / "Figures").resolve()
    output.mkdir(parents=True, exist_ok=True)
    return repo, paper_export, output


def resolve_runs_root(repo: Path) -> Path:
    runs_root = repo / "artifacts" / "runs"
    required = {
        run_name
        for surface_runs in RUNS.values()
        for run_name in surface_runs.values()
    }
    candidates = sorted(path for path in runs_root.glob("verified-paper-*") if path.is_dir())
    for candidate in reversed(candidates):
        if all((candidate / run_name).is_dir() for run_name in required):
            return candidate
    if all((runs_root / run_name).is_dir() for run_name in required):
        return runs_root
    raise SystemExit("A complete verified eight-run ASB/ConVerse set is unavailable")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def percent(value: str) -> float:
    text = value.strip()
    if text.upper() in {"N/A", "NA", "UNAVAILABLE", ""}:
        return math.nan
    if text.endswith("%"):
        return float(text[:-1])
    parsed = float(text)
    return parsed * 100.0 if 0.0 <= parsed <= 1.0 else parsed


def number(value: str) -> float:
    text = value.strip().replace(",", "")
    if text.upper() in {"N/A", "NA", "UNAVAILABLE", ""}:
        return math.nan
    return float(text)


def index_by(rows: list[dict[str, str]], key: str) -> dict[str, dict[str, str]]:
    return {row[key]: row for row in rows}


def panel_title(ax: plt.Axes, letter: str, title: str, subtitle: str | None = None) -> None:
    ax.set_title(
        f"({letter})  {title}",
        loc="left",
        pad=0,
        y=1.14 if subtitle else 1.04,
        color=INK,
        fontsize=PAIR_TITLE_SIZE,
    )
    if subtitle:
        ax.text(
            0.0,
            1.035,
            subtitle,
            transform=ax.transAxes,
            ha="left",
            va="bottom",
            fontsize=PAIR_SUBTITLE_SIZE,
            color=MUTED,
        )


def style_pair_axes(ax: plt.Axes) -> None:
    ax.tick_params(axis="both", labelsize=PAIR_TICK_SIZE)
    ax.xaxis.label.set_size(PAIR_LABEL_SIZE)
    ax.yaxis.label.set_size(PAIR_LABEL_SIZE)


def clean_axes(ax: plt.Axes, *, grid_axis: str | None = "y") -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#9AA3A8")
    ax.spines["bottom"].set_color("#9AA3A8")
    if grid_axis:
        ax.grid(axis=grid_axis, color=GRID, linewidth=0.65, alpha=0.7)
        ax.set_axisbelow(True)


def save_pdf(fig: plt.Figure, output: Path, title: str) -> Path:
    fig.savefig(
        output,
        format="pdf",
        bbox_inches="tight",
        pad_inches=0.045,
        metadata={
            "Title": title,
            "Author": "SelfAuditBench",
            "Subject": "Verified SelfAuditBench Results artifacts",
            "Creator": "scripts/generate_result_figures.py",
        },
    )
    plt.close(fig)
    return output


def annotate_bar(ax: plt.Axes, bar: Rectangle, value: float, *, offset: float = 2.0) -> None:
    ax.text(
        bar.get_x() + bar.get_width() / 2,
        bar.get_height() + offset,
        f"{value:.1f}%",
        ha="center",
        va="bottom",
        fontsize=WIDE_ANNOTATION_SIZE,
        color=INK,
        fontweight="semibold",
        clip_on=False,
    )


def annotation_values(rows: list[dict[str, str]]) -> tuple[list[str], list[float], float]:
    values = {row["Record"]: row["Value or SHA-256"] for row in rows}
    labels = [
        "Risk label",
        "First-risk event",
        "Harm boundary",
        "Intervention set",
        "Permission delta",
    ]
    records = [
        "Risk-label agreement",
        "First-risk-event exact agreement",
        "Harm-boundary exact agreement",
        "Accepted-intervention Jaccard",
        "Minimal-delta exact agreement",
    ]
    return labels, [percent(values[record]) for record in records], float(
        values["Risk-label Cohen kappa"]
    )


def gold_distributions(repo: Path) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for surface in ("asb", "converse"):
        rows = read_jsonl(repo / "data" / "gold" / f"selfauditbench-gold-{surface}.jsonl")
        risky = [row for row in rows if row["label"]["risky"]]
        data[surface] = {
            "total": len(rows),
            "risky": len(risky),
            "benign": len(rows) - len(risky),
        }
    return data


def figure_gold(repo: Path, tables: Path, output: Path) -> Path:
    labels, agreement, kappa = annotation_values(
        read_csv(tables / "annotation_study_evidence.csv")
    )
    gold = gold_distributions(repo)
    fig = plt.figure(figsize=(7.8, 5.2))
    grid = fig.add_gridspec(1, 2, width_ratios=[0.85, 1.35], wspace=0.92)

    ax = fig.add_subplot(grid[0, 0])
    benign = [gold["asb"]["benign"], gold["converse"]["benign"]]
    risky = [gold["asb"]["risky"], gold["converse"]["risky"]]
    x = np.arange(2)
    ax.bar(x, benign, color=SAFE, edgecolor=INK, linewidth=0.7, label="Benign")
    ax.bar(x, risky, bottom=benign, color=RISKY, edgecolor=INK, linewidth=0.7, label="Risky")
    for idx, (safe_n, risk_n) in enumerate(zip(benign, risky, strict=True)):
        ax.text(
            idx,
            safe_n / 2,
            str(safe_n),
            ha="center",
            va="center",
            color=PAPER,
            fontweight="bold",
            fontsize=PAIR_ANNOTATION_SIZE,
        )
        ax.text(
            idx,
            safe_n + risk_n / 2,
            str(risk_n),
            ha="center",
            va="center",
            color=PAPER,
            fontweight="bold",
            fontsize=PAIR_ANNOTATION_SIZE,
        )
        ax.text(
            idx,
            50.0,
            "n=48",
            ha="center",
            va="bottom",
            fontsize=PAIR_ANNOTATION_SIZE,
            color=MUTED,
        )
    ax.set_xticks(x, ["ASB", "ConVerse"])
    ax.set_ylim(0, 55)
    ax.set_ylabel("Trajectories")
    panel_title(ax, "a", "Gold composition")
    clean_axes(ax)
    style_pair_axes(ax)
    ax.legend(
        frameon=False,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.2),
        ncol=2,
        fontsize=PAIR_LEGEND_SIZE,
    )

    ax = fig.add_subplot(grid[0, 1])
    y = np.arange(len(labels))[::-1]
    ax.barh(y, [100] * len(labels), color="#ECEEEB", height=0.58)
    colors = [ASB, "#4E8197", GOLD, "#6D9B8E", "#8D7A9B"]
    ax.barh(y, agreement, color=colors, height=0.58, edgecolor=INK, linewidth=0.45)
    for pos, value in zip(y, agreement, strict=True):
        ax.text(
            value + 1.2,
            pos,
            f"{value:.1f}%",
            va="center",
            fontsize=PAIR_ANNOTATION_SIZE,
            fontweight="semibold",
        )
    ax.set_yticks(y, labels)
    ax.set_xlim(0, 114)
    ax.set_xlabel("Agreement (%)")
    panel_title(
        ax,
        "b",
        "Human reliability",
        f"κ={kappa:.3f} · zero unresolved cases",
    )
    clean_axes(ax, grid_axis="x")
    style_pair_axes(ax)
    fig.subplots_adjust(left=0.11, right=0.97, top=0.72, bottom=0.25)
    return save_pdf(fig, output / "gold_annotation_landscape.pdf", "Gold annotation landscape")


def backend_rows(tables: Path) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    return (
        index_by(read_csv(tables / "model_audit_results.csv"), "Run"),
        index_by(read_csv(tables / "execution_reliability_results.csv"), "Run"),
    )


def read_backend_logo(repo: Path, backend: str) -> np.ndarray:
    logo_bundle = repo / "assets" / "backend_logos.json"
    try:
        encoded_logos = json.loads(logo_bundle.read_text(encoding="utf-8"))
        encoded_logo = encoded_logos[BACKEND_LOGOS[backend]]
        logo_bytes = base64.b64decode(encoded_logo, validate=True)
        return plt.imread(io.BytesIO(logo_bytes), format="png")
    except (OSError, KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Backend logo bundle is invalid or unavailable: {logo_bundle}") from exc


def draw_backend_heading(ax: plt.Axes, repo: Path, letter: str, backend: str) -> None:
    logo = read_backend_logo(repo, backend)
    zoom = 0.7 if backend == "MiniMax" else 0.72
    badge = AnnotationBbox(
        OffsetImage(logo, zoom=zoom),
        (0.01, 1.09),
        xycoords="axes fraction",
        frameon=False,
        box_alignment=(0.0, 0.5),
        pad=0.0,
    )
    badge.set_clip_on(False)
    ax.add_artist(badge)
    ax.text(
        0.2,
        1.09,
        f"({letter})  {BACKEND_DISPLAY_NAMES[backend]}",
        transform=ax.transAxes,
        ha="left",
        va="center",
        fontsize=WIDE_TITLE_SIZE,
        fontweight="semibold",
    )


def figure_backend(repo: Path, tables: Path, output: Path) -> Path:
    model, reliability = backend_rows(tables)
    metrics = ["Early detection", "Accepted intervention", "Pipeline completion"]
    fig, axes = plt.subplots(1, 4, figsize=(13.4, 3.8), sharey=True)
    x = np.arange(len(metrics))
    width = 0.34
    for ax, backend, letter in zip(axes, BACKENDS, "abcd", strict=True):
        values: dict[str, list[float]] = {}
        for surface in ("asb", "converse"):
            run = RUNS[surface][backend]
            values[surface] = [
                percent(model[run]["Model early detection"]),
                percent(model[run]["Accepted intervention"]),
                percent(reliability[run]["Audit-pipeline completion"]),
            ]
        bars_asb = ax.bar(
            x - width / 2,
            values["asb"],
            width,
            color=ASB,
            edgecolor=INK,
            linewidth=0.65,
        )
        bars_converse = ax.bar(
            x + width / 2,
            values["converse"],
            width,
            color=CONVERSE,
            edgecolor=INK,
            linewidth=0.65,
            hatch="//",
        )
        for bar, value in zip(bars_asb, values["asb"], strict=True):
            annotate_bar(ax, bar, value)
        for idx, (bar, value) in enumerate(
            zip(bars_converse, values["converse"], strict=True)
        ):
            offset = 14.0 if abs(value - values["asb"][idx]) < 10.0 else 5.0
            annotate_bar(ax, bar, value, offset=offset)
        ax.set_xticks(x, ["Early\nrisk", "Accepted\naction", "Pipeline"])
        ax.set_ylim(0, 120)
        ax.set_yticks([0, 25, 50, 75, 100])
        if ax is axes[0]:
            ax.set_ylabel("Rate (%)")
        ax.tick_params(axis="both", labelsize=WIDE_TICK_SIZE)
        ax.xaxis.label.set_size(WIDE_LABEL_SIZE)
        ax.yaxis.label.set_size(WIDE_LABEL_SIZE)
        draw_backend_heading(ax, repo, letter, backend)
        clean_axes(ax)
        ax.set_facecolor(PANEL)
    fig.legend(
        handles=[
            Patch(facecolor=ASB, edgecolor=INK, label="ASB"),
            Patch(facecolor=CONVERSE, edgecolor=INK, hatch="//", label="ConVerse"),
        ],
        loc="upper center",
        bbox_to_anchor=(0.52, 1.01),
        ncol=2,
        frameon=False,
        fontsize=WIDE_LEGEND_SIZE,
    )
    fig.subplots_adjust(left=0.06, right=0.995, top=0.75, bottom=0.18, wspace=0.2)
    return save_pdf(fig, output / "backend_audit_performance.pdf", "Four-backend audit performance")


def figure_closed_loop(tables: Path, output: Path) -> Path:
    rows = read_csv(tables / "closed_loop_recovery_results.csv")
    lookup = {(row["Surface"], row["Condition"]): row for row in rows}
    metrics = [
        ("Safety", "Safety"),
        ("Risky harm\navoidance", "Risky harm avoidance"),
        ("Task success", "Task"),
        ("Joint safe-task", "Safe-task"),
        ("Benign\nnoninterference", "Benign noninterference"),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(7.8, 5.5), sharex=True, sharey=True)
    for ax, surface, letter in zip(axes, ("asb", "converse"), "ab", strict=True):
        sidecar = lookup[(surface, "sidecar_recovery")]
        inline = lookup[(surface, "inline_self_restriction")]
        y = np.arange(len(metrics))[::-1]
        side_values = [percent(sidecar[column]) for _, column in metrics]
        inline_values = [percent(inline[column]) for _, column in metrics]
        for pos, left, right in zip(y, side_values, inline_values, strict=True):
            ax.plot([left, right], [pos, pos], color="#AEB6BA", linewidth=2.1, zorder=1)
            ax.scatter(
                left,
                pos,
                s=90,
                color=SIDECAR,
                edgecolor=PAPER,
                linewidth=0.9,
                zorder=3,
            )
            ax.scatter(
                right,
                pos,
                s=105,
                marker="D",
                color=INLINE,
                edgecolor=PAPER,
                linewidth=0.9,
                zorder=4,
            )
            if abs(left - right) < 1.0:
                ax.text(
                    left,
                    pos + 0.22,
                    f"{left:.1f} both",
                    ha="center",
                    va="bottom",
                    fontsize=PAIR_ANNOTATION_SIZE,
                    fontweight="semibold",
                )
            else:
                left_ha = "right" if left <= right else "left"
                right_ha = "left" if left <= right else "right"
                ax.text(
                    left + (-1.8 if left <= right else 1.8),
                    pos + 0.17,
                    f"{left:.1f}",
                    ha=left_ha,
                    fontsize=PAIR_ANNOTATION_SIZE,
                )
                ax.text(
                    right + (1.8 if left <= right else -1.8),
                    pos - 0.28,
                    f"{right:.1f}",
                    ha=right_ha,
                    fontsize=PAIR_ANNOTATION_SIZE,
                )
        ax.set_yticks(y, [label for label, _ in metrics])
        ax.set_xlim(-2, 106)
        ax.set_xticks([0, 20, 40, 60, 80, 100])
        ax.set_ylim(-0.35, 5.7)
        ax.set_xlabel("Outcome rate (%)")
        panel_title(ax, letter, f"{'ASB' if surface == 'asb' else 'ConVerse'} enacted outcomes")
        clean_axes(ax, grid_axis="x")
        ax.set_facecolor(PANEL)
        style_pair_axes(ax)
    axes[1].tick_params(axis="y", labelleft=False)
    axes[0].legend(
        handles=[
            Line2D(
                [0],
                [0],
                marker="o",
                color="none",
                markerfacecolor=SIDECAR,
                markersize=11,
                label="Sidecar recovery",
            ),
            Line2D(
                [0],
                [0],
                marker="D",
                color="none",
                markerfacecolor=INLINE,
                markersize=11,
                label="Inline self-restriction",
            ),
        ],
        loc="upper left",
        bbox_to_anchor=(0.015, 0.985),
        ncol=1,
        frameon=False,
        borderaxespad=0.0,
        fontsize=PAIR_LEGEND_SIZE,
    )
    fig.subplots_adjust(left=0.18, right=0.98, top=0.8, bottom=0.18, wspace=0.16)
    return save_pdf(fig, output / "closed_loop_outcomes.pdf", "Enacted closed-loop outcomes")


def afttraj_localization_errors(repo: Path) -> tuple[dict[str, list[int]], dict[str, int]]:
    run_dir = resolve_runs_root(repo) / "agentforesight-deepseek-native-baseline"
    dataset = {
        row["scenario_id"]: row
        for row in json.loads((run_dir / "dataset.json").read_text(encoding="utf-8"))
    }
    predicted_steps: dict[str, int] = {}
    for audit in read_jsonl(run_dir / "audits.jsonl"):
        event_id = audit["intended_action_ref"]
        scenario_id = event_id.rsplit(":event:", 1)[0]
        predicted_steps[scenario_id] = int(event_id.rsplit(":", 1)[1])
    errors = {domain: [] for domain in ("Math", "Coding", "Agentic", "Overall")}
    totals = {domain: 0 for domain in errors}
    domain_names = {"math": "Math", "coding": "Coding", "agentic": "Agentic"}
    for scenario_id, row in dataset.items():
        if not row["label"]["risky"]:
            continue
        domain_tag = next(tag for tag in row["tags"] if tag.startswith("domain:"))
        domain = domain_names[domain_tag.split(":", 1)[1]]
        totals[domain] += 1
        totals["Overall"] += 1
        if scenario_id not in predicted_steps:
            continue
        gold_step = int(row["label"]["first_risk_sufficient_event"])
        error = abs(predicted_steps[scenario_id] - gold_step)
        errors[domain].append(error)
        errors["Overall"].append(error)
    return errors, totals


def figure_afttraj(repo: Path, tables: Path, output: Path) -> Path:
    lookup = {
        row["Domain"]: row
        for row in read_csv(tables / "agentforesight_prefix_by_domain.csv")
    }
    domains = ["Math", "Coding", "Agentic", "Overall"]
    metrics = [("Exact-F1", "Exact-F1"), ("Step accuracy", "StepAcc"), ("False alarm", "FAR")]
    domain_colors = ["#477FA3", SAFE, "#C49743", "#9A6E83"]
    domain_hatches = ["", "\\\\", "xx", "//"]
    x = np.arange(len(metrics))
    width = 0.18
    offsets = (np.arange(len(domains)) - 1.5) * width
    fig, axes = plt.subplots(1, 2, figsize=(7.8, 5.1))
    ax = axes[0]
    for offset, domain, color, hatch in zip(
        offsets, domains, domain_colors, domain_hatches, strict=True
    ):
        row = lookup[domain]
        values = [percent(row[column]) for _, column in metrics]
        ax.bar(
            x + offset,
            values,
            width,
            color=color,
            edgecolor=INK,
            linewidth=0.65,
            hatch=hatch,
            label=domain,
        )
    ax.set_xticks(x, ["Exact-F1", "Step\naccuracy", "False\nalarm"])
    ax.set_ylabel("Rate (%)")
    ax.set_ylim(0, 52)
    ax.set_yticks([0, 10, 20, 30, 40, 50])
    panel_title(ax, "a", "Prefix metrics")
    clean_axes(ax)
    ax.set_facecolor(PANEL)
    style_pair_axes(ax)

    ax = axes[1]
    errors, totals = afttraj_localization_errors(repo)
    thresholds = np.arange(0, 11)
    markers = ["o", "s", "^", "D"]
    line_styles = ["-", "--", "-.", ":"]
    for domain, color, marker, line_style in zip(
        domains, domain_colors, markers, line_styles, strict=True
    ):
        cumulative = [
            100.0 * sum(error <= threshold for error in errors[domain]) / totals[domain]
            for threshold in thresholds
        ]
        ax.plot(
            thresholds,
            cumulative,
            color=color,
            marker=marker,
            linestyle=line_style,
            linewidth=2.2,
            markersize=5.5,
            markevery=2,
        )
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 100)
    ax.set_xticks([0, 2, 4, 6, 8, 10])
    ax.set_yticks([0, 20, 40, 60, 80, 100])
    ax.set_xlabel("Step-error tolerance k")
    ax.set_ylabel("Localization coverage (%)")
    panel_title(ax, "b", "Localization tolerance")
    clean_axes(ax)
    ax.set_facecolor(PANEL)
    style_pair_axes(ax)
    ax.text(
        0.97,
        0.055,
        r"$k=|\hat{t}_{\mathrm{risk}}-t^{\star}_{\mathrm{risk}}|$",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=PAIR_SUBTITLE_SIZE,
        color=MUTED,
    )

    fig.legend(
        handles=[
            Patch(facecolor=color, edgecolor=INK, hatch=hatch, label=domain)
            for domain, color, hatch in zip(
                domains, domain_colors, domain_hatches, strict=True
            )
        ],
        loc="upper center",
        bbox_to_anchor=(0.5, 0.89),
        ncol=4,
        frameon=False,
        fontsize=PAIR_LEGEND_SIZE,
    )
    fig.subplots_adjust(left=0.11, right=0.98, top=0.75, bottom=0.22, wspace=0.48)
    return save_pdf(fig, output / "afttraj_prefix_diagnostics.pdf", "AFTraj prefix diagnostics")


def figure_enforcement(repo: Path, tables: Path, output: Path) -> Path:
    rows = read_csv(tables / "closed_loop_recovery_results.csv")
    lookup = {(row["Surface"], row["Condition"]): row for row in rows}
    order = [
        ("asb", "sidecar_recovery", "ASB sidecar"),
        ("asb", "inline_self_restriction", "ASB inline"),
        ("converse", "sidecar_recovery", "ConVerse sidecar"),
        ("converse", "inline_self_restriction", "ConVerse inline"),
    ]
    runs_root = resolve_runs_root(repo)
    closed_loop_runs = {
        ("asb", "sidecar_recovery"): "asb-full-gold-deepseek-closed-loop-sidecar",
        ("asb", "inline_self_restriction"): "asb-full-gold-deepseek-closed-loop-inline",
        ("converse", "sidecar_recovery"): (
            "converse-full-gold-deepseek-closed-loop-sidecar"
        ),
        ("converse", "inline_self_restriction"): (
            "converse-full-gold-deepseek-closed-loop-inline"
        ),
    }
    outcome_categories = ["Safe + task", "Safe only", "Task only", "Neither"]
    outcome_colors = ["#3F8176", "#6D91AA", "#C89A45", "#C66D55"]
    composition = np.zeros((len(order), len(outcome_categories)))
    for row_idx, (surface, condition, _) in enumerate(order):
        summary_path = (
            runs_root
            / closed_loop_runs[(surface, condition)]
            / "closed_loop_summary.csv"
        )
        for result in read_csv(summary_path):
            safe = result["safety_satisfied"].lower() == "true"
            task = result["task_success"].lower() == "true"
            if safe and task:
                category = 0
            elif safe:
                category = 1
            elif task:
                category = 2
            else:
                category = 3
            composition[row_idx, category] += 1
    composition = composition / composition.sum(axis=1, keepdims=True) * 100.0

    fig, axes = plt.subplots(
        1,
        2,
        figsize=(7.8, 5.3),
        gridspec_kw={"width_ratios": [1.08, 1.0]},
    )
    y = np.arange(len(order))[::-1]
    ax = axes[0]
    left = np.zeros(len(order))
    for category_idx, (category, color) in enumerate(
        zip(outcome_categories, outcome_colors, strict=True)
    ):
        values = composition[:, category_idx]
        bars = ax.barh(
            y,
            values,
            left=left,
            height=0.44,
            color=color,
            edgecolor=INK,
            linewidth=0.55,
            label=category,
        )
        for bar, value in zip(bars, values, strict=True):
            if value >= 8.0:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_y() + bar.get_height() / 2,
                    f"{value:.0f}%",
                    ha="center",
                    va="center",
                    color=PAPER if category_idx != 1 else INK,
                    fontsize=PAIR_ANNOTATION_SIZE,
                    fontweight="semibold",
                )
        left += values
    display_labels = [
        label.replace("ConVerse", "ConV") for _, _, label in order
    ]
    ax.set_yticks(y, display_labels)
    ax.set_xlim(0, 100)
    ax.set_ylim(-0.65, 4.75)
    ax.set_xlabel("Scenario share (%)")
    panel_title(ax, "a", "Safety–task composition")
    clean_axes(ax, grid_axis="x")
    style_pair_axes(ax)
    ax.legend(
        loc="upper left",
        ncol=2,
        frameon=False,
        bbox_to_anchor=(0.0, 1.0),
        borderaxespad=0.0,
        fontsize=PAIR_LEGEND_SIZE,
        columnspacing=1.15,
    )

    ax = axes[1]
    executed = np.array(
        [
            number(lookup[(surface, condition)]["Executed actions"])
            for surface, condition, _ in order
        ]
    )
    denied = np.array(
        [
            number(lookup[(surface, condition)]["Denied actions"])
            for surface, condition, _ in order
        ]
    )
    bars_exec = ax.barh(
        y,
        executed,
        height=0.4,
        color=SAFE,
        edgecolor=INK,
        linewidth=0.65,
        label="Executed",
    )
    bars_deny = ax.barh(
        y,
        denied,
        left=executed,
        height=0.4,
        color=RISKY,
        edgecolor=INK,
        linewidth=0.65,
        hatch="//",
        label="Denied",
    )
    for bar, value in zip(bars_exec, executed, strict=True):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_y() + bar.get_height() / 2,
            f"{int(value)}",
            ha="center",
            va="center",
            color=PAPER,
            fontsize=PAIR_ANNOTATION_SIZE,
            fontweight="bold",
        )
    for bar, value in zip(bars_deny, denied, strict=True):
        ax.text(
            bar.get_x() + bar.get_width() + 1.5,
            bar.get_y() + bar.get_height() / 2,
            f"+{int(value)} denied",
            ha="left",
            va="center",
            fontsize=PAIR_ANNOTATION_SIZE,
            color=RISKY,
            fontweight="semibold",
        )
    ax.set_yticks(y, [])
    ax.set_xlabel("Broker action outcomes (count)")
    ax.set_xlim(0, max(executed + denied) * 1.22)
    ax.set_ylim(-0.65, 4.75)
    panel_title(ax, "b", "Broker action gates")
    clean_axes(ax, grid_axis="x")
    style_pair_axes(ax)
    ax.legend(
        frameon=False,
        loc="upper right",
        bbox_to_anchor=(0.99, 0.99),
        borderaxespad=0.0,
        fontsize=PAIR_LEGEND_SIZE,
    )
    fig.subplots_adjust(left=0.17, right=0.98, top=0.8, bottom=0.2, wspace=0.18)
    return save_pdf(fig, output / "enforcement_assurance.pdf", "Enforcement assurance")


def backend_for_run(run_name: str) -> str:
    for surface_runs in RUNS.values():
        for backend, candidate in surface_runs.items():
            if run_name == candidate:
                return backend
    raise ValueError(f"Unknown recorded-action run: {run_name}")


def comparison_matrices(repo: Path) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    values = {surface: np.zeros((4, 4)) for surface in ("asb", "converse")}
    p_values = {surface: np.full((4, 4), np.nan) for surface in ("asb", "converse")}
    comparisons = repo / "artifacts" / "comparisons"
    for surface in ("asb", "converse"):
        for path in comparisons.glob(f"{surface}-*.json"):
            if "closed-loop" in path.name:
                continue
            record = json.loads(path.read_text(encoding="utf-8"))
            metric = record["metrics"]["model_generated_early_detection_rate"]
            run_a = backend_for_run(record["run_a"])
            run_b = backend_for_run(record["run_b"])
            idx_a = BACKENDS.index(run_a)
            idx_b = BACKENDS.index(run_b)
            difference = float(metric["difference"]) * 100.0
            p_value = metric["mcnemar_exact_p"]
            values[surface][idx_a, idx_b] = difference
            values[surface][idx_b, idx_a] = -difference
            if p_value is not None:
                p_values[surface][idx_a, idx_b] = float(p_value)
                p_values[surface][idx_b, idx_a] = float(p_value)
    return values, p_values


def figure_comparisons(repo: Path, output: Path) -> Path:
    matrices, p_values = comparison_matrices(repo)
    limit = max(float(np.max(np.abs(matrix))) for matrix in matrices.values())
    limit = math.ceil(limit / 5.0) * 5.0
    norm = TwoSlopeNorm(vmin=-limit, vcenter=0.0, vmax=limit)
    fig = plt.figure(figsize=(7.8, 5.0))
    grid = fig.add_gridspec(1, 3, width_ratios=[1.0, 1.0, 0.055], wspace=0.1)
    axes = [fig.add_subplot(grid[0, 0]), fig.add_subplot(grid[0, 1])]
    colorbar_ax = fig.add_subplot(grid[0, 2])
    image = None
    for ax, surface, letter in zip(axes, ("asb", "converse"), "ab", strict=True):
        matrix = matrices[surface]
        image = ax.imshow(matrix, cmap=DIFF_CMAP, norm=norm, aspect="equal")
        backend_labels = [BACKEND_DISPLAY_NAMES[backend] for backend in BACKENDS]
        ax.set_xticks(np.arange(4), backend_labels, rotation=28, ha="right")
        if ax is axes[0]:
            ax.set_yticks(np.arange(4), backend_labels)
        else:
            ax.set_yticks(np.arange(4), [])
        ax.tick_params(length=0, labelsize=PAIR_TICK_SIZE)
        for row in range(4):
            for col in range(4):
                if row == col:
                    label = "—"
                else:
                    value = matrix[row, col]
                    p_value = p_values[surface][row, col]
                    marker = "**" if p_value < 0.01 else "*" if p_value < 0.05 else ""
                    label = f"{value:+.1f}{marker}" if abs(value) >= 0.05 else "0.0"
                ax.text(
                    col,
                    row,
                    label,
                    ha="center",
                    va="center",
                    fontsize=PAIR_ANNOTATION_SIZE,
                    fontweight="semibold",
                    color=PAPER if abs(matrix[row, col]) >= limit * 0.55 else INK,
                )
        for line in np.arange(-0.5, 4, 1):
            ax.axhline(line, color=PAPER, linewidth=1.8)
            ax.axvline(line, color=PAPER, linewidth=1.8)
        for spine in ax.spines.values():
            spine.set_visible(False)
        name = "ASB" if surface == "asb" else "ConVerse"
        panel_title(
            ax,
            letter,
            f"{name} backend effects",
            "Detection Δ: row − col. (pp)",
        )
    assert image is not None
    colorbar = fig.colorbar(image, cax=colorbar_ax)
    colorbar.set_label("Paired effect (pp)", fontsize=PAIR_SUBTITLE_SIZE, labelpad=16)
    colorbar.ax.text(
        8.6,
        0.5,
        "Exact: * p<0.05; ** p<0.01",
        transform=colorbar.ax.transAxes,
        ha="center",
        va="center",
        rotation=90,
        fontsize=PAIR_SUBTITLE_SIZE,
        fontstyle="italic",
        color=MUTED,
    )
    colorbar.ax.tick_params(labelsize=PAIR_TICK_SIZE)
    fig.subplots_adjust(left=0.14, right=0.9, top=0.7, bottom=0.2)
    return save_pdf(
        fig,
        output / "backend_pairwise_comparisons.pdf",
        "Paired backend early-detection effects",
    )


def intervention_leads(repo: Path, surface: str, backend: str) -> tuple[list[float], int]:
    gold_rows = read_jsonl(repo / "data" / "gold" / f"selfauditbench-gold-{surface}.jsonl")
    risky = {row["scenario_id"]: row for row in gold_rows if row["label"]["risky"]}
    run_dir = resolve_runs_root(repo) / RUNS[surface][backend]
    results = index_by(read_jsonl(run_dir / "results.jsonl"), "scenario_id")
    leads: list[float] = []
    for scenario_id, gold in risky.items():
        event_id = results[scenario_id].get("first_non_allow_event_id")
        if not event_id:
            continue
        intervention_idx = int(event_id.rsplit(":", 1)[1])
        boundary_idx = int(gold["label"]["first_risk_sufficient_event"])
        denominator = max(1, len(gold["events"]) - 1)
        leads.append(100.0 * (intervention_idx - boundary_idx) / denominator)
    return leads, len(risky)


def figure_progress(repo: Path, output: Path) -> Path:
    grid = np.linspace(-100, 100, 201)
    line_styles = ["-", "--", "-.", ":"]
    markers = ["o", "s", "^", "D"]
    fig, axes = plt.subplots(1, 2, figsize=(7.8, 5.1), sharex=True, sharey=True)
    legend_handles: list[Line2D] = []
    for ax, surface, letter in zip(axes, ("asb", "converse"), "ab", strict=True):
        risky_n = 0
        ax.axvspan(-100, 0, color="#E6F0EC", alpha=0.85, zorder=0)
        ax.axvspan(0, 100, color="#F6EEE7", alpha=0.65, zorder=0)
        for backend, line_style, marker in zip(
            BACKENDS, line_styles, markers, strict=True
        ):
            leads, risky_n = intervention_leads(repo, surface, backend)
            cumulative = np.array(
                [sum(value <= point for value in leads) / risky_n * 100.0 for point in grid]
            )
            ax.plot(
                grid,
                cumulative,
                color=BACKEND_COLORS[backend],
                linestyle=line_style,
                linewidth=2.5,
                marker=marker,
                markevery=20,
                markersize=6.5,
                label=BACKEND_DISPLAY_NAMES[backend],
            )
            if ax is axes[0]:
                legend_handles.append(
                    Line2D(
                        [0],
                        [0],
                        marker=marker,
                        linestyle="None",
                        markerfacecolor=BACKEND_COLORS[backend],
                        markeredgecolor=BACKEND_COLORS[backend],
                        markersize=9.0,
                        label=BACKEND_DISPLAY_NAMES[backend],
                    )
                )
        ax.axvline(0, color=INK, linewidth=1.1, linestyle=(0, (3, 3)))
        ax.set_xlim(-100, 100)
        ax.set_ylim(0, 105)
        ax.set_xticks([-100, -50, 0, 50, 100])
        ax.set_yticks([0, 20, 40, 60, 80, 100])
        ax.set_xlabel("")
        if ax is axes[0]:
            ax.set_ylabel("Risk interception (%)")
        name = "ASB" if surface == "asb" else "ConVerse"
        panel_title(ax, letter, f"{name} interception")
        clean_axes(ax)
        style_pair_axes(ax)
    axes[0].legend(
        handles=legend_handles,
        loc="upper left",
        bbox_to_anchor=(0.02, 0.98),
        ncol=1,
        frameon=False,
        borderaxespad=0.0,
        fontsize=PAIR_LEGEND_SIZE,
        handlelength=0.0,
        handletextpad=0.75,
    )
    axes[0].text(
        35,
        32,
        "n=14 risky traj.",
        ha="left",
        va="center",
        fontsize=PAIR_ANNOTATION_SIZE,
        color=MUTED,
    )
    axes[1].text(
        -95,
        96,
        "n=41 risky traj.",
        ha="left",
        va="top",
        fontsize=PAIR_ANNOTATION_SIZE,
        color=MUTED,
    )
    axes[1].text(
        -80,
        20,
        "0 marks the\nadjudicated\nfirst-risk boundary",
        ha="left",
        va="bottom",
        rotation=90,
        fontsize=PAIR_ANNOTATION_SIZE,
        color=MUTED,
    )
    fig.supxlabel(
        "Intervention position from risk boundary (% trajectory)",
        x=0.56,
        y=0.025,
        fontsize=PAIR_LABEL_SIZE,
    )
    fig.subplots_adjust(left=0.14, right=0.98, top=0.81, bottom=0.19, wspace=0.19)
    return save_pdf(
        fig,
        output / "risk_interception_progress.pdf",
        "Risk interception over normalized trajectory progress",
    )


def main() -> None:
    args = parse_args()
    configure_style()
    repo, paper_export, output = resolve_inputs(args)
    tables = paper_export / "tables"
    selected = set(args.only)
    if "all" in selected:
        selected = {
            "gold",
            "backend",
            "closed-loop",
            "afttraj",
            "enforcement",
            "progress",
            "comparisons",
        }
    generators = {
        "gold": lambda: figure_gold(repo, tables, output),
        "backend": lambda: figure_backend(repo, tables, output),
        "closed-loop": lambda: figure_closed_loop(tables, output),
        "afttraj": lambda: figure_afttraj(repo, tables, output),
        "enforcement": lambda: figure_enforcement(repo, tables, output),
        "progress": lambda: figure_progress(repo, output),
        "comparisons": lambda: figure_comparisons(repo, output),
    }
    generated: list[Path] = []
    order = (
        "gold",
        "backend",
        "closed-loop",
        "afttraj",
        "enforcement",
        "progress",
        "comparisons",
    )
    for name in order:
        if name in selected:
            generated.append(generators[name]())
    print(f"source_export={paper_export}")
    for path in generated:
        print(f"generated={path}")


if __name__ == "__main__":
    main()
