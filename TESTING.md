# Detailed Testing Guide

## Test Layers

## 1) Functional auth tests

Covered in `test_main.py`:
- contextual risk transitions (medium -> low -> medium -> high)
- machine blocked IP handling
- confirmation gate for sandbox execution

Run:

```bash
uv run pytest -q test_main.py
```

## 2) Stress + extensibility tests

Covered in `tests/test_stress_and_extensibility.py`:
- parallel first-login load simulation
- action-level scope enforcement
- custom action registration path
- unknown action rejection

Run:

```bash
uv run pytest -q tests/test_stress_and_extensibility.py
```

## 3) Full suite

```bash
uv run pytest -q
```

## 4) Manual integration checklist

1. Start web + MCP services.
2. Register machine with role `agent`.
3. Login and obtain token.
4. Open Agent Playground and test:
   - web search only
   - calculator + db combo
   - ollama prompt
   - sandbox code with and without confirmation checkbox
5. Verify action registry endpoint from UI.

## 5) Stress test tuning suggestions

- Increase `user_count` and `max_workers` in `tests/test_stress_and_extensibility.py`.
- Add staggered randomized IP/UA combinations to model real traffic.
- Add repeated login loops for low-risk steady-state performance.
- For long-running load, use external runners (k6/Locust) and keep pytest stress tests lightweight.

## 6) Expansion testing pattern

When adding a new table/microservice/action:

1. Register action via `register_agent_action(...)`
2. Add dedicated scope
3. Add one positive test (valid scope + expected output)
4. Add one negative test (missing scope/invalid payload)
5. Add concurrency test if action can be burst-invoked
