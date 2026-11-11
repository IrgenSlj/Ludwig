# reference/

Code kept from the design-harness era (tag `harness-era-v1`) because a planned module
starts from it. Not importable, not linted, not tested. Delete each file when the task
that uses it lands.

| File | Old path | Used by |
|---|---|---|
| `critic_base.py` | `critic/base.py` | `src/ludwig/model.py` — `Finding` and statuses (PLAN 1.1) |
| `toolkit_standards.py` | `toolkit/standards.py` | `src/ludwig/rules/packs.py` — cached YAML loading (PLAN 1.5) |
| `http_guards.py` | `webapp/server.py` (`token_ok`, `origin_ok`) | `src/ludwig/api` security tests (PLAN 5.1) |
| `agent_inference.py` | `agent/inference.py` | `src/ludwig/assist` — provider-neutral model calls (PLAN 5.5) |
| `agent_budget.py` | `agent/budget.py` | `src/ludwig/assist` — cost limits (PLAN 5.5) |
| `ci_old.yml` | `.github/workflows/ci.yml` | `.github/workflows/ci.yml` (PLAN 0.3) |
