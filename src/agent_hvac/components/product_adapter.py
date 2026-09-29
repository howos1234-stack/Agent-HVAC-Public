"""Adapters from production product records to deterministic calculation views."""

from __future__ import annotations

from agent_hvac.components.performance_map import (
    EnvelopeVertex,
    FixedCondition,
    MapAxis,
    MapOutput,
    MapPoint,
    OperatingEnvelope2D,
    PerformanceMapError,
    RegularGridMap,
)
from agent_hvac.schemas.components import (
    AutomaticSelectionStatus,
    AxisRole,
    OperatingEnvelope,
    PerformanceMap,
    PerformancePoint,
    ProductDataValue,
    ProductRecord,
)


def adapt_product_performance_map(
    product: ProductRecord,
    map_id: str,
) -> RegularGridMap:
    """Select one eligible production map by exact ID and build its SI calculation view."""
    performance_map = _select_performance_map(product, map_id)
    if performance_map.use_status.automatic_selection != AutomaticSelectionStatus.ELIGIBLE:
        raise PerformanceMapError(f"performance map {map_id!r} is not eligible for calculation")

    axes = tuple(sorted(performance_map.axes, key=lambda axis: axis.order))
    adapted_axes: list[MapAxis] = []
    for axis in axes:
        if axis.role != AxisRole.CANONICAL or axis.canonical_name is None:
            raise PerformanceMapError(
                f"performance map {map_id!r} contains a non-canonical calculation axis"
            )
        adapted_axes.append(
            MapAxis(
                name=axis.canonical_name.value,
                order=axis.order,
                unit=axis.canonical_unit,
                values=axis.canonical_values(),
            )
        )

    return RegularGridMap(
        map_id=performance_map.map_id,
        axes=tuple(adapted_axes),
        points=tuple(_adapt_point(point) for point in performance_map.points),
        fixed_conditions=tuple(
            _adapt_fixed_condition(condition) for condition in performance_map.fixed_conditions
        ),
        interpolation=performance_map.interpolation.value,
        extrapolation=performance_map.extrapolation,
        source_ids=(performance_map.source_id,),
        automatic_selection_eligible=True,
    )


def adapt_product_operating_envelope(
    product: ProductRecord,
    envelope_id: str,
) -> OperatingEnvelope2D:
    """Select one eligible production envelope by exact ID and build its SI polygon view."""
    envelope = _select_operating_envelope(product, envelope_id)
    if envelope.use_status.automatic_selection != AutomaticSelectionStatus.ELIGIBLE:
        raise PerformanceMapError(
            f"operating envelope {envelope_id!r} is not eligible for calculation"
        )
    x_axis, y_axis = envelope.axes
    if any(
        axis.role != AxisRole.CANONICAL or axis.canonical_name is None for axis in (x_axis, y_axis)
    ):
        raise PerformanceMapError(
            f"operating envelope {envelope_id!r} contains a non-canonical calculation axis"
        )
    assert x_axis.canonical_name is not None
    assert y_axis.canonical_name is not None

    vertices = tuple(
        EnvelopeVertex(
            x=vertex.coordinates[0].value_si.value,
            y=vertex.coordinates[1].value_si.value,
            source_ids=(vertex.source_id,),
        )
        for vertex in sorted(envelope.boundary_vertices, key=lambda item: item.vertex_order)
    )
    return OperatingEnvelope2D(
        envelope_id=envelope.envelope_id,
        x_axis_name=x_axis.canonical_name.value,
        y_axis_name=y_axis.canonical_name.value,
        x_unit=x_axis.canonical_unit,
        y_unit=y_axis.canonical_unit,
        vertices=vertices,
        boundary_inclusive=envelope.boundary_inclusive,
        fixed_conditions=tuple(
            _adapt_fixed_condition(condition) for condition in envelope.fixed_conditions
        ),
        source_ids=(envelope.source_id,),
    )


def _adapt_point(point: PerformancePoint) -> MapPoint:
    return MapPoint(
        coordinates=tuple(value.value_si.value for value in point.coordinates),
        outputs=tuple(
            MapOutput(
                name=output.canonical_name.value,
                value=output.value_si.value,
                unit=output.value_si.unit,
                source_id=output.source_id,
            )
            for output in point.outputs
        ),
        source_ids=(point.source_id,),
    )


def _adapt_fixed_condition(value: ProductDataValue) -> FixedCondition:
    return FixedCondition(
        name=value.canonical_name.value,
        value=value.value_si.value,
        unit=value.value_si.unit,
        source_id=value.source_id,
    )


def _select_performance_map(product: ProductRecord, map_id: str) -> PerformanceMap:
    for performance_map in product.performance_maps:
        if performance_map.map_id == map_id:
            return performance_map
    raise PerformanceMapError(f"product does not contain map {map_id!r}")


def _select_operating_envelope(
    product: ProductRecord,
    envelope_id: str,
) -> OperatingEnvelope:
    for envelope in product.operating_envelopes:
        if envelope.envelope_id == envelope_id:
            return envelope
    raise PerformanceMapError(f"product does not contain operating envelope {envelope_id!r}")
