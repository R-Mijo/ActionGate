# Start ActionGate on Windows

Use Python 3.11 or newer. Download the current source, extract it, and open a terminal in the directory containing `README.md`, `pyproject.toml`, `actiongate/` and `tests/`. This guide uses the public Python installation; do not copy paths from another person's computer.

```powershell
python --version
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install .
python -m unittest discover -s tests -v
python -m actiongate demo
python -m actiongate action-demo
```

The installed command is `actiongate`. The Python import is `actiongate`. Both installed commands and `python -m` must run from the current environment. The demos use synthetic fixtures, make no model calls and do not perform real business actions.

## Prepare an evaluation

```powershell
python -m actiongate prepare --directory results/pilot --repeats 3 --seed 20261029
python -m actiongate --help
```

Preparation creates prompts, source snapshots and a manifest. It does not call a model or prove accuracy. Use unique output directories, preserve the raw results and follow [the evaluation protocol](VALIDATION_PROTOCOL.md). Generated studies now use `anchor-synthetic-study-0.2.2` and `full_anchor_verifier_jobs`. Prepare a fresh study after updating; do not relabel or mix earlier study artifacts.

## Review the implementation

Read [`actiongate/core.py`](../actiongate/core.py), [the methodology](METHODOLOGY.md) and [workflow integration](APPLY_TO_YOUR_WORKFLOW.md). The required evidence, semantic checks and reviewer identity come from a trusted integration. A released recommendation does not grant permission for a payment or another business action.

## Troubleshooting

- If `python` opens the Microsoft Store or is unavailable, install/select a working Python 3.11+ interpreter from [python.org](https://www.python.org/downloads/).
- If importing `actiongate` fails, activate the environment and run `python -m pip install .` from the repository root.
- For package updates, build/install from clean source so generated build files cannot carry an earlier package tree.
- Model adapters, authenticated approvals, production persistence and validated business benefits remain separate integration/evaluation work.

Version prepared: 0.3.2. Repository history and historical license notices are preserved.
