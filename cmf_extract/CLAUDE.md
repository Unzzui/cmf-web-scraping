# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**CMF Extract** is a comprehensive Python system for extracting, processing, and analyzing Chilean financial data from the CMF (Comisión para el Mercado Financiero). The project handles XBRL files from Chilean companies and converts them into Excel reports with advanced financial analysis capabilities.

### Core Functionality

The system processes financial data through several stages:

1. **XBRL Processing**: Converts XBRL files to CSV using Arelle, then to Excel
2. **Batch Processing**: Handles multiple companies and time periods
3. **Financial Analysis**: Calculates ratios, metrics, and generates comprehensive reports
4. **Interactive CLI**: Provides guided processing with real-time dashboards

### Key Technologies

- **Python 3.12+** - Primary language
- **Arelle** - XBRL processing engine
- **Pandas/OpenPyXL** - Data manipulation and Excel generation
- **Threading/Multiprocessing** - Parallel processing
- **JSON** - Configuration and taxonomy management

## Development Commands

### Core Processing Commands

**Main CLI Interface:**

- `python cmf_cli.py` - Interactive CLI for guided processing
- `env X2E_DEBUG=1 python cmf_cli.py` - Run with debug logging

**XBRL Processing:**

- `python batch_xbrl_to_excel.py --base-dir data/XBRL/Total --arelle-dir ~/Documents/Arelle` - Process XBRL files
- `python xbrl_to_excel.py <out_dir> <stem> <lang>` - Convert single XBRL to Excel

**Financial Analysis:**

- `python run_products_analysis.py --input-dir Products --output-dir Product_v1 --frequency Total` - Generate analysis reports

### Environment Setup

**Virtual Environment:**

- `python -m venv venv` - Create virtual environment
- `source venv/bin/activate` (Linux/Mac) - Activate environment
- `pip install -r requirements.txt` - Install dependencies

**Development Tools:**

- `pytest` - Run tests
- `pytest tests/test_final_excel_validation.py --excel-path <path>` - Validate specific Excel output
- `python -m pytest -v` - Verbose test output

### Debug and Monitoring

**Debug Variables:**

- `X2E_DEBUG=1` - Enable detailed XBRL conversion logging
- `CMF_DASH_ENABLED=1` - Show console dashboard during processing
- `X2E_KEEP_ALL_DATES=1` - Preserve all date columns (no auto-trim)
- `X2E_DECEMBER_AS_YEAR=1` - Map December dates to year labels
- `X2E_COMBINED=1` - Enable combined mode processing

**Performance Control:**

- `CMF_WORKERS=8` - Set number of worker threads
- `CMF_COMBINED_TTM_LAST_N=3` - Number of recent quarters for TTM calculations

## Project Structure

### Main Scripts

```
├── cmf_cli.py                 # Interactive CLI interface
├── batch_xbrl_to_excel.py     # Batch XBRL processing
├── xbrl_to_excel.py          # Core XBRL→Excel converter
├── run_products_analysis.py   # Financial analysis runner
└── generate_combined_from_total.py  # Combined report generator
```

### Core Modules

```
├── analisis_excel/           # Financial analysis framework
│   ├── data_extractor.py     # Excel data extraction
│   ├── ratio_calculator.py   # Financial ratio calculations
│   ├── formula_builder.py    # Excel formula generation
│   ├── excel_formatter.py    # Report formatting
│   ├── bulk_processor.py     # Batch analysis processing
│   └── utils/               # Utilities and helpers
│       ├── console_dashboard.py  # Real-time progress display
│       ├── lang_map.py       # Language mappings
│       └── cuentas.json      # Account mappings
```

### Data Structure

```
├── data/
│   └── XBRL/
│       ├── Total/            # Combined annual/quarterly data
│       ├── Anual/           # Annual reports only
│       └── Trimestral/      # Quarterly reports only
├── Products/                # Intermediate processed files
│   ├── Total/
│   ├── Anual/
│   └── Trimestral/
└── Product_v1/             # Final analysis reports
    ├── Total/
    ├── Anual/
    └── Trimestral/
```

## XBRL Processing Workflow

### Data Flow

1. **Input**: Raw XBRL files from CMF in `data/XBRL/`
2. **Arelle Export**: Extract facts and presentation data to CSV
3. **Excel Generation**: Create structured Excel reports with formulas
4. **Consolidation**: Combine multiple periods per company
5. **Analysis**: Generate comprehensive financial analysis

### File Naming Conventions

- **XBRL Datasets**: `Estados_financieros_(XBRL)<RUT>_<YYYYMM>_extracted/`
- **Output Files**: `estados_<RUT>_<period_range>_<lang>.xlsx`
- **Analysis Files**: `<company>_<period>_analisis_<type>.xlsx`

### Processing Modes

**Total Mode** (Recommended):

- Combines annual and quarterly data
- Creates time series with quarterly detail under annual columns
- Generates TTM (Trailing Twelve Months) calculations
- Optimal for trend analysis

**Anual Mode**:

- Annual reports only (December periods)
- Year-over-year comparison
- Suitable for long-term analysis

**Trimestral Mode**:

- Quarterly reports only
- Quarter-over-quarter analysis
- Good for seasonal pattern analysis

## Financial Analysis System

### Analysis Modules

**DataExtractor** (`analisis_excel/data_extractor.py`):

- Loads Excel files with automatic sheet detection
- Handles bilingual content (Spanish/English)
- Extracts Balance Sheet, Income Statement, Cash Flow data
- Identifies date columns and financial concepts

**RatioCalculator** (`analisis_excel/ratio_calculator.py`):

- **Liquidity Ratios**: Current Ratio, Quick Ratio, Cash Ratio
- **Solvency Ratios**: Debt-to-Equity, Debt-to-Assets, Interest Coverage
- **Profitability Ratios**: Gross Margin, Operating Margin, ROE, ROA
- **Efficiency Ratios**: Asset Turnover, Inventory Turnover, Cash Cycle

**FormulaBuilder** (`analisis_excel/formula_builder.py`):

- Creates Excel formulas that reference original data cells
- Maintains data transparency and traceability
- Supports bilingual formula generation
- Handles period-specific calculations

### Analysis Types

**Formula Analysis** (Recommended):

- Generates Excel formulas referencing source data
- Dynamic calculations update with data changes
- Full transparency of calculation methods
- Includes explanatory tooltips

**Value Analysis**:

- Static calculated values
- Faster processing for large batches
- Suitable for comparative analysis
- Smaller file sizes

## Configuration and Customization

### Company-Specific Structures

- `analisis_excel/estructura_eeff_empresas.json` - Custom account mappings per company
- Supports industry-specific chart of accounts
- Overrides default taxonomies when available

### Taxonomy Management

- `taxonomia_ilustrada.json` - IFRS account mappings
- `analisis_excel/utils/cuentas.json` - Legacy account mappings
- Supports multiple languages and accounting standards

### Environment Variables

**Processing Control:**

```bash
X2E_MIN_YEAR=2020          # Minimum year to include
X2E_MAX_YEAR=2024          # Maximum year to include
X2E_AUTO_TRIM_EMPTY_TAIL=1 # Remove empty trailing columns
X2E_MIN_NONEMPTY_PER_YEAR=5 # Minimum non-empty cells per year
```

**Mode Control:**

```bash
X2E_COMBINED=1             # Enable combined mode
X2E_KEEP_ALL_DATES=1       # Keep all date columns
X2E_DECEMBER_AS_YEAR=1     # Map December to year labels
CMF_ANALYSIS_COMBINED=1    # Combined analysis mode
```

**Performance:**

```bash
CMF_WORKERS=8              # Processing threads
CMF_DASH_ENABLED=1         # Show progress dashboard
CMF_DASH_REFRESH_HZ=1.0    # Dashboard refresh rate
```

## Common Workflows

### Processing a Single Company

```bash
python cmf_cli.py
# Select specific company from interactive list
# System will process XBRL → Excel → Analysis automatically
```

### Batch Processing All Companies

```bash
python cmf_cli.py
# Select "0. Procesar todos" option
# System processes all companies in Total mode
```

### Manual XBRL Processing

```bash
# Set environment variables
export X2E_DEBUG=1
export CMF_WORKERS=4

# Process specific frequency
python batch_xbrl_to_excel.py \
  --base-dir data/XBRL/Total \
  --arelle-dir ~/Documents/Arelle \
  --langs es
```

### Analysis Only

```bash
# Generate analysis from existing processed files
python run_products_analysis.py \
  --input-dir Products/Total \
  --output-dir Product_v1/Total \
  --frequency Total \
  --workers 4
```

## Troubleshooting

### Common Issues

**XBRL Processing Errors:**

- Verify Arelle installation: `~/Documents/Arelle/arelleCmdLine.py`
- Check XBRL file integrity in dataset directories
- Enable debug logging: `X2E_DEBUG=1`

**Excel Generation Issues:**

- Ensure sufficient memory for large datasets
- Check file permissions in output directories
- Verify pandas/openpyxl compatibility

**Analysis Calculation Errors:**

- Validate input Excel structure (Balance Sheet, Income Statement, Cash Flow)
- Check date column format in headers
- Review account name mappings in cuentas.json

### Performance Optimization

**For Large Datasets:**

- Reduce CMF_WORKERS if memory-constrained
- Use value analysis instead of formula analysis
- Process companies individually rather than batch

**For Speed:**

- Enable combined mode caching
- Use SSD storage for data directories
- Increase worker count on multi-core systems

### Debug Techniques

**Enable Full Debugging:**

```bash
export X2E_DEBUG=1
export CMF_DASH_ENABLED=1
python cmf_cli.py
```

**Validate Specific Outputs:**

```bash
pytest tests/test_final_excel_validation.py \
  --excel-path Product_v1/Total/company_analysis.xlsx -v
```

**Check Processing Logs:**

```bash
tail -f data/debug/xbrl_run.log
tail -f data/debug/products_run.log
```

## Best Practices

### Data Management

- Keep original XBRL files in `data/XBRL/` structure
- Use version control for taxonomy and mapping files
- Regular backups of processed results
- Monitor disk space for large processing runs

### Development

- Use type hints for all function signatures
- Add comprehensive error handling for file operations
- Document complex business logic with comments
- Write tests for financial calculation accuracy

### Performance

- Process companies in parallel when possible
- Cache taxonomy and mapping data between runs
- Use appropriate data types (float64 for financial data)
- Monitor memory usage during large batch operations

## Security Considerations

### Data Protection

- Financial data is sensitive - ensure appropriate access controls
- Use environment variables for configuration paths
- Avoid hardcoding company names or RUT numbers in code
- Log minimal information to avoid data exposure

### File Handling

- Validate input file integrity before processing
- Use secure temporary directories for intermediate files
- Clean up temporary files after processing
- Handle file permission errors gracefully

---

**Development Philosophy:** This system prioritizes data accuracy, transparency, and maintainability. All financial calculations should be verifiable, all data transformations should be auditable, and all processes should handle edge cases gracefully.
