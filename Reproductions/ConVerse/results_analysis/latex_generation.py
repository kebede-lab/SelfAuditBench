"""
LaTeX Table Generation Utilities

This module contains functions for generating publication-ready LaTeX tables
from analysis results.
"""

import pandas as pd
from pathlib import Path
from formatting_utils import format_display_name, format_percentage_with_ci, format_rating_with_ci


def generate_model_table(attack_type, models, output_dir, use_case=None, label_suffix='', 
                        selected_model_names=None):
    """
    Generate model comparison table for a specific attack type and use case.
    
    Args:
        attack_type: Type of attack ('security', 'privacy', or 'benign')
        models: List of model names to include
        output_dir: Directory containing analysis CSV files
        use_case: Optional specific use case (None for all domains)
        label_suffix: Suffix for LaTeX label
        selected_model_names: Dict mapping model names to display names
        
    Returns:
        List of LaTeX table lines
    """
    lines = []
    
    # Use default model names if not provided
    if selected_model_names is None:
        selected_model_names = {}
    
    # Filter models to only those with available CSV files
    available_models = []
    for model in models:
        csv_file = Path(output_dir) / f"{attack_type}_use_case_{model}_analysis.csv"
        if csv_file.exists():
            available_models.append(model)
    
    # If no models available, return empty table structure
    if not available_models:
        return []
    
    # Determine title and data source
    if use_case:
        title = f"{format_display_name(use_case)}"
        data_key = use_case
    else:
        title = "All Domains"
        data_key = 'TOTAL'
    
    lines.append(f"% {attack_type.title()} - Model Analysis ({title})")
    lines.append("\\begin{table}[!b]")
    lines.append("    \\centering")
    lines.append("    \\resizebox{\\linewidth}{!}{")
    lines.append("    \\begin{tabular}{llll} \\toprule")
    lines.append("    \\multirow{2}{*}{\\textbf{Model}} & \\multirow{2}{*}{\\textbf{ASR (\\%) $\\downarrow$}} & \\multicolumn{2}{c}{\\textbf{Utility Metrics}} \\\\ \\cmidrule(lr){3-4}")
    lines.append("     & & \\textbf{Rating $\\uparrow$} & \\textbf{Coverage (\\%) $\\uparrow$} \\\\ \\midrule")
    
    for model in available_models:
        csv_file = Path(output_dir) / f"{attack_type}_use_case_{model}_analysis.csv"
        df = pd.read_csv(csv_file, index_col=0)
        if data_key in df.index:
            row = df.loc[data_key]
            display_name = selected_model_names.get(model, format_display_name(model))
            asr_str = format_percentage_with_ci(row['attack_success_rate'], row['attack_success_ci_half'])
            rating_str = format_rating_with_ci(row['utility_rating'], row['utility_rating_ci_half'])
            coverage_str = format_percentage_with_ci(row['utility_coverage'], row['utility_coverage_ci_half'])
            lines.append(f"    {display_name} & {asr_str} & {rating_str} & {coverage_str} \\\\")
    
    lines.append("    \\bottomrule")
    lines.append("    \\end{tabular}}")
    
    # Generate caption
    if use_case:
        caption = f"Analysis of {attack_type} attacks across models on {title} domain."
    else:
        caption = f"Analysis of {attack_type} attacks across complete models averaged over all domains (Travel Planning, Insurance, Real Estate). Models marked by ``*'' are run on all domains."
    
    caption += " $\\downarrow$/$\\uparrow$ means lower/higher values are better, respectively. ASR is the attack success rate. All tables report the 95\\% confidence interval."
    
    lines.append(f"    \\caption{{{caption}}}")
    lines.append(f"    \\label{{tab:{attack_type}_{label_suffix}}}")
    lines.append("\\end{table}")
    lines.append("")
    
    return lines


def generate_grouped_table(attack_type, model, meta_level, use_cases, output_dir,
                          label_suffix, title, col_name):
    """
    Generate table with groups by use case for a specific meta-level.
    
    Args:
        attack_type: Type of attack
        model: Model name
        meta_level: Meta-level to analyze
        use_cases: List of use cases
        output_dir: Directory containing analysis CSV files
        label_suffix: Suffix for LaTeX label
        title: Title for the table
        col_name: Column name for the grouping variable
        
    Returns:
        List of LaTeX table lines
    """
    lines = []
    model_display = format_display_name(model)
    
    lines.append(f"% {attack_type.title()} - {title} ({model_display})")
    lines.append("\\begin{table}[!t]")
    lines.append("    \\centering")
    lines.append("    \\resizebox{\\linewidth}{!}{")
    lines.append("    \\begin{tabular}{lllll} \\toprule")
    lines.append(f"    \\multirow{{2}}{{*}}{{\\textbf{{Domain}}}} & \\multirow{{2}}{{*}}{{\\textbf{{{col_name}}}}} & \\multirow{{2}}{{*}}{{\\textbf{{ASR (\\%)}} $\\downarrow$}} & \\multicolumn{{2}}{{c}}{{\\textbf{{Utility Metrics}}}} \\\\ \\cmidrule(lr){{4-5}}")
    lines.append("     & & & \\textbf{Rating} $\\uparrow$ & \\textbf{Coverage (\\%)} $\\uparrow$ \\\\ \\midrule")
    
    for use_case in use_cases:
        use_case_display = format_display_name(use_case)
        csv_file = Path(output_dir) / f"{attack_type}_{meta_level}_{model}_{use_case}_analysis.csv"
        
        if csv_file.exists():
            df = pd.read_csv(csv_file, index_col=0)
            df = df[df.index != 'TOTAL']
            
            first_row = True
            for idx in df.index:
                row = df.loc[idx]
                idx_display = format_display_name(idx)
                asr_str = format_percentage_with_ci(row['attack_success_rate'], row['attack_success_ci_half'])
                rating_str = format_rating_with_ci(row['utility_rating'], row['utility_rating_ci_half'])
                coverage_str = format_percentage_with_ci(row['utility_coverage'], row['utility_coverage_ci_half'])
                
                if first_row:
                    lines.append(f"    \\multirow{{{len(df)}}}{{*}}{{{use_case_display}}} & {idx_display} & {asr_str} & {rating_str} & {coverage_str} \\\\")
                    first_row = False
                else:
                    lines.append(f"     & {idx_display} & {asr_str} & {rating_str} & {coverage_str} \\\\")
            
            if use_case != use_cases[-1]:
                lines.append("    \\midrule")
    
    lines.append("    \\bottomrule")
    lines.append("    \\end{tabular}}")
    
    domain_text = " and ".join([format_display_name(uc) for uc in use_cases])
    lines.append(f"    \\caption{{Analysis of {attack_type} attacks by {title.lower()} for {model_display} across {domain_text} domains.}}")
    lines.append(f"    \\label{{tab:{attack_type}_{label_suffix}}}")
    lines.append("\\end{table}")
    lines.append("")
    
    return lines


def generate_security_objectives_table(model, use_cases, output_dir):
    """
    Generate security attack objectives table for a specific model.
    
    Args:
        model: Model name
        use_cases: List of use cases
        output_dir: Directory containing analysis CSV files
        
    Returns:
        List of LaTeX table lines
    """
    # Map to shorter names
    objective_map = {
        'Denial of Service (DoS)': 'DoS',
        'Email Manipulation/Fraud': 'Email Manipulation',
        'Upselling': 'Upselling'
    }
    
    lines = []
    lines.append("% Security - Attack Objective Analysis (GPT-5 - All Domains)")
    lines.append("\\begin{table}[!b]")
    lines.append("    \\centering")
    lines.append("    \\resizebox{\\linewidth}{!}{")
    lines.append("    \\begin{tabular}{lllll} \\toprule")
    lines.append("    \\multirow{2}{*}{\\textbf{Domain}} & \\multirow{2}{*}{\\textbf{Attack Objective}} & \\multirow{2}{*}{\\textbf{ASR (\\%) $\\downarrow$}} & \\multicolumn{2}{c}{\\textbf{Utility Metrics}} \\\\ \\cmidrule(lr){4-5}")
    lines.append("     & & & \\textbf{Rating} $\\uparrow$ & \\textbf{Coverage (\\%)} $\\uparrow$ \\\\ \\midrule")
    
    for use_case in use_cases:
        use_case_display = format_display_name(use_case)
        csv_file = Path(output_dir) / f"security_attack_name_group_{model}_{use_case}_analysis.csv"
        
        if csv_file.exists():
            df = pd.read_csv(csv_file, index_col=0)
            df = df[df.index != 'TOTAL']
            
            first_row = True
            for objective in df.index:
                row = df.loc[objective]
                objective_display = objective_map.get(objective, format_display_name(objective))
                asr_str = format_percentage_with_ci(row['attack_success_rate'], row['attack_success_ci_half'])
                rating_str = format_rating_with_ci(row['utility_rating'], row['utility_rating_ci_half'])
                coverage_str = format_percentage_with_ci(row['utility_coverage'], row['utility_coverage_ci_half'])
                
                if first_row:
                    lines.append(f"    \\multirow{{{len(df)}}}{{*}}{{{use_case_display}}} & {objective_display} & {asr_str} & {rating_str} & {coverage_str} \\\\")
                    first_row = False
                else:
                    lines.append(f"     & {objective_display} & {asr_str} & {rating_str} & {coverage_str} \\\\")
            
            if use_case != use_cases[-1]:
                lines.append("    \\midrule")
    
    lines.append("    \\bottomrule")
    lines.append("    \\end{tabular}}")
    lines.append("    \\caption{Analysis of security attacks by attack category for GPT-5 model across three domains.}")
    lines.append("    \\label{tab:security_categories}")
    lines.append("\\end{table}")
    
    return lines


def generate_all_latex_tables(df, output_dir, mode, judge_model, model_filter, 
                             privacy_all_models, privacy_complete_models,
                             security_all_models, security_complete_models,
                             selected_model_names):
    """
    Generate all LaTeX tables for the paper.
    
    Args:
        df: Raw loaded DataFrame (used to determine model groups)
        output_dir: Directory containing analysis CSV files
        mode: Analysis mode
        judge_model: Judge model used
        model_filter: Model filter applied
        privacy_all_models: List of all privacy models
        privacy_complete_models: List of complete privacy models
        security_all_models: List of all security models
        security_complete_models: List of complete security models
        selected_model_names: Dict mapping model names to display names
        
    Returns:
        List of all LaTeX table lines
    """
    latex_selected = []
    
    # TABLE 1: Privacy - All Models (Travel Planning Only)
    latex_selected.extend(generate_model_table(
        'privacy', privacy_all_models, output_dir, 'travel_planning', 
        'all_models_travel', selected_model_names
    ))
    
    # TABLE 2: Privacy - Complete Models (All Domains)
    latex_selected.extend(generate_model_table(
        'privacy', privacy_complete_models, output_dir, None, 
        'complete_models', selected_model_names
    ))
    
    # TABLE 3: Privacy - Data Proximity for Claude Sonnet 4.0
    latex_selected.extend(generate_grouped_table(
        'privacy', 'claude_sonnet_4_0', 'attack_name_group', 
        ['insurance', 'real_estate'], output_dir, 'claude_sonnet_4_proximity', 
        'Data Proximity', 'Data Proximity'
    ))
    
    # TABLE 4: Privacy - Data Category for Claude Sonnet 4.0
    latex_selected.extend(generate_grouped_table(
        'privacy', 'claude_sonnet_4_0', 'privacy_data_category',
        ['insurance', 'real_estate'], output_dir, 'claude_sonnet_4_categories',
        'Data Category', 'Data Category'
    ))
    
    # TABLE 5: Security - All Models (Travel Planning Only)
    latex_selected.extend(generate_model_table(
        'security', security_all_models, output_dir, 'travel_planning', 
        'all_models_travel', selected_model_names
    ))
    
    # TABLE 6: Security - Complete Models (All Domains)
    latex_selected.extend(generate_model_table(
        'security', security_complete_models, output_dir, None, 
        'complete_models', selected_model_names
    ))
    
    # TABLE 7: Security - Attack Objectives for GPT-5
    latex_selected.extend(generate_security_objectives_table(
        'gpt_5_chat', ['insurance', 'real_estate', 'travel_planning'], output_dir
    ))
    
    return latex_selected


def write_latex_file(latex_lines, output_file, mode, judge_model, model_filter):
    """
    Write LaTeX tables to file with configuration header.
    
    Args:
        latex_lines: List of LaTeX table lines
        output_file: Output file path
        mode: Analysis mode
        judge_model: Judge model used
        model_filter: Model filter applied
    """
    # Generate configuration header
    config_header = [
        f"% ============================================================================",
        f"% Analysis Configuration:",
        f"% Mode: {mode}",
        f"% Judge Model: {judge_model}",
    ]
    
    if model_filter:
        if isinstance(model_filter, str):
            config_header.append(f"% Assistant Models: {model_filter} models only")
        else:
            config_header.append(f"% Assistant Models: {', '.join(model_filter)}")
    else:
        config_header.append(f"% Assistant Models: All existing models")
    
    config_header.append(f"% ============================================================================")
    config_header.append("")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(config_header))
        f.write('\n'.join(latex_lines))
