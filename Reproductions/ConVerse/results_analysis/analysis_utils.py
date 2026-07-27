"""
Analysis Utilities for ConVerse Benchmark

This module contains functions for statistical analysis, confidence interval calculations,
and meta-level analysis of benchmark results.
"""

import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats


def calculate_confidence_interval(successes, total, confidence=0.95):
    """
    Calculate Wilson score interval for binomial proportion.
    
    Args:
        successes: Number of successful outcomes
        total: Total number of trials
        confidence: Confidence level (default: 0.95)
        
    Returns:
        Tuple of (lower_bound, upper_bound)
    """
    if total == 0:
        return 0.0, 0.0
    
    p = successes / total
    z = 1.96  # 95% confidence
    
    denominator = 1 + z**2 / total
    center = (p + z**2 / (2*total)) / denominator
    margin = z * np.sqrt((p*(1-p) + z**2/(4*total)) / total) / denominator
    
    return max(0.0, center - margin), min(1.0, center + margin)


def calculate_utility_confidence_interval(values, confidence=0.95):
    """
    Calculate confidence interval for means using t-distribution with proper bounds.
    
    Args:
        values: Array of values
        confidence: Confidence level (default: 0.95)
        
    Returns:
        Tuple of (mean, lower_bound, upper_bound)
    """
    if len(values) == 0:
        return 0.0, 0.0, 0.0
    
    mean_val = np.mean(values)
    if len(values) == 1:
        # For single values, return the value with no confidence interval
        return mean_val, mean_val, mean_val
    
    if len(values) == 2:
        # For exactly 2 values, use min/max as bounds
        ci_lower = min(values)
        ci_upper = max(values)
    elif len(values) <= 5:
        # For small samples (3-5), use a conservative approach
        std_val = np.std(values, ddof=1)
        margin = std_val * 1.5  # Conservative multiplier
        ci_lower = mean_val - margin
        ci_upper = mean_val + margin
    else:
        # Use standard t-distribution for larger samples
        sem = stats.sem(values)
        t_crit = stats.t.ppf((1 + confidence) / 2, len(values) - 1)
        margin = t_crit * sem
        ci_lower = mean_val - margin
        ci_upper = mean_val + margin
    
    # Apply reasonable bounds based on the data range
    # Check if all values are in percentage range (0-1) FIRST (more specific)
    if all(0 <= v <= 1 for v in values):  # Likely coverage percentages
        ci_lower = max(0.0, ci_lower)
        ci_upper = min(1.0, ci_upper)
    # Check if all values are in rating range (0-10) SECOND (more general)  
    elif all(0 <= v <= 10 for v in values):  # Likely utility ratings
        ci_lower = max(0.0, ci_lower)
        ci_upper = min(10.0, ci_upper)
    
    return mean_val, ci_lower, ci_upper


def calculate_attack_success_metrics(group_df, attack_type):
    """
    Calculate attack success rate and confidence intervals.
    
    Args:
        group_df: DataFrame for a specific group
        attack_type: Type of attack ('security', 'privacy', or 'benign')
        
    Returns:
        Tuple of (success_rate, ci_lower, ci_upper, successes)
    """
    group_size = len(group_df)
    
    if attack_type == 'security':
        success_mask = group_df['attack_success'].isin(['Successful', 'Partially successful'])
        successes = success_mask.sum()
    elif attack_type == 'privacy':
        shared_raw_yes = (group_df['privacy_shared_raw_data'] == 'yes')
        leaked_info_yes = (group_df['privacy_leaked_information'] == 'yes')
        success_mask = shared_raw_yes | leaked_info_yes
        successes = success_mask.sum()
    else:  # benign
        return 0.0, 0.0, 0.0, 0
    
    success_rate = successes / group_size if group_size > 0 else 0.0
    ci_lower, ci_upper = calculate_confidence_interval(successes, group_size)
    return success_rate, ci_lower, ci_upper, successes


def calculate_utility_metrics(group_df):
    """
    Calculate utility rating and coverage metrics with confidence intervals.
    
    Args:
        group_df: DataFrame for a specific group
        
    Returns:
        Dictionary with rating and coverage metrics
    """
    rating_values = group_df['utility_average_rating'].dropna().values
    coverage_values = group_df['utility_items_covered_rate'].dropna().values
    
    rating_mean, rating_ci_lower, rating_ci_upper = calculate_utility_confidence_interval(rating_values)
    coverage_mean, coverage_ci_lower, coverage_ci_upper = calculate_utility_confidence_interval(coverage_values)
    
    return {
        'rating_mean': rating_mean,
        'rating_ci_lower': rating_ci_lower,
        'rating_ci_upper': rating_ci_upper,
        'coverage_mean': coverage_mean,
        'coverage_ci_lower': coverage_ci_lower,
        'coverage_ci_upper': coverage_ci_upper
    }


def create_row_data(meta_level, group_value, group_df, attack_type):
    """
    Create a row of analysis data for a specific group.
    
    Args:
        meta_level: Name of the meta-level being analyzed
        group_value: Value of the group
        group_df: DataFrame for this group
        attack_type: Type of attack
        
    Returns:
        Dictionary containing all metrics for this row
    """
    group_size = len(group_df)
    success_rate, ci_lower, ci_upper, successes = calculate_attack_success_metrics(group_df, attack_type)
    utility_metrics = calculate_utility_metrics(group_df)
    
    return {
        meta_level: group_value,
        'scenario_count': group_size,
        'attack_success_rate': success_rate,
        'attack_success_ci_lower': ci_lower,
        'attack_success_ci_upper': ci_upper,
        'attack_success_ci_half': (ci_upper - ci_lower) / 2,
        'utility_rating': utility_metrics['rating_mean'],
        'utility_rating_ci_lower': utility_metrics['rating_ci_lower'],
        'utility_rating_ci_upper': utility_metrics['rating_ci_upper'],
        'utility_rating_ci_half': (utility_metrics['rating_ci_upper'] - utility_metrics['rating_ci_lower']) / 2,
        'utility_coverage': utility_metrics['coverage_mean'],
        'utility_coverage_ci_lower': utility_metrics['coverage_ci_lower'],
        'utility_coverage_ci_upper': utility_metrics['coverage_ci_upper'],
        'utility_coverage_ci_half': (utility_metrics['coverage_ci_upper'] - utility_metrics['coverage_ci_lower']) / 2
    }


def analyze_meta_level_generic(analysis_df, meta_level, attack_type, model_name=None, use_case=None):
    """
    Generic analysis function for any meta-level.
    
    Args:
        analysis_df: DataFrame to analyze
        meta_level: Column name to group by
        attack_type: Type of attack
        model_name: Optional model name for filtering
        use_case: Optional use case for filtering
        
    Returns:
        DataFrame with analysis results
    """
    table_data = []
    
    for group_value, group_df in analysis_df.groupby(meta_level):
        if pd.isna(group_value):
            continue
        
        row_data = create_row_data(meta_level, group_value, group_df, attack_type)
        table_data.append(row_data)
    
    if not table_data:
        return None
    
    results_df = pd.DataFrame(table_data)
    
    # Add TOTAL row
    total_row = create_row_data(meta_level, 'TOTAL', analysis_df, attack_type)
    results_df = pd.concat([results_df, pd.DataFrame([total_row])], ignore_index=True)
    
    return results_df


def save_analysis_csv(results_df, attack_type, meta_level, output_dir, model_name=None, use_case=None):
    """
    Save analysis results to CSV file.
    
    Args:
        results_df: DataFrame with results
        attack_type: Type of attack
        meta_level: Meta-level analyzed
        output_dir: Output directory path
        model_name: Optional model name
        use_case: Optional use case
    """
    filename_parts = [attack_type, meta_level]
    if model_name:
        filename_parts.append(model_name)
    if use_case:
        filename_parts.append(use_case)
    filename_parts.append('analysis.csv')
    
    csv_filename = Path(output_dir) / '_'.join(filename_parts)
    results_df.to_csv(csv_filename, index=False)


def analyze_by_attack_type_and_meta_level(df, attack_type, meta_levels, output_dir, verbose=False):
    """
    Analyze each meta-level within a specific attack type with proper model filtering.
    
    Args:
        df: Enhanced dataset DataFrame
        attack_type: Type of attack to analyze
        meta_levels: List of meta-levels to analyze
        output_dir: Directory to save CSV outputs
        verbose: If True, print detailed progress
        
    Returns:
        Dictionary with all analysis results
    """
    attack_df = df[df['attack_type'] == attack_type].copy()
    
    if len(attack_df) == 0:
        if verbose:
            print(f"⚠️  No {attack_type} data found")
        return {}
    
    if verbose:
        print(f"\n🎯 === {attack_type.upper()} ATTACK ANALYSIS === 🎯")
        print(f"Total {attack_type} scenarios: {len(attack_df)}")
        print("-" * 60)
    
    results = {}
    global_meta_levels = ['model', 'attack_type']
    
    # Process global meta-levels
    for meta_level in global_meta_levels:
        if meta_level in meta_levels:
            if verbose:
                print(f"\n📊 {meta_level.replace('_', ' ').title()} Analysis for {attack_type.title()} Attacks (Global):")
            
            results_df = analyze_meta_level_generic(attack_df, meta_level, attack_type)
            if results_df is not None:
                results[meta_level] = results_df
                save_analysis_csv(results_df, attack_type, meta_level, output_dir)
    
    # Process model-filtered meta-levels
    model_filtered_meta_levels = [ml for ml in meta_levels if ml not in global_meta_levels]
    
    if model_filtered_meta_levels:
        for model_name in attack_df['model'].unique():
            if pd.isna(model_name):
                continue
            
            model_attack_df = attack_df[attack_df['model'] == model_name].copy()
            
            for meta_level in model_filtered_meta_levels:
                # Handle use-case-specific meta-levels
                if meta_level in ['privacy_data_category', 'attack_name_group', 'responsibility_flag']:
                    # Special checks for attack type applicability
                    if meta_level == 'privacy_data_category' and attack_type != 'privacy':
                        continue
                    if meta_level == 'attack_name_group' and attack_type == 'benign':
                        continue
                    
                    # Process each use case separately
                    for use_case in model_attack_df['use_case'].unique():
                        if pd.isna(use_case):
                            continue
                        
                        use_case_df = model_attack_df[model_attack_df['use_case'] == use_case]
                        analysis_df = use_case_df.dropna(subset=[meta_level])
                        
                        if len(analysis_df) == 0:
                            continue
                        
                        if len(analysis_df[meta_level].unique()) <= 1:
                            continue
                        
                        results_df = analyze_meta_level_generic(analysis_df, meta_level, attack_type, 
                                                               model_name, use_case)
                        if results_df is not None:
                            key = f"{meta_level}_{model_name}_{use_case}"
                            results[key] = results_df
                            save_analysis_csv(results_df, attack_type, meta_level, output_dir, 
                                            model_name, use_case)
                else:
                    # Handle other meta-levels normally
                    analysis_df = model_attack_df.copy()
                    if len(analysis_df[meta_level].unique()) <= 1:
                        continue
                    
                    results_df = analyze_meta_level_generic(analysis_df, meta_level, attack_type, model_name)
                    if results_df is not None:
                        key = f"{meta_level}_{model_name}"
                        results[key] = results_df
                        save_analysis_csv(results_df, attack_type, meta_level, output_dir, model_name)
    
    return results


def generate_per_model_use_case_analysis(df, output_dir, verbose=False):
    """
    Generate per-model use_case aggregation CSVs for LaTeX table generation.
    
    Args:
        df: Enhanced dataset DataFrame
        output_dir: Directory to save CSV outputs
        verbose: If True, print progress
    """
    if verbose:
        print(f"\n📊 Generating per-model use_case analysis CSVs...")
    
    for attack_type in ['security', 'privacy', 'benign']:
        attack_df = df[df['attack_type'] == attack_type]
        
        if len(attack_df) == 0:
            continue
        
        for model_name in attack_df['model'].unique():
            if pd.isna(model_name):
                continue
            
            model_df = attack_df[attack_df['model'] == model_name]
            use_case_data = []
            
            # Analyze each use case
            for use_case in model_df['use_case'].unique():
                if pd.isna(use_case):
                    continue
                
                use_case_df = model_df[model_df['use_case'] == use_case]
                row_data = create_row_data('use_case', use_case, use_case_df, attack_type)
                use_case_data.append(row_data)
            
            # Add TOTAL row (all use cases combined)
            if len(model_df) > 0:
                total_row = create_row_data('use_case', 'TOTAL', model_df, attack_type)
                use_case_data.append(total_row)
            
            # Save to CSV
            if use_case_data:
                use_case_df_export = pd.DataFrame(use_case_data)
                csv_filename = f"{attack_type}_use_case_{model_name}_analysis.csv"
                csv_path = Path(output_dir) / csv_filename
                use_case_df_export.to_csv(csv_path, index=False)
                if verbose:
                    print(f"  💾 Saved: {csv_filename}")


def create_attack_type_comparison(df, output_dir, verbose=False):
    """
    Create comparison CSV across attack types.
    
    Args:
        df: Enhanced dataset DataFrame
        output_dir: Directory to save CSV output
        verbose: If True, print progress
    """
    if verbose:
        print(f"\n📊 Creating attack type comparison CSV...")
    
    attack_comparison_data = []
    
    for attack_type in ['security', 'privacy', 'benign']:
        attack_df = df[df['attack_type'] == attack_type]
        
        if len(attack_df) == 0:
            continue
        
        success_rate, ci_lower, ci_upper, successes = calculate_attack_success_metrics(attack_df, attack_type)
        utility_metrics = calculate_utility_metrics(attack_df)
        
        attack_comparison_data.append({
            'attack_type': attack_type,
            'scenario_count': len(attack_df),
            'attack_success_rate': success_rate,
            'attack_success_ci_half': (ci_upper - ci_lower) / 2,
            'utility_rating': utility_metrics['rating_mean'],
            'utility_rating_ci_half': (utility_metrics['rating_ci_upper'] - utility_metrics['rating_ci_lower']) / 2,
            'utility_coverage': utility_metrics['coverage_mean'],
            'utility_coverage_ci_half': (utility_metrics['coverage_ci_upper'] - utility_metrics['coverage_ci_lower']) / 2
        })
    
    comparison_df = pd.DataFrame(attack_comparison_data)
    comparison_df.to_csv(Path(output_dir) / 'attack_type_comparison.csv', index=False)
    if verbose:
        print(f"  💾 Saved: attack_type_comparison.csv")
