"""
Formatting Utilities for LaTeX Table Generation

This module contains functions for formatting display names, percentages, and ratings
for LaTeX table generation.
"""

import pandas as pd


def format_display_name(name):
    """
    Convert technical field names to human-readable display names.
    
    Args:
        name: Technical name to format
        
    Returns:
        Human-readable display name
    """
    # Model mappings
    model_mappings = {
        'claude_sonnet_4_0': 'Claude Sonnet 4',
        'claude_3_5_haiku_latest': 'Claude 3.5 Haiku',
        'gemini_2.5_flash': 'Gemini 2.5 Flash',
        'gemini_2.5_pro': 'Gemini 2.5 Pro',
        'gpt_5_chat': 'GPT-5',
        'o3_mini': 'O3-Mini',
        'grok_3': 'Grok 3'
    }
    
    # Use case mappings
    use_case_mappings = {
        'insurance': 'Insurance',
        'real_estate': 'Real Estate',
        'travel_planning': 'Travel Planning'
    }
    
    # Attack name group mappings
    attack_name_group_mappings = {
        'Unauthorized Information Access': 'Unauth. Info Access',
        'Potential Privacy Breach': 'Privacy Breach',
        'Denial of Service (DoS)': 'DoS',
        'Upselling': 'Upselling',
        'Email Manipulation/Fraud': 'Email Fraud'
    }
    
    # Check model mappings first
    if name in model_mappings:
        return model_mappings[name]
    
    # Check use case mappings
    if name in use_case_mappings:
        return use_case_mappings[name]
    
    # Check attack name group mappings
    if name in attack_name_group_mappings:
        return attack_name_group_mappings[name]
    
    # Default: replace underscores with spaces and title case
    return name.replace('_', ' ').title()


def sanitize_latex_label(text):
    """
    Sanitize text for use in LaTeX labels by replacing problematic characters.
    
    Args:
        text: Text to sanitize
        
    Returns:
        Sanitized text safe for LaTeX labels
    """
    if not text:
        return ""
    # Replace periods with underscores for LaTeX compatibility
    return text.replace('.', '_').replace(' ', '_').replace('-', '_')


def format_percentage_with_ci(value, ci_half):
    """
    Format percentage with confidence interval like '70.00%±14.00'.
    
    Args:
        value: Percentage value (0-1 range)
        ci_half: Half of the confidence interval
        
    Returns:
        Formatted string for LaTeX
    """
    if pd.isna(value) or pd.isna(ci_half):
        return "\\textbf{0.00\\%}$+$0.09"
    
    percentage = value * 100
    ci_percentage = ci_half * 100
    
    if percentage == 0:
        return "\\textbf{0.00\\%}$+$0.09"
    elif percentage < 1:
        return f"\\textbf{{{percentage:.2f}\\%}}$\\pm${ci_percentage:.2f}"
    else:
        return f"{percentage:.2f}\\%$\\pm${ci_percentage:.2f}"


def format_rating_with_ci(value, ci_half):
    """
    Format rating with confidence interval like '7.70±0.26'.
    
    Args:
        value: Rating value
        ci_half: Half of the confidence interval
        
    Returns:
        Formatted string for LaTeX
    """
    if pd.isna(value) or pd.isna(ci_half):
        return "N/A"
    return f"{value:.2f}$\\pm${ci_half:.2f}"
