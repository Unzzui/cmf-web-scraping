# Minería del XBRL — lo que falta

Estado al 13 de julio de 2026. Escrito para que quien retome esto (yo incluido, en dos
semanas) no tenga que reconstruir el contexto desde los commits.

---

## 1. Dos riesgos que ya se cerraron (13 jul 2026)

**Las migraciones ya están en git.** `migrations/` estaba en el `.gitignore`: 20 de 30
migraciones —incluidas las tres del XBRL, aplicadas en producción— vivían en un solo disco.
El `.gitignore` además escondía una colisión: había **dos migraciones numeradas 027**
(`027_ratio_direction` y `027_xbrl_mineria`) y nadie podía verlo. Las del XBRL se
renumeraron a **030/031/032**, y `schema_migrations` se actualizó en la base para que las
dos fuentes digan lo mismo.

**La taxonomía de la CMF ya está versionada.** `docs/CMF_CLCI_2026` no es documentación: es
una dependencia de `cmf_taxonomia.py`. Sin ella el módulo se degrada **en silencio** a una
lista escrita a mano, y los segmentos vuelven a sumar mal. Ahora hay un test que falla si
el paquete no está — un aviso en el log no sirve, porque nadie lo mira y el dato equivocado
ya viajó.

---

## 2. Lo que falta hacer

### 2.1 Re-correr el DCF (URGENTE — hay precios objetivo mal en producción)

Los arriendos ya entran en la deuda neta (`scripts/dcf/excel_aligned.py`,
`cmf_extract/dcf_patch.py`), pero **la base todavía tiene los valores viejos**. Los precios
objetivo publicados hoy están inflados:

| empresa | sobreestimado |
|---|---|
| ALMENDRAL | 72% |
| TELEFÓNICA MÓVILES | 129% |
| ESMAX | 1.236% |

Hasta que se recalcule, la web está mostrando un precio objetivo que sabemos que está mal.

```bash
python run_pipeline_cli.py --companies <ruts> --stages upload --supabase --supabase-live
```

### 2.2 Conectar el Kd real al DCF

`xbrl_costo_deuda` ya tiene el costo de deuda **declarado** por cada empresa (crédito por
crédito, incluidos los arriendos). El DCF lo sigue **estimando** como
`costos financieros / deuda financiera`.

Al conectarlo hay que respetar la columna `cobertura`: si la nota cubre menos del ~70% de
la deuda del balance, ese Kd no representa a la empresa y **hay que caer a la estimación**.
La columna existe precisamente porque un Kd calculado sobre el 4% de la deuda de Aguas
Andinas se veía perfectamente sano.

### 2.3 Bajar el XBRL de las 144 empresas que faltan

Sólo tenemos 74 de 218 en disco. **El dato no falta en el XBRL: falta el archivo.** Por eso
el lector de acciones sacó 51 y no 218.

Diego dijo que tiene la data en otro PC. El cargador (`scripts/xbrl_a_base.py`) corre sobre
las 218 sin ningún cambio en cuanto estén los archivos.

### 2.4 Exponer en la web lo que ya está cargado

Nada de esto se ve todavía:

| tabla | filas | qué es |
|---|---|---|
| `xbrl_deuda` | 15.460 | cada crédito con su tasa, moneda y vencimiento |
| `xbrl_partes_relacionadas` | 10.315 | con quién opera dentro del grupo |
| `xbrl_filiales` | 4.998 | el mapa de propiedad, con RUT y % |
| `xbrl_proyectos_ambientales` | 3.712 | ESG verificable |
| `xbrl_segmentos` | 2.319 | ingresos/resultado por segmento |
| `xbrl_exposicion_moneda` | 1.028 | activos y pasivos por moneda |

Lo más diferenciador es el **mapa de propiedad** (filiales + `xbrl_matriz_ultima`): no
existe publicado en ninguna parte, y menos para las 176 empresas que no cotizan — que son
justo las que ninguna API cubre.

**Cuidado al mostrar segmentos:** la suma de los segmentos **no da** el consolidado, y eso
es correcto. Los ingresos de un segmento incluyen las ventas a otros segmentos. Si alguien
"arregla" eso para que cuadre, rompe el dato.

### 2.5 Las 28 empresas que cotizan y no tienen ticker

`companies.xbrl_cotiza_santiago` ahora dice qué empresas se transan en bolsa. Hay **28 que
cotizan y no tienen ticker** en nuestra base (Agrosuper, Almendral, CGE Transmisión,
Chilquinta…). Para ellas el precio existe y no lo estamos trayendo.

Antes de esto, la web no podía distinguir "no hay precio porque no cotiza" de "no hay
precio porque nos falta el ticker", y las mostraba igual: vacías.

---

## 3. Lo que se descartó a propósito (para que nadie lo "rescate" después)

**`LevelOfRoundingUsedInFinancialStatements`** prometía declarar la ESCALA de las cifras —
justo la clase de bug que más caro nos ha salido. Verificado contra los 74 archivos: es
**texto libre** con 38 valores distintos, entre ellos `'"Llos presentes esta…'` y
`'Toda la información…'`. Y no predice nada: Falabella declara "Pesos", Aguas Andinas
"Miles de Pesos", y las dos traen los hechos en **unidades**.

Conclusión verificada, y vale por sí sola: **los valores del XBRL están siempre en unidades
de la moneda**, diga lo que diga ese campo. El `/1000` del pipeline es correcto y uniforme.

No se guarda. Un dato que no se puede creer es peor que ninguno — y éste habría *parecido*
autoritativo, que es lo que lo hace peligroso.

**`NumeroAccionistas`**: mezcla el número de accionistas con el de acciones (`'64'` junto a
`'1705831078'`). Nadie lo llena en serio.

---

## 4. Los límites, dichos sin adornos

**El precio de la acción y el beta NO pueden salir del XBRL.** Son hechos de mercado.
Ningún estado financiero dice a qué precio se transó la acción ayer. Esos dos van a seguir
necesitando una fuente externa, y prometer lo contrario sería mentir.

**La convención de las tasas es ambigua en la propia norma.** `TasaEfectiva` está declarada
como `xbrli:decimalItemType` — un decimal *sin* semántica de porcentaje. La taxonomía
*tiene* un `num:percentItemType` y eligió no usarlo. Por eso 17 empresas declaran sus tasas
en decimal y en porcentaje **dentro del mismo archivo**.

La heurística de `xbrl_deuda._tasa()` (frontera en 0,30) es inevitable, no perezosa. Sin
ella, Inversiones La Construcción salía con un costo de deuda del 52%.

---

## 5. Las trampas del formato, para no volver a caer

Están fijadas como tests en `cmf_extract/tests/test_xbrl_facts.py`. No son pruebas
defensivas: son cicatrices.

1. **El `id` de la unidad miente.** LATAM declara `<xbrli:unit id="CLP">` cuyo measure es
   `iso4217:USD`. Creerle al nombre habría dividido sus cifras por 900.

2. **Dos codificaciones.** 22 archivos en UTF-8 y 52 en ISO-8859-1 — y el linkbase de
   etiquetas de la CMF **miente sobre la suya** (declara latin-1 y es UTF-8). Se prueba
   UTF-8 estricto primero.

3. **"Tiene dimensión" no es "es un segmento".** En Arauco, 2.147 de 2.154 contextos tienen
   dimensión, y casi todas son desgloses de patrimonio o tramos de morosidad.

4. **Un eje es un ÁRBOL.** Sumar todos los miembros daba 4.448 millones donde Arauco tiene
   1.482. Y "hoja del eje" tampoco basta: en SMU, `UnallocatedAmountsMember` **es** una hoja
   pero cuelga de las partidas de reconciliación, no de los segmentos. Un segmento es una
   hoja que **desciende de** `OperatingSegmentsMember`.

5. **Cada crédito aparece dos veces**, una por el cierre y otra por el comparativo. La clave
   es `(miembro, fecha)`, no el miembro.
