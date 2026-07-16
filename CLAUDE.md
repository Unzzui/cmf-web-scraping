# cmf-web-scraping

Pipeline de datos de **FindataChile**. El repo hermano `~/Proyectos/FinDataChile` es la
web + BD (Next.js + Supabase); los dos se tocan.

## Antes de trabajar: leé el ADR

Este proyecto tiene un **Architecture Decision Record** en el grafo de codebase-memory con
las decisiones y los gotchas que no se deducen del código. Leelo al empezar:

```
manage_adr(project="home-unzzui-Proyectos-cmf-web-scraping", mode="get")
```

Cubre: los dos pipelines separados (IFRS vs bancos), el subsistema `src/banks/` (API REST
de la CMF), la descarga XBRL HTTP vs Selenium, el fallback Consolidado→Individual, la
identidad de cuenta por QName, los **dos motores de ratios que deben cuadrar**, que el
**upsert nunca purga**, la etapa UPLOAD 3A→3B y los gotchas de Arelle.

Mantenelo vivo: si tomamos una decisión arquitectónica o descubrimos un gotcha no obvio,
actualizá el ADR con `manage_adr(mode="update")`.

## Exploración de código

Usá las tools de **codebase-memory-mcp** primero (`search_graph`, `trace_path`,
`get_code_snippet`, `get_architecture`). El índice está al día; si dudás, corré
`detect_changes` y re-indexá con `index_repository`.

## Reglas que muerden

- **Supabase es PRODUCCIÓN.** El default es `--supabase-dry-run`. No pases
  `--supabase-live` sin que Diego lo pida explícitamente.
- **No quites el guardia `_verificar_facts_no_vacio()`** de `batch_xbrl_to_excel.py`:
  Arelle exporta CSV vacío con exit 0 y eso ya causó huecos en 74 Excel.
- **No quites el `DELETE FROM financial_ratios`** de `save_ratios_all_periods()`.
- Todo cambio en una fórmula de ratio del Excel hay que **replicarlo en el motor de
  Postgres** (`FinDataChile/scripts/ratio_calculator_postgresql.py`), y viceversa.
- Un ratio que no cuadra: **revisá el `updated_at` de la fila antes de culpar a la fórmula.**

## Convenciones

- Commits y comentarios **en español**, formato `tipo(scope): descripción`.
- Scripts de ingesta: idempotentes y con `--dry-run`.
- Los artefactos (`Product_v1/`, `Products/`, `data/`, `out_*/`) van en `.gitignore`.
