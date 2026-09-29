"""Synthetic validation for P06 interpolation and operating-envelope logic."""

from __future__ import annotations

import math
from itertools import product

import pytest

from agent_hvac.components.performance_map import (
    EnvelopeVertex,
    FixedCondition,
    MapAxis,
    MapOutput,
    MapPoint,
    OperatingEnvelope2D,
    PerformanceMapError,
    RegularGridMap,
    evaluate_regular_grid,
    require_envelope_contains,
)
from agent_hvac.utils.exceptions import ComponentEnvelopeError


def _grid(
    dimensions: int = 2,
    *,
    reverse_points: bool = False,
    fixed_conditions: tuple[FixedCondition, ...] = (),
) -> RegularGridMap:
    axes = tuple(
        MapAxis(name=f"x{index}", order=index, unit="Pa", values=(0.0, 1.0))
        for index in range(dimensions)
    )
    coordinates = list(product(*(axis.values for axis in axes)))
    if reverse_points:
        coordinates.reverse()
    points = tuple(
        MapPoint(
            coordinates=coordinate,
            outputs=(
                MapOutput(
                    name="affine",
                    value=3.0
                    + sum((index + 2.0) * value for index, value in enumerate(coordinate)),
                    unit="W",
                    source_id="source-output",
                ),
                MapOutput(
                    name="product",
                    value=7.0 + math.prod(1.0 + value for value in coordinate),
                    unit="kg/s",
                    source_id="source-flow",
                ),
            ),
        )
        for coordinate in coordinates
    )
    return RegularGridMap(
        map_id="synthetic-map",
        axes=axes,
        points=points,
        fixed_conditions=fixed_conditions,
        source_ids=("source-map",),
    )


def _envelope(
    vertices: tuple[tuple[float, float], ...] = ((0.0, 0.0), (4.0, 0.0), (3.0, 3.0), (0.0, 2.0)),
    *,
    boundary_inclusive: bool = True,
) -> OperatingEnvelope2D:
    return OperatingEnvelope2D(
        envelope_id="synthetic-envelope",
        x_axis_name="suction_pressure",
        y_axis_name="discharge_pressure",
        x_unit="Pa",
        y_unit="Pa",
        vertices=tuple(EnvelopeVertex(x=x, y=y) for x, y in vertices),
        boundary_inclusive=boundary_inclusive,
        source_ids=("source-envelope",),
    )


@pytest.mark.parametrize("dimensions", [1, 2, 3])
def test_multilinear_interpolation_matches_synthetic_functions(dimensions: int) -> None:
    query = {f"x{index}": 0.2 + index * 0.15 for index in range(dimensions)}

    result = evaluate_regular_grid(_grid(dimensions), query)

    expected_affine = 3.0 + sum((index + 2.0) * value for index, value in enumerate(query.values()))
    expected_product = 7.0 + math.prod(1.0 + value for value in query.values())
    assert result.outputs["affine"] == pytest.approx(expected_affine, rel=0.0, abs=1e-12)
    assert result.outputs["product"] == pytest.approx(expected_product, rel=0.0, abs=1e-12)
    assert result.output_units == {"affine": "W", "product": "kg/s"}
    assert result.output_source_ids == {
        "affine": ("source-output",),
        "product": ("source-flow",),
    }
    assert result.map_source_ids == ("source-map",)


def test_exact_node_returns_stored_values_and_point_order_does_not_matter() -> None:
    query = {"x0": 1.0, "x1": 0.0}
    normal = evaluate_regular_grid(_grid(), query)
    reversed_points = evaluate_regular_grid(_grid(reverse_points=True), query)

    assert normal == reversed_points
    assert normal.outputs["affine"] == 5.0
    assert normal.outputs["product"] == 9.0


def test_linear_interpolation_handles_finite_axis_span_that_overflows_float_subtraction() -> None:
    grid = RegularGridMap(
        map_id="wide-axis",
        interpolation="LINEAR",
        axes=(MapAxis(name="pressure", order=0, unit="Pa", values=(-1e308, 1e308)),),
        points=(
            MapPoint(
                coordinates=(-1e308,),
                outputs=(MapOutput("value", 10.0, "W", "source-low"),),
            ),
            MapPoint(
                coordinates=(1e308,),
                outputs=(MapOutput("value", 20.0, "W", "source-high"),),
            ),
        ),
    )

    result = evaluate_regular_grid(grid, {"pressure": 0.0})

    assert result.outputs["value"] == pytest.approx(15.0, rel=0.0, abs=0.0)


@pytest.mark.parametrize("query", [{"x0": -1e-12, "x1": 0.5}, {"x0": 0.5, "x1": 1.0001}])
def test_map_extrapolation_is_explicitly_rejected(query: dict[str, float]) -> None:
    with pytest.raises(ComponentEnvelopeError, match="extrapolation is forbidden"):
        evaluate_regular_grid(_grid(), query)


def test_fixed_conditions_require_exact_names_and_values() -> None:
    grid = _grid(
        fixed_conditions=(
            FixedCondition(
                name="suction_temperature",
                value=280.0,
                unit="K",
                source_id="source-fixed",
            ),
        )
    )

    evaluate_regular_grid(grid, {"x0": 0.5, "x1": 0.5}, {"suction_temperature": 280.0})
    with pytest.raises(PerformanceMapError, match="must be exactly"):
        evaluate_regular_grid(grid, {"x0": 0.5, "x1": 0.5})
    with pytest.raises(PerformanceMapError, match="does not exactly match"):
        evaluate_regular_grid(
            grid,
            {"x0": 0.5, "x1": 0.5},
            {"suction_temperature": 280.0 + 1e-12},
        )


def test_incomplete_duplicate_and_nonfinite_grid_data_are_rejected() -> None:
    grid = _grid()
    with pytest.raises(PerformanceMapError, match="complete Cartesian grid"):
        evaluate_regular_grid(
            RegularGridMap(**{**grid.__dict__, "points": grid.points[:-1]}),
            {"x0": 0.5, "x1": 0.5},
        )
    with pytest.raises(PerformanceMapError, match="coordinates must be unique"):
        evaluate_regular_grid(
            RegularGridMap(**{**grid.__dict__, "points": grid.points + (grid.points[0],)}),
            {"x0": 0.5, "x1": 0.5},
        )
    with pytest.raises(PerformanceMapError, match="must be finite"):
        evaluate_regular_grid(grid, {"x0": math.nan, "x1": 0.5})


def test_ineligible_or_non_forbidden_policy_is_rejected() -> None:
    grid = _grid()
    with pytest.raises(PerformanceMapError, match="ineligible"):
        evaluate_regular_grid(
            RegularGridMap(**{**grid.__dict__, "automatic_selection_eligible": False}),
            {"x0": 0.5, "x1": 0.5},
        )
    with pytest.raises(PerformanceMapError, match="FORBIDDEN"):
        evaluate_regular_grid(
            RegularGridMap(**{**grid.__dict__, "extrapolation": "LINEAR"}),
            {"x0": 0.5, "x1": 0.5},
        )


def test_axis_query_and_output_contract_mismatches_are_rejected() -> None:
    grid = _grid()
    bad_axes = (
        MapAxis(name="x0", order=0, unit="Pa", values=(0.0, 1.0)),
        MapAxis(name="x1", order=2, unit="Pa", values=(0.0, 1.0)),
    )
    with pytest.raises(PerformanceMapError, match="axis order"):
        evaluate_regular_grid(
            RegularGridMap(**{**grid.__dict__, "axes": bad_axes}),
            {"x0": 0.5, "x1": 0.5},
        )
    with pytest.raises(PerformanceMapError, match="query axes"):
        evaluate_regular_grid(grid, {"x0": 0.5})

    changed_output = MapPoint(
        coordinates=grid.points[-1].coordinates,
        outputs=(
            MapOutput(name="affine", value=1.0, unit="kW", source_id="wrong-source"),
            grid.points[-1].outputs[1],
        ),
    )
    with pytest.raises(PerformanceMapError, match="identical output names and units"):
        evaluate_regular_grid(
            RegularGridMap(**{**grid.__dict__, "points": grid.points[:-1] + (changed_output,)}),
            {"x0": 0.5, "x1": 0.5},
        )

    nonfinite_output = MapPoint(
        coordinates=grid.points[-1].coordinates,
        outputs=(
            MapOutput(
                name="affine",
                value=math.inf,
                unit="W",
                source_id="source-output",
            ),
            grid.points[-1].outputs[1],
        ),
    )
    with pytest.raises(PerformanceMapError, match="outputs must be finite"):
        evaluate_regular_grid(
            RegularGridMap(**{**grid.__dict__, "points": grid.points[:-1] + (nonfinite_output,)}),
            {"x0": 0.5, "x1": 0.5},
        )


def test_interpolation_preserves_all_contributing_point_sources() -> None:
    grid = _grid(dimensions=1)
    second_point = MapPoint(
        coordinates=grid.points[1].coordinates,
        outputs=tuple(
            MapOutput(
                name=output.name,
                value=output.value,
                unit=output.unit,
                source_id=f"{output.source_id}-second",
            )
            for output in grid.points[1].outputs
        ),
    )
    sourced_grid = RegularGridMap(**{**grid.__dict__, "points": (grid.points[0], second_point)})

    result = evaluate_regular_grid(sourced_grid, {"x0": 0.5})

    assert result.output_source_ids == {
        "affine": ("source-output", "source-output-second"),
        "product": ("source-flow", "source-flow-second"),
    }


def test_envelope_accepts_inside_and_inclusive_boundary_and_rejects_outside() -> None:
    envelope = _envelope()

    require_envelope_contains(envelope, 1.0, 1.0)
    require_envelope_contains(envelope, 2.0, 0.0)
    require_envelope_contains(envelope, 4.0, 0.0)
    require_envelope_contains(envelope, 3.5, 1.5)
    with pytest.raises(ComponentEnvelopeError, match="outside"):
        require_envelope_contains(envelope, 4.0, 2.0)


def test_exclusive_boundary_rejects_edges_and_vertices() -> None:
    envelope = _envelope(boundary_inclusive=False)

    with pytest.raises(ComponentEnvelopeError, match="excluded boundary"):
        require_envelope_contains(envelope, 2.0, 0.0)
    with pytest.raises(ComponentEnvelopeError, match="excluded boundary"):
        require_envelope_contains(envelope, 0.0, 0.0)


@pytest.mark.parametrize("shift", [(0.0, 0.0), (3e6, 9e6)])
def test_polygon_start_rotation_reverse_and_translation_are_equivalent(
    shift: tuple[float, float],
) -> None:
    vertices = ((0.0, 0.0), (4.0, 0.0), (3.0, 3.0), (0.0, 2.0))
    variants = (
        vertices,
        vertices[2:] + vertices[:2],
        tuple(reversed(vertices)),
    )
    for variant in variants:
        shifted = tuple((x + shift[0], y + shift[1]) for x, y in variant)
        envelope = _envelope(shifted)
        require_envelope_contains(envelope, 1.0 + shift[0], 1.0 + shift[1])
        require_envelope_contains(envelope, 2.0 + shift[0], 0.0 + shift[1])
        with pytest.raises(ComponentEnvelopeError, match="outside"):
            require_envelope_contains(envelope, 4.0 + shift[0], 2.0 + shift[1])


@pytest.mark.parametrize("shift", [(0.0, 0.0), (3e6, 9e6)])
def test_translated_triangle_preserves_outside_and_boundary_policy(
    shift: tuple[float, float],
) -> None:
    vertices = tuple((x + shift[0], y + shift[1]) for x, y in ((0.0, 0.0), (1.0, 1.0), (0.0, 2.0)))
    inclusive = _envelope(vertices)
    exclusive = _envelope(vertices, boundary_inclusive=False)

    with pytest.raises(ComponentEnvelopeError, match="outside"):
        require_envelope_contains(inclusive, 0.6 + shift[0], 0.5 + shift[1])
    require_envelope_contains(inclusive, 0.5 + shift[0], 0.5 + shift[1])
    with pytest.raises(ComponentEnvelopeError, match="excluded boundary"):
        require_envelope_contains(exclusive, 0.5 + shift[0], 0.5 + shift[1])


def test_self_intersecting_and_repeated_closure_polygons_are_rejected() -> None:
    with pytest.raises(PerformanceMapError, match="self-intersect"):
        require_envelope_contains(
            _envelope(((0.0, 0.0), (3.0, 3.0), (0.0, 3.0), (3.0, 0.0))),
            1.0,
            1.0,
        )
    with pytest.raises(PerformanceMapError, match="unique"):
        require_envelope_contains(
            _envelope(((0.0, 0.0), (3.0, 0.0), (0.0, 3.0), (0.0, 0.0))),
            1.0,
            1.0,
        )
