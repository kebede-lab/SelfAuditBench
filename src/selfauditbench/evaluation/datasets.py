"""Deterministic diagnostic dataset slices and eligibility summaries."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Literal

from selfauditbench.adapters.io import write_scenarios
from selfauditbench.core.models import LabelProvenance, Scenario

SurfaceName = Literal["asb", "converse", "agentforesight"]


def default_summary_path(output: Path) -> Path:
    return output.with_name(f"{output.stem}.dataset_summary.json")


def write_diagnostic_slice(
    scenarios: Sequence[Scenario],
    *,
    surface: SurfaceName,
    output: Path,
    summary_path: Path | None = None,
    limit: int = 50,
) -> tuple[int, Path]:
    selected, selection = build_diagnostic_slice(scenarios, surface=surface, limit=limit)
    count = write_scenarios(output, selected)
    summary = summarize_scenarios(
        selected,
        source_count=len(scenarios),
        surface=surface,
        output=output,
        selection=selection,
    )
    path = summary_path or default_summary_path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return count, path


def build_diagnostic_slice(
    scenarios: Sequence[Scenario],
    *,
    surface: SurfaceName,
    limit: int = 50,
) -> tuple[list[Scenario], dict[str, Any]]:
    ordered = sorted(scenarios, key=lambda scenario: scenario.scenario_id)
    if surface == "agentforesight":
        selected = _balanced_label_slice(
            ordered,
            safe_target=limit // 2,
            risky_target=limit - (limit // 2),
            strata_key=_agentforesight_domain,
        )
        return selected, {
            "strategy": "balanced_safe_unsafe_by_domain",
            "requested": limit,
            "safe_target": limit // 2,
            "unsafe_target": limit - (limit // 2),
        }
    if surface == "converse":
        controls = [scenario for scenario in ordered if _is_benign(scenario)]
        control_target = min(limit // 2, len(controls))
        risky_target = limit - control_target
        selected, paired_count = _converse_pair_slice(
            ordered,
            pair_target=limit // 2,
        )
        if len(selected) < limit:
            selected_ids = {scenario.scenario_id for scenario in selected}
            remaining = [
                scenario for scenario in ordered if scenario.scenario_id not in selected_ids
            ]
            selected.extend(
                _balanced_label_slice(
                    remaining,
                    safe_target=max(0, control_target - sum(_is_benign(item) for item in selected)),
                    risky_target=max(0, risky_target - sum(_is_risky(item) for item in selected)),
                    strata_key=_converse_stratum,
                )
            )
        selected = sorted(selected[:limit], key=lambda scenario: scenario.scenario_id)
        return selected, {
            "strategy": "best_effort_attack_control_by_domain_and_pressure",
            "requested": limit,
            "requested_attack_control_pairs": limit // 2,
            "selected_attack_control_pairs": paired_count,
            "available_controls": len(controls),
            "selected_controls": sum(_is_benign(scenario) for scenario in selected),
        }
    selected = _balanced_label_slice(
        ordered,
        safe_target=limit // 2,
        risky_target=limit - (limit // 2),
        strata_key=_asb_stratum,
    )
    return selected, {
        "strategy": "balanced_attack_control_by_attack_family",
        "requested": limit,
        "control_target": limit // 2,
        "attack_target": limit - (limit // 2),
    }


def summarize_scenarios(
    scenarios: Sequence[Scenario],
    *,
    source_count: int | None = None,
    surface: str | None = None,
    output: Path | None = None,
    selection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_counts = Counter(scenario.source_dataset for scenario in scenarios)
    label_counts = Counter(_label_bucket(scenario) for scenario in scenarios)
    strata = {
        "domain": Counter(_domain_tag(scenario) for scenario in scenarios),
        "task": Counter(_task_tag(scenario) for scenario in scenarios),
        "risk_or_attack": Counter(_risk_or_attack_tag(scenario) for scenario in scenarios),
        "source_dataset": source_counts,
    }
    eligibility = headline_eligibility(scenarios)
    return {
        "surface": surface,
        "output": output.as_posix() if output is not None else None,
        "source_count": source_count,
        "scenario_count": len(scenarios),
        "source_dataset_counts": dict(sorted(source_counts.items())),
        "risky_count": label_counts["risky"],
        "control_count": label_counts["benign"],
        "unlabeled_count": label_counts["unlabeled"],
        "weak_label_count": sum(scenario.weak_label for scenario in scenarios),
        "false_alarm_denominator_valid": eligibility["false_alarm_denominator_valid"],
        "headline_eligibility": eligibility,
        "strata_counts": {
            name: dict(sorted(counter.items())) for name, counter in strata.items()
        },
        "selection": selection or {},
    }


def headline_eligibility(scenarios: Sequence[Scenario]) -> dict[str, Any]:
    total = len(scenarios)
    weak = sum(scenario.weak_label for scenario in scenarios)
    recorded_action_labels = sum(
        _has_complete_recorded_action_label(scenario) for scenario in scenarios
    )
    labels = [scenario.label for scenario in scenarios if scenario.label is not None]
    benign = sum(label.risky is False for label in labels)
    source_datasets = {scenario.source_dataset for scenario in scenarios}
    human_adjudicated = sum(
        scenario.label_provenance == LabelProvenance.HUMAN_ADJUDICATED
        for scenario in scenarios
    )
    curated = sum(
        scenario.label_provenance == LabelProvenance.SOURCE_CURATED
        for scenario in scenarios
    )
    evidence_ids = {
        scenario.label_evidence_sha256
        for scenario in scenarios
        if scenario.label_evidence_sha256 is not None
    }
    unique_scenario_ids = len({scenario.scenario_id for scenario in scenarios}) == total
    unique_source_refs = len(
        {(scenario.source_dataset, scenario.source_ref.casefold()) for scenario in scenarios}
    ) == total
    complete_pairs = _complete_pair_count(scenarios)
    expected_pairs = total // 2 if total % 2 == 0 else -1
    pairs_valid = complete_pairs == expected_pairs
    surface_counts = Counter(scenario.source_dataset for scenario in scenarios)
    expected_gold_shape = (
        surface_counts == {"asb": 48}
        or surface_counts == {"converse": 48}
        or surface_counts == {"asb": 48, "converse": 48}
    )
    human_ready = (
        total > 0
        and weak == 0
        and recorded_action_labels == total
        and human_adjudicated == total
        and len(evidence_ids) == 1
        and unique_scenario_ids
        and unique_source_refs
        and pairs_valid
        and expected_gold_shape
    )
    prefix_ready = (
        total > 0
        and source_datasets == {"agentforesight"}
        and weak == 0
        and curated == total
        and unique_scenario_ids
    )
    if human_ready and source_datasets <= {"asb", "converse"}:
        status = "recorded_action_headline_eligible"
    elif prefix_ready:
        status = "prefix_reliability_only"
    else:
        status = "supplementary_exploratory"
    return {
        "status": status,
        "total": total,
        "weak_labels": weak,
        "recorded_action_labels_complete": recorded_action_labels,
        "human_adjudicated": human_adjudicated,
        "source_curated": curated,
        "shared_label_evidence": len(evidence_ids) == 1,
        "unique_scenario_ids": unique_scenario_ids,
        "unique_source_refs": unique_source_refs,
        "complete_pair_count": complete_pairs,
        "pairs_valid": pairs_valid,
        "expected_gold_shape": expected_gold_shape,
        "source_datasets": sorted(source_datasets),
        "false_alarm_denominator_valid": (
            status == "recorded_action_headline_eligible" and benign > 0
        ),
    }


def _balanced_label_slice(
    scenarios: Sequence[Scenario],
    *,
    safe_target: int,
    risky_target: int,
    strata_key: Callable[[Scenario], str],
) -> list[Scenario]:
    safe = [scenario for scenario in scenarios if _is_benign(scenario)]
    risky = [scenario for scenario in scenarios if _is_risky(scenario)]
    selected = _round_robin_by_stratum(safe, safe_target, strata_key)
    selected.extend(_round_robin_by_stratum(risky, risky_target, strata_key))
    if len(selected) < safe_target + risky_target:
        selected_ids = {scenario.scenario_id for scenario in selected}
        remaining = [scenario for scenario in scenarios if scenario.scenario_id not in selected_ids]
        selected.extend(
            _round_robin_by_stratum(
                remaining,
                safe_target + risky_target - len(selected),
                strata_key,
            )
        )
    return sorted(selected, key=lambda scenario: scenario.scenario_id)


def _round_robin_by_stratum(
    scenarios: Sequence[Scenario],
    limit: int,
    key: Callable[[Scenario], str],
) -> list[Scenario]:
    buckets: dict[str, list[Scenario]] = defaultdict(list)
    for scenario in scenarios:
        buckets[key(scenario)].append(scenario)
    selected: list[Scenario] = []
    while len(selected) < limit and any(buckets.values()):
        for name in sorted(buckets):
            if buckets[name] and len(selected) < limit:
                selected.append(buckets[name].pop(0))
    return selected


def _converse_pair_slice(
    scenarios: Sequence[Scenario],
    *,
    pair_target: int,
) -> tuple[list[Scenario], int]:
    pair_groups: dict[str, list[Scenario]] = defaultdict(list)
    for scenario in scenarios:
        if scenario.pair_id is not None:
            pair_groups[scenario.pair_id].append(scenario)
    pair_buckets: dict[str, list[tuple[Scenario, Scenario]]] = defaultdict(list)
    for group in pair_groups.values():
        benign = sorted(
            (scenario for scenario in group if _is_benign(scenario)),
            key=lambda scenario: scenario.scenario_id,
        )
        risky = sorted(
            (scenario for scenario in group if _is_risky(scenario)),
            key=lambda scenario: scenario.scenario_id,
        )
        if benign and risky:
            pair_buckets[_converse_stratum(risky[0])].append((benign[0], risky[0]))

    selected: list[Scenario] = []
    selected_pairs = 0
    while selected_pairs < pair_target and any(pair_buckets.values()):
        for name in sorted(pair_buckets):
            if pair_buckets[name] and selected_pairs < pair_target:
                selected_benign, selected_risky = pair_buckets[name].pop(0)
                selected.extend((selected_benign, selected_risky))
                selected_pairs += 1
    return selected, selected_pairs


def _has_complete_recorded_action_label(scenario: Scenario) -> bool:
    label = scenario.label
    if label is None:
        return False
    if not label.utility_expectation.strip():
        return False
    if not label.risky:
        return (
            label.first_risk_sufficient_event is None
            and label.harm_boundary_event is None
            and not label.accepted_interventions
            and not label.minimal_permission_deltas
        )
    return (
        label.first_risk_sufficient_event is not None
        and label.harm_boundary_event is not None
        and label.first_risk_sufficient_event <= label.harm_boundary_event
        and bool(label.accepted_interventions)
        and bool(label.minimal_permission_deltas)
    )


def _complete_pair_count(scenarios: Sequence[Scenario]) -> int:
    grouped: dict[str, list[Scenario]] = defaultdict(list)
    for scenario in scenarios:
        if scenario.pair_id is not None:
            grouped[scenario.pair_id].append(scenario)
    complete = 0
    for pair in grouped.values():
        roles = {
            tag.removeprefix("role:")
            for scenario in pair
            for tag in scenario.tags
            if tag.startswith("role:")
        }
        if len(pair) == 2 and roles == {"attack", "control"}:
            complete += 1
    return complete


def _is_risky(scenario: Scenario) -> bool:
    return bool(scenario.label and scenario.label.risky)


def _is_benign(scenario: Scenario) -> bool:
    return bool(scenario.label and not scenario.label.risky)


def _label_bucket(scenario: Scenario) -> str:
    if scenario.label is None:
        return "unlabeled"
    return "risky" if scenario.label.risky else "benign"


def _agentforesight_domain(scenario: Scenario) -> str:
    return _tag_value(scenario, "domain") or "unknown"


def _converse_stratum(scenario: Scenario) -> str:
    domain = _source_ref_part(scenario, 1) or _domain_tag(scenario)
    if "privacy" in scenario.tags:
        pressure = "privacy"
    elif "security" in scenario.tags:
        pressure = "security"
    else:
        pressure = "benign"
    return f"{domain}:{pressure}"


def _asb_stratum(scenario: Scenario) -> str:
    return _source_ref_part(scenario, 1) or _risk_or_attack_tag(scenario)


def _domain_tag(scenario: Scenario) -> str:
    return _tag_value(scenario, "domain") or _source_ref_part(scenario, 1) or "unknown"


def _task_tag(scenario: Scenario) -> str:
    for tag in scenario.tags:
        if tag.startswith("example-") or tag.startswith("persona"):
            return tag
    return _source_ref_part(scenario, 2) or "unknown"


def _risk_or_attack_tag(scenario: Scenario) -> str:
    if not _is_risky(scenario):
        return "control"
    for tag in scenario.tags:
        if tag in {"privacy", "security"} or tag.startswith("unsafe-source:"):
            return tag
    return _source_ref_part(scenario, 1) or "risky"


def _tag_value(scenario: Scenario, prefix: str) -> str | None:
    needle = f"{prefix}:"
    for tag in scenario.tags:
        if tag.startswith(needle):
            return tag.removeprefix(needle)
    return None


def _source_ref_part(scenario: Scenario, index: int) -> str | None:
    parts = scenario.source_ref.replace("\\", "/").split("/")
    if len(parts) > index:
        return parts[index]
    return None
