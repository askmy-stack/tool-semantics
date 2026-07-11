# Contributing to Tool-Semantics

Thanks for helping make agent tool interfaces safer to evolve.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
pytest
```

## Before opening a pull request

```bash
ruff check .
ruff format --check .
mypy src
pytest --cov=tool_semantics
```

## Typing

The package ships a `py.typed` marker. Keep public APIs fully typed; `mypy` runs in strict mode on `src/`.

## Design-sensitive changes

Open a design issue first if you plan to change:

- the snapshot schema (`InterfaceSnapshot` / `ToolContract`)
- severity model or change codes ([docs/change-codes.md](docs/change-codes.md))
- behavioral contract formats
- provider-neutral runners or MCP live capture protocol

## Issue labels

| Label | Use |
| --- | --- |
| `good first issue` | Small, well-scoped starter tasks |
| `documentation` | Docs, examples, diagrams |
| `enhancement` | New capabilities |
| `bug` | Incorrect behavior |
| `tests` | Coverage and fixtures |
| `research` | Open-ended / experimental work |
| `help wanted` | Maintainers want collaboration |

## Commit style

Prefer short, imperative subjects focused on *why*:

- `detect enum value removals in parameter diffs`
- `add markdown compatibility report renderer`

## Code of conduct

Participation is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
