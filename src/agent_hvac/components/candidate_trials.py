"""Run independent synthetic component trials without selecting or ranking products.

This WS-A helper preserves the existing component evaluators as the only source of
physical results. A rejected candidate has no result; it cannot inherit the output
or detailed provenance of a previously evaluated candidate.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from agent_hvac.components.compressor_map import (
    CompressorMapInput,
    CompressorMapResult,
    evaluate_compressor_map,
)
from agent_hvac.components.expansion_valve_map import (
    ExpansionValveMapInput,
    ExpansionValveMapResult,
    evaluate_expansion_valve_map,
)
from agent_hvac.components.heat_exchanger_rated_point import (
    HeatExchangerBoundaryInput,
    HeatExchangerRatedPointResult,
    HeatExchangerRatedPointSelection,
    evaluate_heat_exchanger_rated_point,
    select_heat_exchanger_rated_point,
)
from agent_hvac.properties.base import PropertyBackend
from agent_hvac.schemas.components import ProductRecord
from agent_hvac.utils.exceptions import HVACError


@dataclass(frozen=True)
class HeatExchangerTrialInput:
    """An exact rated-point selection and caller-owned P05 boundary conditions."""

    backend: PropertyBackend
    selection: HeatExchangerRatedPointSelection
    boundaries: HeatExchangerBoundaryInput


type ComponentTrialInput = CompressorMapInput | ExpansionValveMapInput | HeatExchangerTrialInput
type ComponentTrialResult = (
    CompressorMapResult | ExpansionValveMapResult | HeatExchangerRatedPointResult
)


@dataclass(frozen=True)
class ComponentCandidateTrial:
    """Caller identity for one trial; distinct IDs may use the same mock product."""

    candidate_id: str
    input: ComponentTrialInput


@dataclass(frozen=True)
class ComponentTrialOutcome:
    """A result or explicit failure, never both.

    ``selected_source_ids`` identify the requested parent records even if evaluation
    fails. On success, the typed ``result`` retains detailed value-level provenance.
    These identities are not a claim that a failed calculation used any data values.
    """

    candidate_id: str
    product_id: str
    record_id: str
    envelope_id: str | None
    is_mock: bool
    selected_source_ids: tuple[str, ...]
    status: Literal["EVALUATED", "REJECTED"]
    result: ComponentTrialResult | None
    failure_type: str | None
    failure_message: str | None


def evaluate_synthetic_component_trials(
    candidates: Sequence[ComponentCandidateTrial],
) -> tuple[ComponentTrialOutcome, ...]:
    """Evaluate each mock candidate independently, preserving order and failure.

    Only expected HVAC domain errors reject an individual candidate. Programming
    errors propagate. This function neither ranks candidates nor relaxes any model,
    envelope, fixed-condition, source or unit requirement.
    """
    identifiers = [candidate.candidate_id for candidate in candidates]
    if any(not identifier.strip() for identifier in identifiers):
        raise ValueError("component candidate IDs must be nonempty")
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("component candidate IDs must be unique")
    if any(not _product(candidate.input).is_mock for candidate in candidates):
        raise ValueError("synthetic component trials require mock ProductRecord inputs")

    outcomes: list[ComponentTrialOutcome] = []
    for candidate in candidates:
        product = _product(candidate.input)
        record_id, envelope_id, selected_sources = _selected_identity(candidate.input)
        try:
            result = _evaluate(candidate.input)
        except HVACError as exc:
            outcomes.append(
                ComponentTrialOutcome(
                    candidate_id=candidate.candidate_id,
                    product_id=product.product_id,
                    record_id=record_id,
                    envelope_id=envelope_id,
                    is_mock=product.is_mock,
                    selected_source_ids=selected_sources,
                    status="REJECTED",
                    result=None,
                    failure_type=type(exc).__name__,
                    failure_message=str(exc),
                )
            )
        else:
            outcomes.append(
                ComponentTrialOutcome(
                    candidate_id=candidate.candidate_id,
                    product_id=product.product_id,
                    record_id=record_id,
                    envelope_id=envelope_id,
                    is_mock=product.is_mock,
                    selected_source_ids=selected_sources,
                    status="EVALUATED",
                    result=result,
                    failure_type=None,
                    failure_message=None,
                )
            )
    return tuple(outcomes)


def _product(data: ComponentTrialInput) -> ProductRecord:
    if isinstance(data, HeatExchangerTrialInput):
        return data.selection.product
    return data.product


def _selected_identity(data: ComponentTrialInput) -> tuple[str, str | None, tuple[str, ...]]:
    product = _product(data)
    if isinstance(data, HeatExchangerTrialInput):
        record_id = data.selection.rated_point_id
        sources = tuple(
            point.source_id for point in product.rated_points if point.rated_point_id == record_id
        )
        return record_id, None, sources

    record_id = data.map_id
    envelope_id = data.envelope_id
    sources = tuple(
        performance_map.source_id
        for performance_map in product.performance_maps
        if performance_map.map_id == record_id
    ) + tuple(
        envelope.source_id
        for envelope in product.operating_envelopes
        if envelope.envelope_id == envelope_id
    )
    return record_id, envelope_id, sources


def _evaluate(data: ComponentTrialInput) -> ComponentTrialResult:
    if isinstance(data, CompressorMapInput):
        return evaluate_compressor_map(data)
    if isinstance(data, ExpansionValveMapInput):
        return evaluate_expansion_valve_map(data)
    rated_data = select_heat_exchanger_rated_point(data.selection)
    return evaluate_heat_exchanger_rated_point(data.backend, rated_data, data.boundaries)
