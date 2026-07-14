🎯 Contexto crítico

Sistema de conversión 100% basado en facts (sin fuzzy). La construcción de cada hoja (Balance, Resultados, Flujo) se hace solo con lo que existe en facts\_\*.csv/out_consolidated, respetando los headers de rol ([210000], [310000], [510000]) y sin inventar celdas.
Se eliminaron fuentes paralelas/inglesas y el mapeo difuso; los filtros evitan “notas” y categorías para que no se propaguen valores a cuentas que no deben.

🏗️ Arquitectura del sistema
Archivos clave

xbrl_to_excel.py — script principal.

(Opcional) facts_enhancer.py — mejoras conservadoras; si no está, se opera en modo estricto.

Entrada:

facts*<stem>\_es.csv, presentation*<stem>\_es.csv

out_consolidated_YYYY-YYYY/ (carpeta de trabajo)

Salida:

estados\_<stem>\_es.xlsx

...\_flujo_debug.csv (debug)

debug_facts_normalized.csv (debug)

Filosofía

Facts-first: nada se trae si no existe en facts.

Matching exacto por etiqueta (y por qname si está disponible).

Estrictamente español.

Separación por roles: seccionamiento duro entre estados.

Rendimiento: pandas vectorizado, merges y agregaciones; sin bucles costosos.

📊 Flujo de datos

/data/XBRL/Total/<RUT>_<EMPRESA>/
└── out_consolidated_<AAAAMM–AAAAMM>/
├── facts*<stem>\_es.csv
├── presentation*<stem>_es.csv
└── estados_<stem>\_es.xlsx (salida)
Carga → load_inputs()

Normalización → normalize_facts()

Árbol de presentación → restructure_presentation_to_single_column() + build_tree_and_order()

Selección por estado → select_role_tree() + filter_facts_by_statement()

Estructura base → build_complete_statement_structure() (taxonomía + orden estable)

Pegado estricto de valores → fill_values_from_facts_strict()

(Opcional) apply_facts_enhancements()

Etiqueta de períodos y trimming → \_period_labels_from_dates(), \_period_sort_key()

(Flujo) add_cash_beginning_period()

Excel (formatos, agrupaciones, filtros)

🔧 Componentes y responsabilidades

1. normalize_facts(facts_raw, lang='es')

Detecta columnas de fecha por patrón ^\d{4}-\d{2}-\d{2}$ (no depende de dtypes).

Normaliza encabezados de fecha a YYYY-MM-DD; coalesce de columnas duplicadas.

Filtra notas/ruido: conserva

headers de rol [210000|310000|510000]

líneas no iniciadas por [ (cuentas reales)

excluye bloques de “Notas” u otros headers fuera de estados.

Mantiene columnas mínimas: Label (+ qname si existe) + fechas.

Guarda debug_facts_normalized.csv con X2E_DEBUG=1.

⚠️ Evita ambigüedades de NA usando pd.isna() primero.

2. restructure_presentation_to_single_column() → build_tree_and_order()

Reestructura presentation\_\*.csv a una sola columna Cuenta (roles + cuentas).

Ignora columnas auxiliares (Pref. Label, Type, References).

Mantiene etiquetas [sinopsis] como categorías visuales, no numéricas.

build_tree_and_order() genera filas con roleUri, Label, presLabel, depth, order.

3. select_role_tree(p_tree, kind)

Filtra el árbol por tipo de estado (BALANCE/RESULTADOS/FLUJO) vía guess_role_kind() y ordena por (order, depth).

4. filter_facts_by_statement(facts, statement_kind)

Corta el bloque de facts entre header objetivo y el siguiente header.

Mantiene:

filas con algún dato en fechas,

header del estado,

pseudo-categorías [sinopsis|abstract|resumen] (solo estructurales).

Usa grupos no capturantes en regex para evitar warnings:

r'\[(?:sinopsis|abstract|resumen)\]' 5) build_complete_statement_structure(statement_kind, lang, date_columns, presentation_tree, facts_df)

Carga mapeo base desde taxonomía ilustrada (ES).

Refuerza con orden real del presentation.csv para el rol actual, pero solo incluye:

cuentas con datos en facts del estado,

categorías [sinopsis] (para estructura visual).

Selecciona rol primario por estado (210000, 310000/320000, 510000/520000), con fallback simple.

Siempre inserta un header explícito para el rol elegido.

6. strip_foreign_role_segments(df, expected_role)

Corta segmentos completos cuyo encabezado [XXXXXX] no sea el rol esperado, hasta el siguiente header.

Evita que cuentas de notas (p.ej. [851100] Nota - …) o de otros estados contaminen el actual.

7. fill_values_from_facts_strict(structure, facts_for_statement, date_columns, statement_kind, debug)

Matching exacto:

clave 1: qname (si existe en facts y estructura),

clave 2: Label/Cuenta con espacios normalizados (sin fuzzy).

Une por Label exacto; agrega por \_rid:

0 valores → NaN,

> 1 valores distintos → NaN (ambiguo),

exactamente 1 → se usa.

Nunca escribe en categorías ([xxxxxx], [sinopsis], etc.).

Resultado: no se “llenan” cuentas sin datos del período, ni se mezclan contextos.

8. Etiquetado de períodos y orden

\_period_labels_from_dates() convierte YYYY-MM-DD a:

Balance (instant): YYYY / YYYYQn (según mes),

Resultados/Flujo (duration): mismo esquema por fin de período.

\_period_sort_key() impone orden natural (por año y Qn).

Ajustes:

X2E_DECEMBER_AS_YEAR=1: preferir YYYY sobre YYYYQ4.

X2E_COMBINED=1: mantener años + trimestres (outline en Excel).

X2E_KEEP_ONLY_QUARTERS=1 + X2E_MAX_QUARTERS: recorte iterface.

Auto-trim cola vacía: si X2E_AUTO_TRIM_EMPTY_TAIL=1, elimina años al final con menos de X2E_MIN_NONEMPTY_PER_YEAR celdas no vacías (suma de hojas).

9. (Solo FLUJO) add_cash_beginning_period(df)

Inserta “Efectivo y equivalentes al efectivo al principio del periodo” justo antes de la fila de “… al final del periodo”.

Valor = “final del periodo” del período anterior (shift a la derecha).

Convierte strings con comas a numérico seguro, deja NaN si no es convertible.

10. Escritura Excel

Motor preferido: xlsxwriter (fallback: openpyxl).

Estilo corporativo, títulos, subtítulos, headers, alternancia de filas, totales.

Números en miles (/1000) con formatos positivos/negativos.

Categorías (headers de rol y [sinopsis]) se escriben sin números (celdas vacías).

Para X2E_COMBINED=1: agrupación (outline) de columnas Q1..Q4 por año.

⚙️ Variables de entorno

X2E_DEBUG=1 → logs detallados + archivos debug.

Fechas / períodos

X2E_KEEP_ALL_DATES=1 → no recortar fechas en normalización.

X2E_DECEMBER_AS_YEAR=1 → diciembre como YYYY.

X2E_COMBINED=1 → años + trimestres visibles y agrupados.

X2E_KEEP_ONLY_QUARTERS=1 + X2E_MAX_QUARTERS=12 → interfaz trimestral compacta.

X2E_MIN_YEAR, X2E_MAX_YEAR → ventana dura de años.

X2E_AUTO_TRIM_EMPTY_TAIL=1, X2E_MIN_NONEMPTY_PER_YEAR=5.

Facts Enhancer

Si facts_enhancer.py no está: “🔒 MODO ESTRICTO (no-op)”.

✅ Garantías funcionales

Nada de fuzzy; solo coincidencia exacta.

No se copian valores a categorías ni a headers.

Aislamiento por rol: strip_foreign_role_segments() garantiza que notas como
[851100] Nota - Estado de flujos de efectivo y sus cuentas no entren al estado.

Valores ambiguos (múltiples contextos distintos) → se descartan (NaN).

Cuentas sin dato en facts → permanecen vacías (o se omiten al final según hoja).

🧪 Señales de depuración

DEBUG normalize_facts: fechas detectadas, shape final, sample de labels.

DEBUG: Filtrado {ESTADO}: filas totales y con datos.

DEBUG fill_values_from_facts_strict: celdas rellenadas / candidatas.

Mensajes especiales al detectar/proteger la cuenta conflictiva (si habilitado).

🩹 Fallos resueltos (highlights)

Ambigüedad booleana de NA: se evalúa pd.isna() antes que nada.

Warning de regex en str.contains con grupos → grupos no capturantes (?:...).

Propagación desde notas: corte por segmentación dura de rol.

Fechas inconsistentes: detección por patrón, no por dtype.

🧭 Tabla de funciones principales
Función Propósito
load_inputs Lee facts y reestructura presentation si es necesario
normalize_facts Limpia y estandariza facts, detecta fechas, filtra notas
restructure_presentation_to_single_column Reduce árbol a 1 columna “Cuenta”
build_tree_and_order Genera roleUri, depth, order
select_role_tree Filtra árbol por estado
filter_facts_by_statement Aísla el bloque de facts del estado
build_complete_statement_structure Estructura base (taxonomía + orden presentation)
strip_foreign_role_segments Elimina bloques de otros roles (p. ej. [851100])
fill_values_from_facts_strict Pegado estricto por qname/Label exacto
\_period_labels_from_dates, \_period_sort_key Etiquetado/ordenamiento de períodos
add_cash_beginning_period Inserta “Efectivo al principio del periodo” en Flujo
create_legacy_merged_structure Fallback legacy si falla la estrategia estricta
main Orquestación y escritura del Excel

# Español (por defecto)

python xbrl_to_excel.py "/ruta/out_consolidated_2025-2014" "91705000-7_QUIÑENCO_SA_202506" es

# Con debug y vista combinada de periodos

X2E*DEBUG=1 X2E_COMBINED=1 python xbrl_to_excel.py "/ruta/out_consolidated_2025-2014" "91705000-7_QUIÑENCO_SA_202506" es
Salida: estados*<stem>\_es.xlsx (Balance General, Estado de Resultados, Flujo Efectivo).

🧰 Troubleshooting rápido

Cuentas con datos que no deberían

Verifica que el header de notas (p. ej. [851100]) no esté dentro del bloque del estado → strip_foreign_role_segments lo corta.

Asegura que el facts filtrado sea el del estado (filter_facts_by_statement).

Periodos raros

Chequear X2E_DECEMBER_AS_YEAR, X2E_COMBINED, X2E_KEEP_ONLY_QUARTERS.

Columnas duplicadas de fecha

\_coalesce_duplicate_named_columns las fusiona; revisa debug_facts_normalized.csv.

Valores de texto

El escritor limpia comas/espacios. Si no son numéricos válidos → celda vacía.

💡 Criterios de diseño que garantizan precisión

Segmentación dura por rol → cero contaminación entre estados o notas.

Matching exacto y conservador → nunca se “adivina”.

No se escriben números en categorías → se evita ruido en celdas.

Vectorización → desempeño alto con datasets grandes (decenas de periodos).

Debug exhaustivo → diagnóstico claro en cada etapa.

Resumen: el pipeline construye cada estado exclusivamente con facts del bloque correcto, pega valores con criterios estrictos y no ambiguos, bloquea cualquier traspaso desde notas (incluida "[851100] Nota - Estado de flujos de efectivo"), etiqueta los períodos de forma coherente y produce un Excel profesional, estable y trazable.
