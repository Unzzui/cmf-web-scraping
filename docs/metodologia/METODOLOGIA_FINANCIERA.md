# Metodología de Análisis Financiero

## Introducción

Este documento describe la metodología financiera utilizada para el cálculo de ratios e indicadores financieros basados en los estados financieros extraídos de reportes XBRL de la CMF (Comisión para el Mercado Financiero) de Chile.

## 1. Ratios de Liquidez

### 1.1 Liquidez Corriente
**Fórmula:** Activo Corriente / Pasivo Corriente

**Interpretación:** Mide la capacidad de la empresa para cumplir con sus obligaciones de corto plazo (menos de un año) utilizando sus activos más líquidos. Un ratio superior a 1.0 indica que la empresa tiene suficientes activos corrientes para cubrir sus pasivos corrientes.

**Estándares de referencia:**
- Ratio < 1.0: Posible problema de liquidez
- Ratio 1.0 - 1.5: Liquidez adecuada
- Ratio > 2.0: Posible exceso de liquidez (fondos no productivos)

### 1.2 Prueba Ácida (Quick Ratio)
**Fórmula:** (Activo Corriente - Inventarios) / Pasivo Corriente

**Interpretación:** Ratio más conservador que excluye los inventarios por ser menos líquidos. Mide la capacidad inmediata de la empresa para pagar sus deudas de corto plazo sin depender de la venta de inventarios.

**Estándares de referencia:**
- Ratio < 0.8: Posible problema de liquidez inmediata
- Ratio 0.8 - 1.2: Liquidez adecuada
- Ratio > 1.5: Excelente liquidez

### 1.3 Cash Ratio
**Fórmula:** Efectivo y Equivalentes / Pasivo Corriente

**Interpretación:** El ratio más conservador de liquidez. Mide la capacidad de la empresa para pagar sus deudas inmediatas únicamente con efectivo y equivalentes de efectivo.

**Estándares de referencia:**
- Ratio < 0.2: Liquidez crítica
- Ratio 0.2 - 0.5: Liquidez limitada pero aceptable
- Ratio > 0.5: Excelente liquidez inmediata

### 1.4 Capital de Trabajo
**Fórmula:** Activo Corriente - Pasivo Corriente

**Interpretación:** Representa los recursos financieros netos disponibles para financiar las operaciones diarias. Un capital de trabajo positivo indica que la empresa puede financiar sus operaciones corrientes.

## 2. Ratios de Solvencia y Estructura

### 2.1 Endeudamiento (Debt-to-Equity)
**Fórmula:** Deuda Total / Patrimonio

**Interpretación:** Mide la proporción de financiamiento mediante deuda versus patrimonio. Indica el apalancamiento financiero y el riesgo asociado.

**Estándares de referencia:**
- Ratio < 0.5: Bajo endeudamiento
- Ratio 0.5 - 1.0: Endeudamiento moderado
- Ratio > 1.5: Alto endeudamiento (mayor riesgo)

### 2.2 Apalancamiento (Debt-to-Assets)
**Fórmula:** Deuda Total / Activos Totales

**Interpretación:** Indica qué proporción de los activos está financiada con deuda. Valores más altos indican mayor dependencia del financiamiento externo.

**Estándares de referencia:**
- Ratio < 0.3: Bajo apalancamiento
- Ratio 0.3 - 0.6: Apalancamiento moderado
- Ratio > 0.7: Alto apalancamiento

### 2.3 Cobertura de Intereses
**Fórmula:** EBIT / |Gastos por Intereses|

**Interpretación:** Mide la capacidad de la empresa para pagar los intereses de su deuda con las ganancias operativas. Un ratio más alto indica mejor capacidad de servicio de deuda.

**Estándares de referencia:**
- Ratio < 2.5: Cobertura insuficiente
- Ratio 2.5 - 5.0: Cobertura adecuada
- Ratio > 10.0: Excelente cobertura

### 2.4 Deuda / EBITDA
**Fórmula:** Deuda Total / EBITDA

**Interpretación:** Indica cuántos años tomaría pagar toda la deuda si se dedicara todo el EBITDA a este propósito. Es una medida de sostenibilidad de la deuda.

**Estándares de referencia:**
- Ratio < 3.0: Deuda sostenible
- Ratio 3.0 - 5.0: Deuda moderada
- Ratio > 6.0: Deuda preocupante

### 2.5 Autonomía Financiera
**Fórmula:** Patrimonio / Activo Total

**Interpretación:** Mide el grado de independencia financiera de la empresa. Valores más altos indican menor dependencia de financiamiento externo.

## 3. Ratios de Rentabilidad

### 3.1 Margen Bruto
**Fórmula:** Utilidad Bruta / Ventas

**Interpretación:** Indica el porcentaje de ingresos que queda después de deducir el costo directo de los bienes vendidos. Refleja la eficiencia en la gestión de costos directos.

### 3.2 Margen Operativo (EBIT)
**Fórmula:** EBIT / Ventas

**Interpretación:** Mide la rentabilidad operativa antes de intereses e impuestos. Refleja la eficiencia operativa de la empresa.

### 3.3 Margen EBITDA
**Fórmula:** EBITDA / Ventas

**Interpretación:** Margen operativo antes de depreciación y amortización. Útil para comparar empresas con diferentes estructuras de activos fijos.

### 3.4 Margen Neto
**Fórmula:** Utilidad Neta / Ventas

**Interpretación:** Indica el porcentaje de ventas que se convierte en utilidad neta después de todos los gastos, intereses e impuestos.

### 3.5 ROE (Return on Equity)
**Fórmula:** Utilidad Neta / Patrimonio Promedio

**Interpretación:** Mide la rentabilidad generada sobre el patrimonio de los accionistas. Utiliza el promedio del patrimonio entre el año actual y anterior para mayor precisión.

**Estándares de referencia:**
- ROE < 10%: Rentabilidad baja
- ROE 10% - 15%: Rentabilidad adecuada
- ROE > 20%: Excelente rentabilidad

### 3.6 ROA (Return on Assets)
**Fórmula:** Utilidad Neta / Activos Totales Promedio

**Interpretación:** Mide la eficiencia de la empresa en generar utilidades con sus activos. Utiliza el promedio de activos para mayor precisión.

## 4. Ratios de Eficiencia Operativa

### 4.1 Rotación de Activos
**Fórmula:** Ventas / Activos Totales Promedio

**Interpretación:** Mide la eficiencia con que la empresa utiliza sus activos para generar ventas. Valores más altos indican mejor utilización de activos.

### 4.2 Rotación de Inventarios
**Fórmula:** Costo de Ventas / Inventarios Promedio

**Interpretación:** Indica cuántas veces al año la empresa rota completamente su inventario. Valores más altos sugieren mejor gestión de inventarios.

### 4.3 Días de Inventario
**Fórmula:** 365 / Rotación de Inventarios

**Interpretación:** Número promedio de días que los productos permanecen en inventario antes de ser vendidos.

### 4.4 Rotación de Cuentas por Cobrar
**Fórmula:** Ventas / Cuentas por Cobrar Promedio

**Interpretación:** Mide la eficiencia en la cobranza. Valores más altos indican cobros más rápidos.

### 4.5 Período Promedio de Cobro
**Fórmula:** 365 / Rotación de Cuentas por Cobrar

**Interpretación:** Número promedio de días que toma cobrar las ventas a crédito.

### 4.6 Rotación de Cuentas por Pagar
**Fórmula:** Compras / Cuentas por Pagar Promedio

**Interpretación:** Mide la frecuencia de pago a proveedores. Se aproximan las compras como Costo de Ventas + Cambio en Inventarios.

### 4.7 Período Promedio de Pago
**Fórmula:** 365 / Rotación de Cuentas por Pagar

**Interpretación:** Número promedio de días que la empresa toma para pagar a sus proveedores.

### 4.8 Ciclo de Conversión de Efectivo
**Fórmula:** Días de Inventario + Período Promedio de Cobro - Período Promedio de Pago

**Interpretación:** Tiempo total entre el desembolso de efectivo para comprar inventario y la recepción de efectivo por las ventas. Valores más bajos son mejores.

## 5. Ratios de Flujos de Efectivo

### 5.1 Conversión de Caja
**Fórmula:** Flujo de Efectivo Operativo / Utilidad Neta

**Interpretación:** Mide qué tan bien la empresa convierte sus utilidades contables en efectivo real. Valores cercanos a 1.0 o superiores son deseables.

### 5.2 Free Cash Flow
**Fórmula:** Flujo de Efectivo Operativo - CAPEX

**Interpretación:** Efectivo disponible después de mantener y expandir la base de activos. Positivo indica capacidad de generar efectivo para dividendos, reducciones de deuda o crecimiento.

### 5.3 Estructura de Activos (AC/AT)
**Fórmula:** Activo Corriente / Activo Total

**Interpretación:** Proporción de activos que son corrientes (líquidos). Valores más altos indican mayor liquidez pero posiblemente menor rentabilidad.

### 5.4 Estructura de Pasivos (PC/PT)
**Fórmula:** Pasivo Corriente / Pasivo Total

**Interpretación:** Proporción de pasivos que vencen en el corto plazo. Valores más altos indican mayor presión de liquidez.

## 6. Consideraciones Metodológicas

### 6.1 Tratamiento de Datos Faltantes
- Se utiliza el valor disponible cuando solo hay un período
- Se calcula el promedio aritmético cuando hay dos períodos consecutivos
- Se aplican verificaciones de error para evitar divisiones por cero

### 6.2 Estados por Naturaleza vs. por Función
Para empresas que reportan estados de resultados por naturaleza (código 320000), se realizan aproximaciones:
- Costo de Ventas ≈ Materias Primas + Cambio en Inventarios - Trabajos Capitalizados

### 6.3 Periodicidad de Cálculo
- Los ratios se calculan por período reportado (típicamente anual)
- Se utilizan promedios de balance cuando es apropiado (ROE, ROA, ratios de rotación)
- Los flujos de efectivo se toman del período correspondiente

### 6.4 Moneda y Unidades
- Todos los cálculos se realizan en las unidades originales de reporte (típicamente miles de pesos chilenos)
- Los ratios son adimensionales o se expresan en las unidades apropiadas (días, veces por año, etc.)

## 7. Limitaciones y Consideraciones

### 7.1 Limitaciones de los Ratios
- Los ratios son indicadores históricos, no predictivos
- Deben compararse con empresas del mismo sector
- Las diferencias contables pueden afectar la comparabilidad
- Los eventos extraordinarios pueden distorsionar los resultados

### 7.2 Contexto Económico
- Los ratios deben interpretarse considerando el ciclo económico
- Las condiciones del mercado financiero afectan los estándares de referencia
- La inflación puede distorsionar comparaciones intertemporales

### 7.3 Calidad de Datos
- Los resultados dependen de la calidad y completitud de los datos XBRL
- Se recomienda validar datos anómalos con los estados financieros originales
- Algunos conceptos pueden requerir ajustes manuales según el contexto específico