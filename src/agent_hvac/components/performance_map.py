"""Deterministic regular-grid interpolation and 2D operating-envelope checks."""

from __future__ import annotations

import math
from bisect import bisect_right
from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from itertools import pairwise, product
from types import MappingProxyType

from agent_hvac.utils.exceptions import ComponentEnvelopeError, HVACError


class PerformanceMapError(HVACError):
    """A performance map cannot be evaluated without guessing or extrapolating."""


@dataclass(frozen=True)
class MapAxis:
    """One canonical SI map axis in its approved order."""

    name: str
    order: int
    unit: str
    values: tuple[float, ...]


@dataclass(frozen=True)
class FixedCondition:
    """A canonical SI condition that must match the requested operating point exactly."""

    name: str
    value: float
    unit: str
    source_id: str


@dataclass(frozen=True)
class MapOutput:
    """One map output with its unit and value-level source reference."""

    name: str
    value: float
    unit: str
    source_id: str


@dataclass(frozen=True)
class MapPoint:
    """A complete coordinate and its outputs."""

    coordinates: tuple[float, ...]
    outputs: tuple[MapOutput, ...]
    source_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class RegularGridMap:
    """Calculation view of an approved, eligible regular-grid performance map."""

    map_id: str
    axes: tuple[MapAxis, ...]
    points: tuple[MapPoint, ...]
    fixed_conditions: tuple[FixedCondition, ...] = ()
    interpolation: str = "MULTILINEAR"
    extrapolation: str = "FORBIDDEN"
    source_ids: tuple[str, ...] = ()
    automatic_selection_eligible: bool = True


@dataclass(frozen=True)
class MapEvaluation:
    """Interpolated outputs that retain map, unit, and source identity."""

    map_id: str
    outputs: Mapping[str, float]
    output_units: Mapping[str, str]
    output_source_ids: Mapping[str, tuple[str, ...]]
    point_source_ids: tuple[str, ...]
    map_source_ids: tuple[str, ...]


@dataclass(frozen=True)
class EnvelopeVertex:
    """One ordered vertex in canonical SI coordinates."""

    x: float
    y: float
    source_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class OperatingEnvelope2D:
    """A simple two-axis polygon with an explicit boundary policy."""

    envelope_id: str
    x_axis_name: str
    y_axis_name: str
    x_unit: str
    y_unit: str
    vertices: tuple[EnvelopeVertex, ...]
    boundary_inclusive: bool
    fixed_conditions: tuple[FixedCondition, ...] = ()
    source_ids: tuple[str, ...] = ()


def evaluate_regular_grid(
    performance_map: RegularGridMap,
    query: Mapping[str, float],
    fixed_conditions: Mapping[str, float] | None = None,
) -> MapEvaluation:
    """Evaluate an eligible complete grid without extrapolation or implicit tolerance."""
    axes, point_lookup, output_units = _validated_grid(performance_map)
    _validate_fixed_conditions(performance_map.fixed_conditions, fixed_conditions or {})
    expected_names = {axis.name for axis in axes}
    if set(query) != expected_names:
        raise PerformanceMapError(
            f"map {performance_map.map_id!r} query axes must be exactly {sorted(expected_names)!r}"
        )
    query_values = tuple(query[axis.name] for axis in axes)
    if not all(math.isfinite(value) for value in query_values):
        raise PerformanceMapError("map query coordinates must be finite")

    exact_coordinate = tuple(
        axis.values[axis.values.index(value)] if value in axis.values else value
        for axis, value in zip(axes, query_values, strict=True)
    )
    exact_point = point_lookup.get(exact_coordinate)
    if exact_point is not None:
        values = {output.name: output.value for output in exact_point.outputs}
        sources: dict[str, tuple[str, ...]] = {
            output.name: (output.source_id,) for output in exact_point.outputs
        }
        return _result(
            performance_map,
            values,
            output_units,
            sources,
            exact_point.source_ids,
        )

    brackets = tuple(
        _bracket(axis, value, performance_map.map_id)
        for axis, value in zip(axes, query_values, strict=True)
    )
    values = {name: 0.0 for name in output_units}
    output_sources: dict[str, set[str]] = {name: set() for name in output_units}
    contributing_point_sources: set[str] = set()
    for corner_bits in product((0, 1), repeat=len(axes)):
        coordinate: list[float] = []
        weight = 1.0
        for bit, (lower, upper, fraction) in zip(corner_bits, brackets, strict=True):
            coordinate.append(upper if bit else lower)
            weight *= fraction if bit else 1.0 - fraction
        point = point_lookup[tuple(coordinate)]
        point_outputs = {output.name: output.value for output in point.outputs}
        point_output_sources = {output.name: output.source_id for output in point.outputs}
        for name in values:
            values[name] += weight * point_outputs[name]
            if weight > 0.0:
                output_sources[name].add(point_output_sources[name])
        if weight > 0.0:
            contributing_point_sources.update(point.source_ids)
    if not all(math.isfinite(value) for value in values.values()):
        raise PerformanceMapError("map interpolation produced a non-finite output")
    return _result(
        performance_map,
        values,
        output_units,
        {name: tuple(sorted(source_ids)) for name, source_ids in output_sources.items()},
        tuple(sorted(contributing_point_sources)),
    )


def require_envelope_contains(
    envelope: OperatingEnvelope2D,
    x: float,
    y: float,
    fixed_conditions: Mapping[str, float] | None = None,
) -> None:
    """Return normally only when a point satisfies the approved polygon and boundary policy."""
    _validate_envelope(envelope)
    _validate_fixed_conditions(envelope.fixed_conditions, fixed_conditions or {})
    if not math.isfinite(x) or not math.isfinite(y):
        raise ComponentEnvelopeError("operating-envelope query coordinates must be finite")
    point = EnvelopeVertex(x=x, y=y)
    on_boundary = any(
        _point_on_segment(point, start, end) for start, end in _polygon_edges(envelope.vertices)
    )
    if on_boundary:
        if envelope.boundary_inclusive:
            return
        raise ComponentEnvelopeError(
            f"point lies on the excluded boundary of envelope {envelope.envelope_id!r}"
        )

    inside = False
    for start, end in _polygon_edges(envelope.vertices):
        if (start.y > y) == (end.y > y):
            continue
        start_x = Fraction.from_float(start.x)
        start_y = Fraction.from_float(start.y)
        end_x = Fraction.from_float(end.x)
        end_y = Fraction.from_float(end.y)
        query_x = Fraction.from_float(x)
        query_y = Fraction.from_float(y)
        x_crossing = start_x + (query_y - start_y) * (end_x - start_x) / (end_y - start_y)
        if query_x < x_crossing:
            inside = not inside
    if not inside:
        raise ComponentEnvelopeError(
            f"point lies outside operating envelope {envelope.envelope_id!r}"
        )


def _validated_grid(
    performance_map: RegularGridMap,
) -> tuple[
    tuple[MapAxis, ...],
    dict[tuple[float, ...], MapPoint],
    dict[str, str],
]:
    if not performance_map.automatic_selection_eligible:
        raise PerformanceMapError("ineligible map cannot be used for automatic calculation")
    if performance_map.interpolation not in {"LINEAR", "MULTILINEAR"}:
        raise PerformanceMapError(f"unsupported interpolation {performance_map.interpolation!r}")
    if performance_map.interpolation == "LINEAR" and len(performance_map.axes) != 1:
        raise PerformanceMapError("LINEAR interpolation requires exactly one axis")
    if performance_map.extrapolation != "FORBIDDEN":
        raise PerformanceMapError("only FORBIDDEN extrapolation policy is supported")
    axes = tuple(sorted(performance_map.axes, key=lambda axis: axis.order))
    if not axes or tuple(axis.order for axis in axes) != tuple(range(len(axes))):
        raise PerformanceMapError("axis order must be contiguous and start at zero")
    if len({axis.name for axis in axes}) != len(axes):
        raise PerformanceMapError("axis names must be unique")
    for axis in axes:
        if len(axis.values) < 2:
            raise PerformanceMapError(f"axis {axis.name!r} must contain at least two values")
        if not all(math.isfinite(value) for value in axis.values):
            raise PerformanceMapError(f"axis {axis.name!r} values must be finite")
        if any(a >= b for a, b in pairwise(axis.values)):
            raise PerformanceMapError(f"axis {axis.name!r} values must be strictly increasing")

    point_lookup: dict[tuple[float, ...], MapPoint] = {}
    output_units: dict[str, str] | None = None
    for point in performance_map.points:
        if len(point.coordinates) != len(axes):
            raise PerformanceMapError("map point coordinate dimension does not match axis count")
        if not all(math.isfinite(value) for value in point.coordinates):
            raise PerformanceMapError("map point coordinates must be finite")
        if point.coordinates in point_lookup:
            raise PerformanceMapError("map point coordinates must be unique")
        if any(
            value not in axis.values for axis, value in zip(axes, point.coordinates, strict=True)
        ):
            raise PerformanceMapError("map point coordinate is not declared on its axis")
        names = [output.name for output in point.outputs]
        if not names or len(set(names)) != len(names):
            raise PerformanceMapError("map point output names must be nonempty and unique")
        if not all(math.isfinite(output.value) for output in point.outputs):
            raise PerformanceMapError("map point outputs must be finite")
        units = {output.name: output.unit for output in point.outputs}
        if output_units is None:
            output_units = units
        elif units != output_units:
            raise PerformanceMapError("all map points must have identical output names and units")
        point_lookup[point.coordinates] = point

    expected_coordinates = set(product(*(axis.values for axis in axes)))
    if set(point_lookup) != expected_coordinates:
        raise PerformanceMapError("map points must form a complete Cartesian grid")
    assert output_units is not None
    return axes, point_lookup, output_units


def _validate_fixed_conditions(
    expected: tuple[FixedCondition, ...],
    actual: Mapping[str, float],
) -> None:
    expected_by_name = {condition.name: condition for condition in expected}
    if len(expected_by_name) != len(expected):
        raise PerformanceMapError("fixed-condition names must be unique")
    if set(actual) != set(expected_by_name):
        raise PerformanceMapError(f"fixed conditions must be exactly {sorted(expected_by_name)!r}")
    for name, condition in expected_by_name.items():
        if not math.isfinite(condition.value) or not math.isfinite(actual[name]):
            raise PerformanceMapError("fixed-condition values must be finite")
        if actual[name] != condition.value:
            raise PerformanceMapError(
                f"fixed condition {name!r} does not exactly match the approved map condition"
            )


def _bracket(axis: MapAxis, value: float, map_id: str) -> tuple[float, float, float]:
    if value < axis.values[0] or value > axis.values[-1]:
        raise ComponentEnvelopeError(
            f"query for axis {axis.name!r} is outside map {map_id!r}; extrapolation is forbidden"
        )
    upper_index = bisect_right(axis.values, value)
    if upper_index == len(axis.values):
        upper_index -= 1
    lower_index = upper_index - 1
    lower = axis.values[lower_index]
    upper = axis.values[upper_index]
    exact_lower = Fraction.from_float(lower)
    exact_upper = Fraction.from_float(upper)
    exact_value = Fraction.from_float(value)
    fraction = float((exact_value - exact_lower) / (exact_upper - exact_lower))
    if not math.isfinite(fraction) or not 0.0 <= fraction <= 1.0:
        raise PerformanceMapError(
            f"map {map_id!r} cannot represent a stable interpolation fraction "
            f"for axis {axis.name!r}"
        )
    return lower, upper, fraction


def _result(
    performance_map: RegularGridMap,
    values: dict[str, float],
    output_units: Mapping[str, str],
    output_source_ids: Mapping[str, tuple[str, ...]],
    point_source_ids: tuple[str, ...],
) -> MapEvaluation:
    return MapEvaluation(
        map_id=performance_map.map_id,
        outputs=MappingProxyType(dict(values)),
        output_units=MappingProxyType(dict(output_units)),
        output_source_ids=MappingProxyType(dict(output_source_ids)),
        point_source_ids=point_source_ids,
        map_source_ids=performance_map.source_ids,
    )


def _validate_envelope(envelope: OperatingEnvelope2D) -> None:
    vertices = envelope.vertices
    if len(vertices) < 3:
        raise PerformanceMapError("operating envelope must contain at least three vertices")
    if not all(math.isfinite(value) for vertex in vertices for value in (vertex.x, vertex.y)):
        raise PerformanceMapError("operating-envelope vertices must be finite")
    if len(set(vertices)) != len(vertices):
        raise PerformanceMapError(
            "operating-envelope vertices must be unique and not repeat closure"
        )
    edges = tuple(_polygon_edges(vertices))
    for first_index, (a, b) in enumerate(edges):
        for second_index, (c, d) in enumerate(edges[first_index + 1 :], first_index + 1):
            adjacent = second_index == first_index + 1 or (
                first_index == 0 and second_index == len(edges) - 1
            )
            if not adjacent and _segments_intersect(a, b, c, d):
                raise PerformanceMapError("operating-envelope polygon must not self-intersect")

    signed_double_area = sum(
        (
            Fraction.from_float(start.x) * Fraction.from_float(end.y)
            - Fraction.from_float(end.x) * Fraction.from_float(start.y)
        )
        for start, end in edges
    )
    if signed_double_area == 0:
        raise PerformanceMapError("operating-envelope polygon must have nonzero area")


def _polygon_edges(
    vertices: tuple[EnvelopeVertex, ...],
) -> tuple[tuple[EnvelopeVertex, EnvelopeVertex], ...]:
    return tuple(zip(vertices, vertices[1:] + vertices[:1], strict=True))


def _point_on_segment(
    point: EnvelopeVertex,
    start: EnvelopeVertex,
    end: EnvelopeVertex,
) -> bool:
    cross = _exact_cross(start, end, point)
    if cross != 0:
        return False
    return min(start.x, end.x) <= point.x <= max(start.x, end.x) and min(
        start.y, end.y
    ) <= point.y <= max(start.y, end.y)


def _orientation(a: EnvelopeVertex, b: EnvelopeVertex, c: EnvelopeVertex) -> int:
    cross = _exact_cross(a, b, c)
    if cross == 0:
        return 0
    return 1 if cross > 0 else -1


def _exact_cross(a: EnvelopeVertex, b: EnvelopeVertex, c: EnvelopeVertex) -> Fraction:
    ax = Fraction.from_float(a.x)
    ay = Fraction.from_float(a.y)
    bx = Fraction.from_float(b.x)
    by = Fraction.from_float(b.y)
    cx = Fraction.from_float(c.x)
    cy = Fraction.from_float(c.y)
    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)


def _segments_intersect(
    a: EnvelopeVertex,
    b: EnvelopeVertex,
    c: EnvelopeVertex,
    d: EnvelopeVertex,
) -> bool:
    orientations = (
        _orientation(a, b, c),
        _orientation(a, b, d),
        _orientation(c, d, a),
        _orientation(c, d, b),
    )
    if orientations[0] != orientations[1] and orientations[2] != orientations[3]:
        return True
    return (
        (orientations[0] == 0 and _point_on_segment(c, a, b))
        or (orientations[1] == 0 and _point_on_segment(d, a, b))
        or (orientations[2] == 0 and _point_on_segment(a, c, d))
        or (orientations[3] == 0 and _point_on_segment(b, c, d))
    )
