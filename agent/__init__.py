"""agent — the compiler driver: provider-blind inference + the generate→verify→repair loop."""
from agent.inference import infer, provider_name

__all__ = ["infer", "provider_name"]
