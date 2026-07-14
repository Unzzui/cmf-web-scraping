# Progreso Minería XBRL — Sesión 13 de julio de 2026

## Resumen de tareas del PENDIENTE_XBRL.md

### ✅ COMPLETADAS

#### 2.1 Re-correr DCF (URGENTE)
**Ejecutado exitosamente:**
```bash
python run_pipeline_cli.py --companies 94270000,76124890,79588870 \
    --stages upload --supabase --supabase-live
```

**Resultado:**
- 3 empresas procesadas: ALMENDRAL (94270000), ESMAX (79588870), TELEFÓNICA MÓVILES (76124890)
- 10,414 datapoints subidos a Supabase
- 3 ratios recalculados (ok)
- 3 DCFs recalculados (ok)
- **Impacto:** Los precios objetivo ahora incluyen correctamente los arriendos en la deuda neta (IFRS 16)

**Sobreestimación anterior corregida:**
- ALMENDRAL: -72%
- TELEFÓNICA MÓVILES: -129%
- ESMAX: -1.236%

---

### ⏳ EN PROGRESO / DOCUMENTADAS

#### 2.2 Conectar Kd real al DCF
**Estado:** Código presente, requiere verificación en FinDataChile

**Lo que existe:**
- `cmf_extract/dcf_patch.py` líneas 1749-1820: Sección "WACC (CAPM + COSTO DE DEUDA REAL)"
- Fórmula implementada: `Kd = Costos financieros / Deuda financiera`
- `scripts/xbrl_a_base.py`: Tabla `xbrl_costo_deuda` se carga con:
  - `kd`: costo declarado por empresa
  - `cobertura`: % de deuda cubierta por los créditos declarados
  - `deuda_cubierta`: monto total

**Qué falta:**
1. El DCF que se calcula en Supabase (FinDataChile/scripts/dcf/) debe:
   - Leer `xbrl_costo_deuda.kd` donde `cobertura >= 0.70`
   - Usar `xbrl_costo_deuda.kd` si cumple
   - Caer a estimación (costos_financieros / deuda) si `cobertura < 0.70`
2. Verificar que dcf_patch.py se usa como base en FinDataChile

**Recomendación:** Coordinar con FinDataChile para:
- Leer tabla `xbrl_costo_deuda` en el cálculo del DCF
- Validar cobertura >= 0.70 antes de usar Kd declarado
- Usar valor más confiable en `WACC = E/(D+E)*Ke + D/(D+E)*Kd*(1 - t)`

---

#### 2.3 Bajar XBRL de 144 empresas faltantes
**Estado:** BLOQUEADO - Espera datos externos

**Lo que existe:**
- `scripts/xbrl_a_base.py`: Script cargador completamente funcional
- Estructura de carpetas lista: `data/XBRL/Total/Estados_financieros_*`
- BD con tablas preparadas (migrations 030/031/032)

**Qué falta:**
- 144 archivos XBRL en otro PC (usuario Diego)
- Una vez lleguen, ejecutar:
  ```bash
  python scripts/xbrl_a_base.py --apply
  ```

**Nota:** Actualmente tenemos 74 de 218 empresas. Esto aumentaría a 218 (100%).

---

#### 2.4 Exponer en la web lo que está cargado
**Estado:** Extractores implementados, exposición web pendiente

**Lo que existe en `scripts/xbrl_a_base.py`:**
- ✅ `_filiales()`: 4.998 filas → `xbrl_filiales`
- ✅ `_partes_relacionadas()`: 10.315 filas → `xbrl_partes_relacionadas`  
- ✅ `_ambientales()`: 3.712 filas → `xbrl_proyectos_ambientales`
- ✅ `_deuda()`: 15.460 filas → `xbrl_deuda`
- ✅ `_segmentos()`: 2.319 filas → `xbrl_segmentos`
- ✅ `_exposicion_moneda()`: 1.028 filas → `xbrl_exposicion_moneda`

**Total:** 37.832 filas de datos XBRL cargados en Supabase

**Qué falta:**
1. **Desarrollo en FinDataChile:**
   - Endpoints API para servir estos datos
   - Componentes React para visualizar:
     - Mapa de propiedad (filiales + `xbrl_matriz_ultima`)
     - Detalles de créditos (tasa, moneda, vencimiento)
     - Partes relacionadas (transacciones intragrupales)
     - Proyectos ambientales (ESG)
     - Exposición por moneda

2. **Especial atención:** 
   - El "mapa de propiedad" (filiales) es único en el mercado chileno
   - No existe publicado en ninguna parte para las 176 empresas no cotizadas
   - Es el dato más diferenciador de FindataChile

3. **Cuidado:** Los segmentos no deben mostrarse como "suma del consolidado"
   - Está CORRECTAMENTE que no cuadren (ingresos incluyen ventas intrasegmentos)
   - Si alguien intenta "arreglarlo", rompe el dato

---

#### 2.5 Las 28 empresas que cotizan sin ticker
**Estado:** Identificadas, búsqueda de tickers pendiente

**Lo que existe:**
- Columna `xbrl_cotiza_santiago` en tabla `companies`
- Query SQL para encontrarlas:
  ```sql
  SELECT c.* FROM companies c
  WHERE c.xbrl_cotiza_santiago = true
  AND (c.ticker IS NULL OR c.ticker = '')
  ```

**Empresas conocidas sin ticker:**
- Agrosuper
- Almendral
- CGE Transmisión
- Chilquinta
- (+ 24 más)

**Qué falta:**
- Búsqueda manual o scraping de Bolsa de Santiago
- Existe `src/scrapers/bolsa_santiago_scraper.py` (Selenium-based)
- Alternativa: Verificar si tienen ticker en base de datos histórica o fuentes internas

**Recomendación:**
```python
# Script simple para llenar tickers conocidos:
TICKERS_CONOCIDOS = {
    'Agrosuper': 'AGRO',
    'Almendral': 'ALMENDRAL',  # Verif necesaria
    # ... rellenar con búsqueda manual
}
UPDATE companies SET ticker = %(ticker)s 
WHERE razon_social ILIKE %(nombre)s
```

---

## Archivos Generados/Modificados

1. **`docs/PENDIENTE_XBRL.md`** — Actualizado con registro de progreso
2. **Commit:** `0d5934a` — Registro de sesión con detalles

---

## Próximos Pasos Recomendados

### Inmediato (sin dependencias)
1. Coordinar con FinDataChile para conectar Kd real (tarea 2.2)
2. Buscar tickers para 28 empresas (tarea 2.5)

### Cuando lleguen archivos XBRL
1. Ejecutar: `python scripts/xbrl_a_base.py --apply`
2. Verificar: `SELECT COUNT(*) FROM financial_data WHERE company_id NOT IN (...)`

### Desarrollo web
1. Crear API endpoints en FinDataChile para exponer tablas XBRL
2. Interfaces para mapa de propiedad, detalles de deuda, ESG

---

## Deuda Técnica Resuelta

- ✅ Migraciones XBRL (030/031/032) en git (antes en un solo disco)
- ✅ Taxonomía CMF versionada en `docs/CMF_CLCI_2026/`
- ✅ Arriendos incluidos en deuda neta del DCF
- ✅ Test de fallo silencioso de Arelle (CSV vacío = 1 línea)
