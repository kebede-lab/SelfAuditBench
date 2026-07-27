# Results Analysis Package

This package provides a modular codebase for analyzing ConVerse results.

## Overview

The analysis logic is organized into Python utility modules with a clean notebook interface that uses these modules for maintainability and reusability.

## Structure

```
results_analysis/
├── __init__.py                 # Package initialization
├── data_loading.py             # Functions for loading and parsing result files
├── data_enhancement.py         # Functions for creating unified datasets
├── analysis_utils.py           # Statistical analysis and confidence intervals
├── formatting_utils.py         # LaTeX formatting utilities
├── latex_generation.py         # LaTeX table generation
├── results_analysis.ipynb      # Simplified notebook using the utilities
└── README.md                   # This file
```

## Modules

### data_loading.py
- `load_all_results()`: Load all judge result files from "logs" directory with filtering
- `parse_file_path()`: Parse file paths to extract metadata from an attack log (e.g., use case, model, persona, etc.)

### data_enhancement.py
- `create_unified_dataset()`: Combine utility, security, and privacy evaluations
- `create_attack_name_group()`: Create attack name groups based on attack type (e.g., related_and_useful, related_but_private, and unrelated attacks for privacy)
- `create_security_attack_group()`: Map security attack actions to categories (e.g., DoS, Upselling, Email Manipulation)
- `enhance_dataset_with_groupings()`: Add the previous attack groupings and categorizations to the unified dataset

### analysis_utils.py
- `calculate_confidence_interval()`: Wilson score interval for binomial proportions
- `calculate_utility_confidence_interval()`: t-distribution CIs for means
- `calculate_attack_success_metrics()`: Attack success rates with CIs
- `calculate_utility_metrics()`: Utility rating and coverage metrics with CIs
- `analyze_by_attack_type_and_meta_level()`: Comprehensive meta-level analysis
- `generate_per_model_use_case_analysis()`: Per-model use case CSVs
- `create_attack_type_comparison()`: Attack type comparison CSV

### formatting_utils.py
- `format_display_name()`: Convert technical names to human-readable format
- `format_percentage_with_ci()`: Format percentages with confidence intervals for LaTeX
- `format_rating_with_ci()`: Format ratings with confidence intervals for LaTeX
- `sanitize_latex_label()`: Sanitize text for LaTeX labels

### latex_generation.py
- `generate_model_table()`: Generate model comparison tables
- `generate_grouped_table()`: Generate domain-grouped analysis tables
- `generate_security_objectives_table()`: Generate security objectives table
- `generate_all_latex_tables()`: Generate all LaTeX tables for paper
- `write_latex_file()`: Write LaTeX tables to file with configuration header

## Usage

### Running the Notebook

1. Open `results_analysis.ipynb` in Jupyter or VS Code
2. Configure the analysis parameters in the configuration cell:
   - `MODE`: "baseline" or "taskConfined"
   - `JUDGE_MODEL`: Judge model used (e.g., "gpt-5")
   - `MODEL_FILTER`: Optional filter for assistant models
3. Run all cells to generate analysis results and LaTeX tables

### Using the Modules in Your Own Code

```python
from results_analysis import (
    load_all_results,
    create_unified_dataset,
    enhance_dataset_with_groupings,
    analyze_by_attack_type_and_meta_level,
    generate_all_latex_tables
)

# Load data
df = load_all_results(mode="baseline", judge_model="gpt-5")

# Create enhanced dataset
enhanced_df = create_unified_dataset(df)
enhanced_df = enhance_dataset_with_groupings(enhanced_df)

# Perform analysis
results = analyze_by_attack_type_and_meta_level(
    enhanced_df, 'security', ['model', 'use_case'], 'output_dir'
)

# Generate LaTeX tables
latex_tables = generate_all_latex_tables(
    df, 'output_dir', 'baseline', 'gpt-5', None,
    all_models, complete_models, all_models, complete_models,
    model_names
)
```

## Output Files

- **CSV files**: Detailed analysis with confidence intervals in `analysis_outputs/` (temporary)
- **LaTeX file**: Publication-ready tables saved as `../latex_tables_selected.tex` (in root folder)
