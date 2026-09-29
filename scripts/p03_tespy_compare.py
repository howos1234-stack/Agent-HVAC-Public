"""Run the predefined P03 R744 comparison and print a machine-readable report."""

import json
from importlib.metadata import version

from agent_hvac.physics.cycle import BaselineCycleInputs
from agent_hvac.solvers.tespy_reference import run_p03_cross_validation
from agent_hvac.utils.units import MassFlow, Pressure, Temperature


def main() -> int:
    inputs = BaselineCycleInputs(
        fluid="R744",
        evaporator_pressure=Pressure(value=3_000_000.0, unit="Pa"),
        high_side_pressure=Pressure(value=9_000_000.0, unit="Pa"),
        compressor_inlet_temperature=Temperature(value=280.0, unit="K"),
        heat_rejection_outlet_temperature=Temperature(value=310.0, unit="K"),
        refrigerant_mass_flow=MassFlow(value=0.1, unit="kg/s"),
        compressor_isentropic_efficiency=0.8,
    )
    report = run_p03_cross_validation(inputs)
    payload = {
        "versions": {"tespy": version("tespy"), "coolprop": version("coolprop")},
        "all_within_tolerance": report.all_within_tolerance,
        "max_relative_error": report.max_relative_error,
        "metrics": {
            name: {
                "p02": metric.p02_value,
                "tespy": metric.tespy_value,
                "absolute_error": metric.absolute_error,
                "relative_error": metric.relative_error,
                "allowed_error": metric.allowed_error,
                "within_tolerance": metric.within_tolerance,
            }
            for name, metric in report.metrics.items()
        },
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if report.all_within_tolerance else 1


if __name__ == "__main__":
    raise SystemExit(main())
