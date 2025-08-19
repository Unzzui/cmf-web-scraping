# 📊 Scripts de Verificación de Disponibilidad XBRL CMF

Este conjunto de scripts te permite verificar qué archivos XBRL están disponibles en la CMF y compararlos con los que ya tienes descargados localmente.

## 🎯 ¿Qué Hacen Estos Scripts?

### 1. **`check_xbrl_availability.py`** - Verificador de Disponibilidad

- ✅ **Verifica** qué períodos XBRL están disponibles en la CMF
- 🌐 **Navega** automáticamente por la página de cada empresa
- 📅 **Revisa** períodos trimestrales (marzo, junio, septiembre, diciembre)
- 📊 **Reporta** qué períodos están disponibles para descarga

### 2. **`compare_xbrl_local_vs_cmf.py`** - Comparador Local vs CMF

- 📁 **Lee** los archivos XBRL que ya tienes descargados
- 🌐 **Compara** con lo disponible en la CMF
- ❌ **Identifica** qué períodos te faltan
- 🔍 **Detecta** archivos extra que podrían no ser necesarios
- 📥 **Recomienda** qué descargar para completar tu colección

## 🚀 Instalación y Uso

### Requisitos

```bash
# Instalar dependencias
pip install selenium beautifulsoup4 pandas

# Asegurarse de tener Chrome y ChromeDriver instalados
```

### Uso Básico

#### Verificar Disponibilidad de Todas las Empresas

```bash
# Ejecutar en modo headless (recomendado)
python check_xbrl_availability.py

# Ejecutar con ventana visible para debugging
python check_xbrl_availability.py --no-headless

# Modo debug con más información
python check_xbrl_availability.py --debug
```

#### Verificar Solo Una Empresa

```bash
# Verificar empresa específica
python check_xbrl_availability.py --company 61808000-5_AGUAS_ANDINAS_SA
```

#### Comparar Archivos Locales con CMF

```bash
# Comparar todas las empresas
python compare_xbrl_local_vs_cmf.py

# Comparar empresa específica
python compare_xbrl_local_vs_cmf.py --company 61808000-5_AGUAS_ANDINAS_SA

# Con ventana visible
python compare_xbrl_local_vs_cmf.py --no-headless
```

## 📁 Estructura de Carpetas Esperada

Los scripts esperan encontrar esta estructura:

```
/home/unzzui/Documents/coding/cmf-web-scraping/data/XBRL/Total/
├── 61808000-5_AGUAS_ANDINAS_SA/
│   ├── Estados_financieros_(XBRL)61808000_201412_extracted/
│   ├── Estados_financieros_(XBRL)61808000_201409_extracted/
│   └── Estados_financieros_(XBRL)61808000_201406_extracted/
├── 91041000-0_VIÑA_SAN_PEDRO_TARAPACA_SA/
│   ├── Estados_financieros_(XBRL)91041000_202412_extracted/
│   └── Estados_financieros_(XBRL)91041000_202312_extracted/
└── [otras empresas...]
```

## 🔍 Cómo Funciona el Proceso

### 1. **Detección de Empresas Locales**

- Lee la carpeta `/data/XBRL/Total/`
- Extrae RUT y nombre de cada carpeta de empresa
- Identifica períodos ya descargados (formato YYYYMM)

### 2. **Verificación en CMF**

- Navega a la página de cada empresa en la CMF
- Llena el formulario automáticamente:
  - **Año**: Desde el actual hacia atrás
  - **Mes**: 3, 6, 9, 12 (trimestral)
  - **Tipo**: Consolidado
  - **Norma**: Estándar IFRS
- Verifica si aparece el enlace "Estados financieros (XBRL)"

### 3. **Comparación y Reporte**

- **Períodos locales**: Lo que ya tienes
- **Períodos CMF**: Lo que está disponible para descargar
- **Períodos faltantes**: Lo que necesitas descargar
- **Períodos extra**: Lo que podrías no necesitar

## 📊 Ejemplo de Salida

### Verificador de Disponibilidad

```
2024-12-20 10:30:15 - INFO - ============================================================
2024-12-20 10:30:15 - INFO - Procesando empresa: 61808000-5_AGUAS_ANDINAS_SA
2024-12-20 10:30:15 - INFO - ============================================================
2024-12-20 10:30:15 - INFO - Verificando disponibilidad XBRL para: 61808000-5_AGUAS_ANDINAS_SA (61808000-5)
2024-12-20 10:30:15 - INFO - Empresa en CMF: AGUAS ANDINAS S.A.
2024-12-20 10:30:15 - INFO - Verificando período: 2025-3 (202503)
2024-12-20 10:30:15 - INFO - ❌ XBRL no disponible para 2025-3
2024-12-20 10:30:15 - INFO - Verificando período: 2024-12 (202412)
2024-12-20 10:30:15 - INFO - ✅ XBRL disponible para 2024-12
```

### Comparador Local vs CMF

```
2024-12-20 10:35:20 - INFO - ============================================================
2024-12-20 10:35:20 - INFO - Comparando períodos para: 61808000-5_AGUAS_ANDINAS_SA
2024-12-20 10:35:20 - INFO - ============================================================
2024-12-20 10:35:20 - INFO - Períodos locales encontrados: 3
2024-12-20 10:35:20 - INFO -   Local: 201412, 201409, 201406
2024-12-20 10:35:20 - INFO - Períodos disponibles en CMF: 5
2024-12-20 10:35:20 - INFO -   CMF: 201412, 201409, 201406, 201403, 201312

2024-12-20 10:35:20 - INFO - 📊 RESUMEN DE COMPARACIÓN:
2024-12-20 10:35:20 - INFO -    📁 Períodos locales: 3
2024-12-20 10:35:20 - INFO -    🌐 Períodos en CMF: 5
2024-12-20 10:35:20 - INFO -    ✅ Períodos en común: 3
2024-12-20 10:35:20 - INFO -    ❌ Períodos faltantes: 2
2024-12-20 10:35:20 - INFO -    🔍 Períodos extra locales: 0

2024-12-20 10:35:20 - INFO - 📥 PERÍODOS FALTANTES (disponibles para descarga):
2024-12-20 10:35:20 - INFO -    📅 2014-03 (201403)
2024-12-20 10:35:20 - INFO -    📅 2013-12 (201312)
```

## 🎯 Casos de Uso

### 1. **Verificación Diaria/Semanal**

```bash
# Ejecutar para ver qué XBRL nuevos están disponibles
python check_xbrl_availability.py
```

### 2. **Auditoría de Colección**

```bash
# Ver qué períodos te faltan para completar tu colección
python compare_xbrl_local_vs_cmf.py
```

### 3. **Verificación de Empresa Específica**

```bash
# Cuando quieres verificar solo una empresa
python check_xbrl_availability.py --company 61808000-5_AGUAS_ANDINAS_SA
```

### 4. **Debugging y Desarrollo**

```bash
# Con ventana visible para ver qué está pasando
python compare_xbrl_local_vs_cmf.py --no-headless --debug
```

## ⚠️ Consideraciones Importantes

### **Respeto al Servidor**

- Los scripts incluyen delays entre consultas
- No sobrecargan la CMF con múltiples requests simultáneos
- Pausa entre empresas para evitar bloqueos

### **Manejo de Errores**

- Recuperación automática de fallos de conexión
- Logging detallado para debugging
- Timeouts configurados para evitar esperas infinitas

### **Configuración del Navegador**

- Modo headless por defecto (más eficiente)
- Configuraciones anti-detección
- Preferencias para evitar descargas accidentales

## 🔧 Personalización

### Cambiar Ruta Base

```python
# En ambos scripts, modificar esta línea:
xbrl_base_path: str = "/home/unzzui/Documents/coding/cmf-web-scraping/data/XBRL/Total"
```

### Ajustar Delays

```python
# Modificar estos valores según tu conexión:
time.sleep(3)      # Espera entre consultas
time.sleep(2)      # Pausa entre empresas
```

### Cambiar Límites

```python
# Ajustar según tus necesidades:
max_periods_to_check = 30  # Máximo períodos a verificar
max_periods_to_check = 20  # Para verificación más rápida
```

## 📈 Próximos Pasos

Una vez que identifiques qué períodos faltan, puedes:

1. **Descargar automáticamente** usando el script `cmf_xbrl_downloader.py`
2. **Priorizar descargas** por empresa o período
3. **Programar verificaciones** periódicas con cron
4. **Integrar** con tu sistema de gestión de archivos

## 🆘 Solución de Problemas

### **Error de ChromeDriver**

```bash
# Instalar ChromeDriver
sudo pacman -S chromedriver  # Arch Linux
# o descargar manualmente desde: https://chromedriver.chromium.org/
```

### **Error de Permisos**

```bash
# Dar permisos de ejecución
chmod +x check_xbrl_availability.py
chmod +x compare_xbrl_local_vs_cmf.py
```

### **Error de Conexión**

- Verificar conexión a internet
- Revisar si la CMF está accesible
- Ajustar timeouts si es necesario

### **Logs Confusos**

```bash
# Usar modo debug para más información
python check_xbrl_availability.py --debug
```

## 📞 Soporte

Si tienes problemas o preguntas:

1. Revisa los logs con `--debug`
2. Verifica que la estructura de carpetas sea correcta
3. Asegúrate de tener todas las dependencias instaladas
4. Revisa que Chrome y ChromeDriver estén funcionando

¡Estos scripts te ayudarán a mantener tu colección de XBRL siempre actualizada! 🎉
