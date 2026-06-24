"""Ludwig core — engine/sensor-agnostic contracts and the prompt stack (M4).

The loop is the product; the engine (``ToolAdapter``) and the evaluator (``Sensor``)
are pluggable behind the protocols in ``core.contracts``. This package wraps the
existing ``ludwig.py`` functionality behind those contracts so a new engine or sensor
is a contained task (BRIEF.md §4). The production multi-candidate loop still lives in
``ludwig.run``; ``core.orchestrator.run_via_contracts`` is the contract-driven path.
"""
