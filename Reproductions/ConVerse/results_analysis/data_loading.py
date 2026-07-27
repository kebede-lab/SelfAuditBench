"""
Data Loading Utilities for ConVerse Benchmark Analysis

This module contains functions for loading and parsing result files from the logs directory.
"""

import json
import os
import glob
import re
from pathlib import Path
import pandas as pd


def parse_file_path(file_path):
    """
    Parse a result file path to extract metadata.
    
    Args:
        file_path: Path to the result file
        
    Returns:
        Dictionary containing extracted metadata or None if parsing fails
    """
    path_parts = Path(file_path).parts
    
    # Extract metadata from path structure
    # Example: logs/travel_planning/gpt_5_chat/baseline/persona1/privacy/attack_name/file.json
    try:
        logs_idx = path_parts.index('logs')
        use_case = path_parts[logs_idx + 1]
        model = path_parts[logs_idx + 2]
        mode = path_parts[logs_idx + 3]  # baseline, taskConfined, etc.
        persona = path_parts[logs_idx + 4]
        attack_category = path_parts[logs_idx + 5]  # privacy, security
        attack_name = path_parts[logs_idx + 6]
        filename = path_parts[-1]
        
        # Extract judge type, judge model, and metadata from filename
        judge_type = None
        judge_model = None
        repetition = None
        retry = None
        
        # Determine judge type and extract judge model if present
        if 'utility_judge' in filename:
            judge_type = 'utility'
            # New format: utility_judge_gpt-5_20251119_040535_rep1.json
            # Old format: utility_judge_20251005_011555_rep1.json
            match = re.match(r'utility_judge_([^_]+)_\d{8}_\d{6}', filename)
            if match:
                # Check if the first group is a model name (not a date)
                potential_model = match.group(1)
                if not potential_model.isdigit() or len(potential_model) != 8:
                    judge_model = potential_model
        elif 'privacy_judge' in filename:
            judge_type = 'privacy'
            match = re.match(r'privacy_judge_([^_]+)_\d{8}_\d{6}', filename)
            if match:
                potential_model = match.group(1)
                if not potential_model.isdigit() or len(potential_model) != 8:
                    judge_model = potential_model
        elif 'security_judge' in filename:
            judge_type = 'security'
            match = re.match(r'security_judge_([^_]+)_\d{8}_\d{6}', filename)
            if match:
                potential_model = match.group(1)
                if not potential_model.isdigit() or len(potential_model) != 8:
                    judge_model = potential_model
        else:
            return None
        
        # Extract repetition number
        rep_match = re.search(r'_rep(\d+)', filename)
        if rep_match:
            repetition = int(rep_match.group(1))
        
        # Extract retry number
        retry_match = re.search(r'_retry(\d+)', filename)
        if retry_match:
            retry = int(retry_match.group(1))
        
        return {
            'use_case': use_case,
            'model': model,
            'mode': mode,
            'persona': persona,
            'attack_category': attack_category,
            'attack_name': attack_name,
            'judge_type': judge_type,
            'judge_model': judge_model,
            'repetition': repetition,
            'retry': retry,
            'filename': filename,
            'file_path': file_path
        }
    except (ValueError, IndexError) as e:
        return None

def load_all_results(logs_dir='../logs', mode=None, judge_model=None, model_filter=None, verbose=False):
    """
    Load all judge result files from the logs directory.
    
    Args:
        logs_dir: Base directory for logs (default: '../logs' for running from results_analysis folder).
        mode: Filter results by mode (e.g., 'baseline', 'taskConfined'). If None, load all modes.
        judge_model: Filter results by judge model (e.g., 'gpt-5', 'claude-sonnet-4'). If None, load all judge models.
        model_filter: Filter by assistant model. Can be:
            - None: Include all models
            - String: "gemini", "claude", "gpt" to filter by model family
            - List: Specific model names to include
        verbose: If True, print each file as it's being loaded
        
    Returns:
        DataFrame containing all loaded results with metadata
    """
    all_results = []
    
    # Find all JSON files in logs directory that contain 'judge' in filename
    pattern = os.path.join(logs_dir, '**', '*judge*.json')
    json_files = glob.glob(pattern, recursive=True)
    
    if verbose:
        print(f"\n🔍 Processing {len(json_files)} total judge files...")
    
    loaded_count = 0
    for file_path in json_files:
        # Parse file path metadata
        metadata = parse_file_path(file_path)
        if metadata is None:
            continue
        
        # Filter by mode if specified
        if mode is not None and metadata.get('mode') != mode:
            continue
        
        # Filter by judge model if specified
        # If judge_model is None, select only files WITHOUT model names (old format)
        # If judge_model is a string, select only files WITH that specific model name
        if judge_model is None:
            # Only include files where judge_model is None (old format without model name)
            if metadata.get('judge_model') is not None:
                continue
        else:
            # Only include files with the specified judge model
            if metadata.get('judge_model') != judge_model:
                continue
        
        if verbose:
            print(f"   ✓ Loading: {file_path} [judge_model={metadata.get('judge_model')}]")
        loaded_count += 1
        
        # Filter by assistant model if specified
        if model_filter is not None:
            assistant_model = metadata.get('model')
            if isinstance(model_filter, str):
                # Filter by model family
                if model_filter.lower() == 'gemini' and 'gemini' not in assistant_model.lower():
                    continue
                elif model_filter.lower() == 'claude' and 'claude' not in assistant_model.lower():
                    continue
                elif model_filter.lower() == 'gpt' and 'gpt' not in assistant_model.lower():
                    continue
            elif isinstance(model_filter, list):
                # Filter by specific model list
                if assistant_model not in model_filter:
                    continue
        
        try:
            # Load JSON content
            with open(file_path, 'r', encoding='utf-8') as f:
                content = json.load(f)
            
            # Handle different JSON content types
            if isinstance(content, dict):
                # If content is a dictionary, merge with metadata
                result = {**metadata, **content}
                all_results.append(result)
            
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            continue
        except Exception as e:
            continue
    
    if verbose:
        print(f"\n✅ Successfully loaded {loaded_count} files after filtering\n")
    
    return pd.DataFrame(all_results)
