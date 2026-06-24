"""Ludwig local daemon (M0).

A thin FastAPI service that wraps the existing ``ludwig.py`` orchestrator loop and
persists projects / runs / artifacts to SQLite. Strangler-fig: this package imports
and drives ``ludwig.py`` unchanged — it does not reimplement the loop.
"""
