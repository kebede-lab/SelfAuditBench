"""
Results Analysis Package for ConVerse Benchmark

This package provides utilities for analyzing benchmark results across different
models, use cases, attack types, and personas.

Modules:
- data_loading: Functions for loading and parsing result files
- data_enhancement: Functions for creating unified datasets and categorizations
- analysis_utils: Statistical analysis and confidence interval calculations
- formatting_utils: LaTeX formatting utilities
- latex_generation: LaTeX table generation functions
"""

__version__ = "1.0.0"

from .data_loading import load_all_results, parse_file_path
from .data_enhancement import (
    create_unified_dataset,
    enhance_dataset_with_groupings,
    create_attack_name_group,
    create_security_attack_group
)
from .analysis_utils import (
    calculate_confidence_interval,
    calculate_utility_confidence_interval,
    calculate_attack_success_metrics,
    calculate_utility_metrics,
    analyze_by_attack_type_and_meta_level,
    generate_per_model_use_case_analysis,
    create_attack_type_comparison
)
from .formatting_utils import (
    format_display_name,
    format_percentage_with_ci,
    format_rating_with_ci,
    sanitize_latex_label
)
from .latex_generation import (
    generate_model_table,
    generate_grouped_table,
    generate_security_objectives_table,
    generate_all_latex_tables,
    write_latex_file
)

__all__ = [
    # Data loading
    'load_all_results',
    'parse_file_path',
    
    # Data enhancement
    'create_unified_dataset',
    'enhance_dataset_with_groupings',
    'create_attack_name_group',
    'create_security_attack_group',
    
    # Analysis utilities
    'calculate_confidence_interval',
    'calculate_utility_confidence_interval',
    'calculate_attack_success_metrics',
    'calculate_utility_metrics',
    'analyze_by_attack_type_and_meta_level',
    'generate_per_model_use_case_analysis',
    'create_attack_type_comparison',
    
    # Formatting utilities
    'format_display_name',
    'format_percentage_with_ci',
    'format_rating_with_ci',
    'sanitize_latex_label',
    
    # LaTeX generation
    'generate_model_table',
    'generate_grouped_table',
    'generate_security_objectives_table',
    'generate_all_latex_tables',
    'write_latex_file'
]
