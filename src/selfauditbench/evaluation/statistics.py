"""Deterministic uncertainty estimates and paired run comparisons."""

from __future__ import annotations

import json
import math
import random
from pathlib import Path
from statistics import NormalDist
from typing import Any

from selfauditbench.core.models import Scenario, ScenarioResult
from selfauditbench.evaluation.evidence import metric_evidence_class
from selfauditbench.evaluation.metrics import scenario_binary_outcomes
from selfauditbench.storage.artifacts import load_jsonl, verify_integrity_manifest

DEFAULT_CONFIDENCE = 0.95
DEFAULT_BOOTSTRAP_SAMPLES = 2000


def wilson_interval(
    numerator: int,
    denominator: int,
    *,
    confidence: float = DEFAULT_CONFIDENCE,
) -> dict[str, int | float | None]:
    if denominator <= 0:
        return {
            "confidence": confidence,
            "lower": None,
            "upper": None,
            "numerator": numerator,
            "denominator": denominator,
        }
    z = NormalDist().inv_cdf(0.5 + confidence / 2)
    proportion = numerator / denominator
    z_squared = z * z
    scale = 1 + z_squared / denominator
    center = (proportion + z_squared / (2 * denominator)) / scale
    margin = (
        z
        * math.sqrt(
            proportion * (1 - proportion) / denominator
            + z_squared / (4 * denominator * denominator)
        )
        / scale
    )
    return {
        "confidence": confidence,
        "lower": max(0.0, center - margin),
        "upper": min(1.0, center + margin),
        "numerator": numerator,
        "denominator": denominator,
    }


def ratio_confidence_intervals(
    metrics: dict[str, Any],
    *,
    confidence: float = DEFAULT_CONFIDENCE,
) -> dict[str, dict[str, int | float | None]]:
    intervals: dict[str, dict[str, int | float | None]] = {}
    for name, value in metrics.items():
        if _is_ratio(value):
            intervals[name] = wilson_interval(
                int(value["numerator"]),
                int(value["denominator"]),
                confidence=confidence,
            )
    reliability = metrics.get("execution_reliability", {})
    if isinstance(reliability, dict):
        for name, value in reliability.items():
            if _is_ratio(value):
                intervals[name] = wilson_interval(
                    int(value["numerator"]),
                    int(value["denominator"]),
                    confidence=confidence,
                )
    closed_loop = metrics.get("closed_loop_recovery", {})
    if isinstance(closed_loop, dict):
        for name, value in closed_loop.items():
            if _is_ratio(value):
                intervals[f"closed_loop_recovery.{name}"] = wilson_interval(
                    int(value["numerator"]),
                    int(value["denominator"]),
                    confidence=confidence,
                )
    return dict(sorted(intervals.items()))


def compare_run_directories(
    run_a: Path,
    run_b: Path,
    *,
    bootstrap_samples: int = DEFAULT_BOOTSTRAP_SAMPLES,
    seed: int = 7,
    confidence: float = DEFAULT_CONFIDENCE,
    allow_treatment_difference: bool = False,
) -> dict[str, Any]:
    if bootstrap_samples < 1:
        raise ValueError("bootstrap_samples must be positive")

    integrity_a = verify_integrity_manifest(run_a)
    integrity_b = verify_integrity_manifest(run_b)
    _require_verified_integrity(run_a, integrity_a)
    _require_verified_integrity(run_b, integrity_b)

    manifest_a = _read_json(run_a / "manifest.json")
    manifest_b = _read_json(run_b / "manifest.json")
    contract_hash_a = manifest_a.get("evaluation_contract_hash")
    contract_hash_b = manifest_b.get("evaluation_contract_hash")
    if not _is_nonempty_string(contract_hash_a) or not _is_nonempty_string(
        contract_hash_b
    ):
        raise ValueError(
            "paired comparison requires recorded evaluation_contract_hash values"
        )
    comparison_hash: str | None = None
    if allow_treatment_difference:
        comparison_hash_a = manifest_a.get("comparison_contract_hash")
        comparison_hash_b = manifest_b.get("comparison_contract_hash")
        if not _is_nonempty_string(comparison_hash_a) or not _is_nonempty_string(
            comparison_hash_b
        ):
            raise ValueError(
                "treatment comparison requires recorded comparison_contract_hash values"
            )
        if comparison_hash_a != comparison_hash_b:
            raise ValueError(
                "treatment comparison requires identical comparison_contract_hash values"
            )
        comparison_hash = str(comparison_hash_a)
    elif contract_hash_a != contract_hash_b:
        raise ValueError(
            "paired comparison requires identical evaluation_contract_hash values"
        )
    hash_a = manifest_a.get("dataset_hash")
    hash_b = manifest_b.get("dataset_hash")
    if not hash_a or not hash_b:
        raise ValueError("paired comparison requires recorded dataset hashes")
    if hash_a != hash_b:
        raise ValueError("paired comparison requires identical dataset hashes")

    scenarios_a = _load_scenarios(run_a / "dataset.json")
    scenarios_b = _load_scenarios(run_b / "dataset.json")
    if set(scenarios_a) != set(scenarios_b):
        raise ValueError("paired comparison requires identical scenario ID sets")
    scenario_ids = sorted(scenarios_a)
    if not scenario_ids:
        raise ValueError("paired comparison requires a nonempty dataset")
    results_a = _load_results(run_a / "results.jsonl")
    results_b = _load_results(run_b / "results.jsonl")
    expected = set(scenario_ids)
    if set(results_a) != expected or set(results_b) != expected:
        raise ValueError(
            "paired comparison requires one result per identical dataset scenario"
        )
    shared = scenario_ids

    outcomes_a = {
        scenario_id: scenario_binary_outcomes(results_a[scenario_id], scenarios_a[scenario_id])
        for scenario_id in shared
    }
    outcomes_b = {
        scenario_id: scenario_binary_outcomes(results_b[scenario_id], scenarios_b[scenario_id])
        for scenario_id in shared
    }
    metric_names = sorted(
        set().union(*(set(outcomes_a[scenario_id]) for scenario_id in shared))
    )
    comparisons: dict[str, Any] = {}
    for metric_index, metric in enumerate(metric_names):
        eligible_ids = [
            scenario_id
            for scenario_id in shared
            if outcomes_a[scenario_id].get(metric) is not None
            and outcomes_b[scenario_id].get(metric) is not None
        ]
        pairs = [
            (bool(outcomes_a[scenario_id][metric]), bool(outcomes_b[scenario_id][metric]))
            for scenario_id in eligible_ids
        ]
        if not pairs:
            continue
        comparisons[metric] = _paired_binary_summary(
            pairs,
            bootstrap_samples=bootstrap_samples,
            seed=seed + metric_index,
            confidence=confidence,
            cluster_ids=[
                scenarios_a[scenario_id].pair_id or scenario_id
                for scenario_id in eligible_ids
            ],
        )
        comparisons[metric]["evidence_class"] = metric_evidence_class(metric)

    return {
        "run_a": str(manifest_a.get("run_id") or run_a.name),
        "run_b": str(manifest_b.get("run_id") or run_b.name),
        "dataset_hash": hash_a or hash_b,
        "evaluation_contract_hash": contract_hash_a,
        "evaluation_contract_hashes": {
            "run_a": contract_hash_a,
            "run_b": contract_hash_b,
        },
        "comparison_contract_hash": comparison_hash,
        "comparison_mode": (
            "paired_treatment_ablation"
            if allow_treatment_difference
            else "paired_identical_contract"
        ),
        "treatments": {
            "run_a": manifest_a.get("treatment") or {},
            "run_b": manifest_b.get("treatment") or {},
        },
        "integrity": {
            "run_a": {
                "status": integrity_a["status"],
                "root_digest": integrity_a.get("root_digest"),
            },
            "run_b": {
                "status": integrity_b["status"],
                "root_digest": integrity_b.get("root_digest"),
            },
        },
        "shared_scenarios": len(shared),
        "surfaces": sorted(
            {scenarios_a[scenario_id].source_dataset for scenario_id in shared}
        ),
        "pooled_claim_use": (
            "surface_specific"
            if len({scenarios_a[item].source_dataset for item in shared}) == 1
            else "descriptive_only"
        ),
        "bootstrap_samples": bootstrap_samples,
        "bootstrap_seed": seed,
        "confidence": confidence,
        "difference_direction": "run_a_minus_run_b",
        "metrics": comparisons,
    }


def write_paired_comparison(
    output: Path,
    comparison: dict[str, Any],
) -> tuple[Path, Path]:
    output.parent.mkdir(parents=True, exist_ok=True)
    json_path = output.with_suffix(".json")
    markdown_path = output.with_suffix(".md")
    json_path.write_text(
        json.dumps(comparison, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_comparison_markdown(comparison), encoding="utf-8")
    return json_path, markdown_path


def _paired_binary_summary(
    pairs: list[tuple[bool, bool]],
    *,
    bootstrap_samples: int,
    seed: int,
    confidence: float,
    cluster_ids: list[str] | None = None,
) -> dict[str, int | float | None]:
    n = len(pairs)
    a_values = [int(a) for a, _ in pairs]
    b_values = [int(b) for _, b in pairs]
    differences = [a - b for a, b in zip(a_values, b_values, strict=True)]
    difference = sum(differences) / n
    clusters: dict[str, list[int]] = {}
    identifiers = cluster_ids or [str(index) for index in range(n)]
    if len(identifiers) != n:
        raise ValueError("cluster IDs must align with paired outcomes")
    for identifier, value in zip(identifiers, differences, strict=True):
        clusters.setdefault(identifier, []).append(value)
    cluster_names = sorted(clusters)
    rng = random.Random(seed)
    bootstrap_values: list[float] = []
    for _ in range(bootstrap_samples):
        sampled = [
            clusters[cluster_names[rng.randrange(len(cluster_names))]]
            for _ in cluster_names
        ]
        flattened = [value for cluster in sampled for value in cluster]
        bootstrap_values.append(sum(flattened) / len(flattened))
    bootstrap = sorted(bootstrap_values)
    alpha = 1 - confidence
    lower = _percentile(bootstrap, alpha / 2)
    upper = _percentile(bootstrap, 1 - alpha / 2)
    a_only = sum(a and not b for a, b in pairs)
    b_only = sum(b and not a for a, b in pairs)
    return {
        "n": n,
        "clusters": len(cluster_names),
        "run_a_rate": sum(a_values) / n,
        "run_b_rate": sum(b_values) / n,
        "difference": difference,
        "ci_lower": lower,
        "ci_upper": upper,
        "discordant_a_only": a_only,
        "discordant_b_only": b_only,
        "mcnemar_exact_p": _mcnemar_exact_p(a_only, b_only),
    }


def _mcnemar_exact_p(a_only: int, b_only: int) -> float | None:
    discordant = a_only + b_only
    if discordant == 0:
        return None
    log_probabilities = [
        math.lgamma(discordant + 1)
        - math.lgamma(index + 1)
        - math.lgamma(discordant - index + 1)
        - discordant * math.log(2)
        for index in range(min(a_only, b_only) + 1)
    ]
    maximum = max(log_probabilities)
    tail = math.exp(maximum) * math.fsum(
        math.exp(value - maximum) for value in log_probabilities
    )
    return float(min(1.0, 2 * tail))


def _percentile(values: list[float], probability: float) -> float:
    if not values:
        raise ValueError("percentile requires values")
    position = probability * (len(values) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    weight = position - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def _comparison_markdown(comparison: dict[str, Any]) -> str:
    lines = [
        "# SelfAuditBench Paired Run Comparison",
        "",
        f"- Run A: `{comparison['run_a']}`",
        f"- Run B: `{comparison['run_b']}`",
        f"- Shared scenarios: {comparison['shared_scenarios']}",
        f"- Dataset hash: `{comparison.get('dataset_hash')}`",
        (
            "- Evaluation-contract hashes: "
            f"A=`{comparison.get('evaluation_contract_hashes', {}).get('run_a')}`, "
            f"B=`{comparison.get('evaluation_contract_hashes', {}).get('run_b')}`"
        ),
        f"- Comparison mode: `{comparison.get('comparison_mode')}`",
        (
            "- Comparison-contract hash: "
            f"`{comparison.get('comparison_contract_hash')}`"
        ),
        (
            "- Run integrity: "
            f"A=`{comparison.get('integrity', {}).get('run_a', {}).get('status')}`, "
            f"B=`{comparison.get('integrity', {}).get('run_b', {}).get('status')}`"
        ),
        f"- Bootstrap samples: {comparison['bootstrap_samples']}",
        f"- Difference direction: `{comparison['difference_direction']}`",
        "",
        (
            "| Metric | Evidence class | n | Clusters | Run A | Run B | "
            "Difference | 95% CI | McNemar p |"
        ),
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |",
    ]
    for metric, value in comparison["metrics"].items():
        p_value = value["mcnemar_exact_p"]
        lines.append(
            f"| `{metric}` | `{value['evidence_class']}` | {value['n']} | "
            f"{value['clusters']} | "
            f"{value['run_a_rate']:.4f} | {value['run_b_rate']:.4f} | "
            f"{value['difference']:.4f} | "
            f"[{value['ci_lower']:.4f}, {value['ci_upper']:.4f}] | "
            f"{'N/A' if p_value is None else f'{p_value:.4g}'} |"
        )
    lines.extend(
        [
            "",
            "Bootstrap intervals resample restored attack-control pair clusters and are "
            "deterministic under the recorded seed. McNemar's exact test uses only "
            "discordant scenario outcomes and does not replace effect-size reporting.",
            "",
        ]
    )
    return "\n".join(lines)


def _load_scenarios(path: Path) -> dict[str, Scenario]:
    values = json.loads(path.read_text(encoding="utf-8"))
    scenarios: dict[str, Scenario] = {}
    for item in values:
        scenario = Scenario.model_validate(item)
        if scenario.scenario_id in scenarios:
            raise ValueError(
                f"duplicate scenario_id in comparison dataset: {scenario.scenario_id}"
            )
        scenarios[scenario.scenario_id] = scenario
    return scenarios


def _load_results(path: Path) -> dict[str, ScenarioResult]:
    results: dict[str, ScenarioResult] = {}
    for item in load_jsonl(path):
        result = ScenarioResult.model_validate(item)
        if result.scenario_id in results:
            raise ValueError(
                f"duplicate scenario_id in comparison results: {result.scenario_id}"
            )
        results[result.scenario_id] = result
    return results


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object at {path}")
    return value


def _require_verified_integrity(
    run_dir: Path,
    result: dict[str, Any],
) -> None:
    if result.get("status") == "verified" and result.get("verified") is True:
        return
    errors = result.get("errors")
    detail = (
        "; ".join(str(item) for item in errors)
        if isinstance(errors, list) and errors
        else "verification did not succeed"
    )
    raise ValueError(
        f"paired comparison requires verified integrity for {run_dir} "
        f"(status={result.get('status', 'unknown')}): {detail}"
    )


def _is_nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_ratio(value: object) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("numerator"), int)
        and isinstance(value.get("denominator"), int)
    )
