# Repository Guidelines

## Mandatory Product Purpose

FinData democratizes professional financial intelligence by turning difficult public
data into clear, traceable, accessible knowledge. Every agent must preserve the brand's
**rebelde con rigor** principle: reduce cost, complexity, and access barriers without
reducing precision. **Datos públicos. Decisiones propias.**

For extraction and Excel work, preserve source, period, unit, context, and auditability;
never fabricate data or hide failures behind silent fallbacks. Outputs, warnings, CLI,
and GUI copy must be understandable without knowing the implementation. Read
`../CLAUDE.md` before changing behavior or output design.

## Project Structure & Module Organization
- `analisis_excel/`: core Python package for Excel generation, formulas, and utilities.
- `data/XBRL/{Anual,Trimestral,Total}`: input datasets (per company); outputs also stored under each company folder.
- `Products/` → consolidated Excel outputs; `Product_v1/` → final, analysis-ready workbooks.
- Test files live at repo root (`test_*.py`) and under `tests/`.
- CLI entrypoint: `cmf_cli.py` (interactive pipeline orchestration).

## Build, Test, and Development Commands
- Setup env: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`.
- Run CLI: `python cmf_cli.py` (recommended) or end-to-end: `bash run_all.sh --arelle-dir ~/Documents/Arelle --langs es,en`.
- Process XBRL only: `python batch_xbrl_to_excel.py --base-dir data/XBRL/Total --arelle-dir ~/Documents/Arelle --langs es en`.
- Generate analysis: `python run_products_analysis.py --input-dir Products --output-dir Product_v1 --frequency Total --langs es,en --workers 8`.
- Tests: if `pytest` is available, `pytest -q`; otherwise run a focused check: `python test_complete_system.py`.

## Coding Style & Naming Conventions
- Python, PEP 8, 4‑space indent. Use `snake_case` for modules/functions, `PascalCase` for classes.
- Keep functions small and typed where practical; prefer docstrings over inline comments.
- File names: scripts in root (`xbrl_to_excel.py`, `facts_enhancer.py`), package code in `analisis_excel/`.
- Outputs follow pattern like `Product_v1/Total/estados_<RUT>_*_<ES|EN>.xlsx`.

## Testing Guidelines
- Unit/integration tests are Python scripts (`test_*.py`). Aim to cover transformations in `analisis_excel/` and end‑to‑end flows.
- Add new tests alongside related modules; name functions `test_<behavior>`.
- Large tests may expect fixtures in `data/`—guard with existence checks to avoid brittle failures.

## Commit & Pull Request Guidelines
- Commits: present tense, concise summary + scope (e.g., `facts: ensure cash flow links match period`).
- PRs: include purpose, key changes, run instructions, and before/after examples; link issues when relevant.
- CI is not enforced; manually run local tests/CLI before requesting review.

## Security & Configuration Tips
- Arelle location defaults to `~/Documents/Arelle`. Common env vars: `CMF_LANGS`, `CMF_WORKERS`, `X2E_MIN_YEAR`, `X2E_MAX_YEAR`, `X2E_AUTO_TRIM_EMPTY_TAIL`, `CMF_ANALYSIS_COMBINED`, `X2E_COMBINED`.
- Do not commit large outputs or credentials (`.env` is present). Keep datasets under `data/` out of PRs unless minimal samples.
