# reference/

Code kept from the design-harness era (tag `harness-era-v1`) because a planned module
starts from it. Not importable, not linted, not tested. Delete each file when the task
that uses it lands.

| File | Old path | Used by |
|---|---|---|
| `toolkit_standards.py` | `toolkit/standards.py` | `src/ludwig/rules/packs.py` — cached YAML loading (PLAN 1.5) |
| `http_guards.py` | `webapp/server.py` (`token_ok`, `origin_ok`) | `src/ludwig/api` security tests (PLAN 5.1) |
| `agent_inference.py` | `agent/inference.py` | `src/ludwig/assist` — provider-neutral model calls (PLAN 5.5) |
| `agent_budget.py` | `agent/budget.py` | `src/ludwig/assist` — cost limits (PLAN 5.5) |
