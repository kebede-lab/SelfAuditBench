"""
Data Enhancement Utilities for ConVerse Benchmark Analysis

This module contains functions for enhancing the dataset with attack details,
creating unified datasets, and categorizing attacks.
"""

import json
import os
from pathlib import Path
from collections import defaultdict
import pandas as pd
import re


def extract_filename_key(file_path):
    """Extract the common filename key after removing judge type prefix."""
    filename = os.path.basename(file_path)
    # Remove the judge type prefix (utility_judge_, security_judge_, privacy_judge_)
    if filename.startswith('utility_judge_'):
        return filename[14:]  # Remove 'utility_judge_' prefix
    elif filename.startswith('security_judge_'):
        return filename[15:]  # Remove 'security_judge_' prefix
    elif filename.startswith('privacy_judge_'):
        return filename[14:]  # Remove 'privacy_judge_' prefix
    return filename


def extract_utility_metrics(file_path):
    """Extract utility metrics from utility judge files."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = json.load(f)
            
        # Extract utility metrics based on the actual structure
        how_many_items = 0
        items_covered_rate = 0.0
        
        if 'utility_evaluation' in content and isinstance(content['utility_evaluation'], dict):
            utility_section = content['utility_evaluation']
            if 'UTILITY' in utility_section and isinstance(utility_section['UTILITY'], dict):
                items_covered_str = utility_section['UTILITY'].get('HOW_MANY_ITEMS_COVERED', '0/0')
                
                # Parse the "5/5" format to extract both numerator and denominator
                if '/' in items_covered_str:
                    parts = items_covered_str.split('/')
                    if len(parts) == 2:
                        try:
                            numerator = int(parts[0])
                            denominator = int(parts[1])
                            how_many_items = numerator
                            # Calculate rate as float, handle division by zero
                            items_covered_rate = float(numerator) / float(denominator) if denominator > 0 else 0.0
                        except ValueError:
                            how_many_items = 0
                            items_covered_rate = 0.0
                else:
                    # Handle cases where it's just a single number
                    how_many_items = int(items_covered_str) if items_covered_str.isdigit() else 0
                    items_covered_rate = 1.0 if how_many_items > 0 else 0.0
        
        # Extract rating metrics
        average_rating = 0
        num_items_rated = 0
        if 'ratings_evaluation' in content and isinstance(content['ratings_evaluation'], dict):
            ratings_section = content['ratings_evaluation']
            average_rating = ratings_section.get('average_rating', 0)
            num_items_rated = ratings_section.get('num_items_rated', 0)
        
        return {
            'utility_how_many_items_covered': how_many_items,
            'utility_items_covered_rate': items_covered_rate,
            'utility_average_rating': average_rating,
            'utility_num_items_rated': num_items_rated
        }
    except Exception as e:
        return {
            'utility_how_many_items_covered': 0,
            'utility_items_covered_rate': 0.0,
            'utility_average_rating': 0,
            'utility_num_items_rated': 0
        }


def load_all_attack_files(verbose=False):
    """Load all security and privacy attack JSON files from the resources folder."""
    base_path = '../resources'  # Adjusted for running from results_analysis subdirectory
    use_cases = ['insurance_usecase', 'real_estate_usecase', 'travel_planning_usecase']
    attack_types = ['security_attacks', 'privacy_attacks']
    
    # Storage structure: {use_case: {persona: {attack_type: data}}}
    all_attacks = defaultdict(lambda: defaultdict(dict))
    load_count = 0
    error_count = 0
    
    for use_case in use_cases:
        for attack_type in attack_types:
            attack_folder = os.path.join(base_path, use_case, attack_type)
            
            if os.path.exists(attack_folder):
                for persona_num in range(1, 5):  # persona1 to persona4
                    persona_file = f"{attack_type}_persona{persona_num}.json"
                    file_path = os.path.join(attack_folder, persona_file)
                    
                    if os.path.exists(file_path):
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                data = json.load(f)
                                
                            # Clean use case name (remove _usecase suffix)
                            clean_use_case = use_case.replace('_usecase', '')
                            persona = f'persona{persona_num}'
                            
                            all_attacks[clean_use_case][persona][attack_type] = data
                            load_count += 1
                            
                        except Exception as e:
                            error_count += 1
                            if verbose:
                                print(f"⚠️  Error loading {file_path}: {e}")
    
    if verbose:
        print(f"🔍 load_all_attack_files: Loaded {load_count} files, {error_count} errors")
        print(f"   Use cases: {list(dict(all_attacks).keys())}")
    
    return dict(all_attacks)


def find_security_attack_action(attack_name, use_case, persona, attack_data):
    """Find the attack_action for a given security attack name with fuzzy matching."""
    if use_case not in attack_data or persona not in attack_data[use_case]:
        return None
        
    security_data = attack_data[use_case][persona].get('security_attacks', {})
    
    # Navigate through the nested security attacks structure
    if 'security_attacks' in security_data:
        for attack_category, attacks in security_data['security_attacks'].items():
            # Each attack category contains multiple attacks (attack_1, attack_2, etc.)
            for attack_key, attack_details in attacks.items():
                if isinstance(attack_details, dict):
                    resource_name = attack_details.get('name', '')
                    # Try exact match first
                    if resource_name == attack_name:
                        return attack_details.get('attack_action')
                    # Try partial match (handles cases where judge names are truncated)
                    if resource_name and attack_name and (
                        resource_name.lower() in attack_name.lower() or 
                        attack_name.lower() in resource_name.lower()
                    ):
                        return attack_details.get('attack_action')
    
    return None


def find_privacy_data_category(data_item, use_case, persona, attack_data):
    """Find the category for a given privacy data item with fuzzy matching."""
    if use_case not in attack_data or persona not in attack_data[use_case]:
        return None
        
    privacy_data = attack_data[use_case][persona].get('privacy_attacks', {})
    
    # Navigate through the nested privacy structure
    if 'categories' in privacy_data:
        for category_type, category_data in privacy_data['categories'].items():
            if 'items' in category_data:
                for item in category_data['items']:
                    if isinstance(item, dict):
                        resource_item = item.get('data_item', '')
                        # Try exact match first
                        if resource_item == data_item:
                            return item.get('category')
                        # Try partial/fuzzy matching for items like "Passport Issue/Expiry Dates"
                        if resource_item and data_item and (
                            'passport' in resource_item.lower() and 'passport' in data_item.lower() and
                            ('issue' in data_item.lower() or 'expiry' in data_item.lower())
                        ):
                            return item.get('category')
    
    return None


def extract_privacy_data_from_file(file_path):
    """Extract privacy-specific data from a privacy judge file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = json.load(f)
        
        # Initialize privacy fields
        privacy_data = {
            'privacy_leaked_information': None,
            'privacy_shared_raw_data': None,
            'privacy_data_item': None,
            'privacy_evaluation_type': None,
            'privacy_confidence_score': None
        }
        
        # Check for llm_evaluation structure (most common)
        if 'llm_evaluation' in content and isinstance(content['llm_evaluation'], dict):
            llm_eval = content['llm_evaluation']
            
            # Check for leaked_information field
            if 'leaked_information' in llm_eval:
                privacy_data['privacy_leaked_information'] = llm_eval['leaked_information']
            
            # Check for shared_raw_data field
            if 'shared_raw_data' in llm_eval:
                privacy_data['privacy_shared_raw_data'] = llm_eval['shared_raw_data']
            
            # Extract confidence score
            if 'confidence_score' in llm_eval:
                privacy_data['privacy_confidence_score'] = llm_eval['confidence_score']
        
        # Check for data_item field at top level
        if 'data_item' in content:
            privacy_data['privacy_data_item'] = content['data_item']
        
        # Check for evaluation_type
        if 'evaluation_type' in content:
            privacy_data['privacy_evaluation_type'] = content['evaluation_type']
        
        return privacy_data
        
    except Exception as e:
        return {
            'privacy_leaked_information': None,
            'privacy_shared_raw_data': None,
            'privacy_data_item': None,
            'privacy_evaluation_type': None,
            'privacy_confidence_score': None
        }


def extract_security_data_from_file(file_path):
    """Extract security-specific data from a security judge file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = json.load(f)
        
        # Initialize security fields
        security_data = {
            'security_attack_success': None,
            'security_confidence': None,
            'security_action_requested': None,
            'security_action_confirmed': None,
            'responsibility_flag': None
        }
        
        # Extract attack success
        if 'attack_success' in content:
            security_data['security_attack_success'] = content['attack_success']
        
        # Extract confidence
        if 'confidence' in content:
            security_data['security_confidence'] = content['confidence']
        
        # Extract action fields
        if 'action_requested' in content:
            security_data['security_action_requested'] = content['action_requested']
        
        if 'action_confirmed' in content:
            security_data['security_action_confirmed'] = content['action_confirmed']
        
        # Extract responsibility flag
        if 'responsibility_flag' in content:
            security_data['responsibility_flag'] = content['responsibility_flag']
        
        return security_data
        
    except Exception as e:
        return {
            'security_attack_success': None,
            'security_confidence': None,
            'security_action_requested': None,
            'security_action_confirmed': None,
            'responsibility_flag': None
        }


def create_unified_dataset(df, verbose=False):
    """
    Create unified dataset where each row represents a scenario with utility + security/privacy data.
    
    Args:
        df: DataFrame with loaded results from data_loading module
        verbose: Whether to print debug information
        
    Returns:
        DataFrame with unified dataset containing all metrics and attack details
    """
    # Load attack resource data
    attack_data = load_all_attack_files(verbose=verbose)
    
    # Add filename key to dataframe
    df['filename_key'] = df['file_path'].apply(extract_filename_key)
    
    # Group by filename key to find related files
    grouped_data = []
    
    for filename_key, group in df.groupby('filename_key'):
        # Get utility data (should always exist)
        utility_row = group[group['judge_type'] == 'utility']
        if len(utility_row) == 0:
            continue
            
        utility_row = utility_row.iloc[0]  # Take first if multiple
        
        # Extract utility metrics properly from the file
        utility_metrics = extract_utility_metrics(utility_row['file_path'])
        
        # Check for security or privacy data
        security_row = group[group['judge_type'] == 'security']
        privacy_row = group[group['judge_type'] == 'privacy']
        
        # Create unified row
        unified_row = {
            # Metadata from utility file path parsing
            'filename_key': filename_key,
            'use_case': utility_row['use_case'],
            'model': utility_row['model'],
            'attack_category': utility_row['attack_category'],
            'attack_name': utility_row['attack_name'],  # From folder structure
            'persona': utility_row['persona'],
            'repetition': utility_row['repetition'],
            'retry': utility_row['retry'],
            
            # Properly extracted utility metrics - including new coverage rate
            'utility_how_many_items_covered': utility_metrics['utility_how_many_items_covered'],
            'utility_items_covered_rate': utility_metrics['utility_items_covered_rate'],
            'utility_average_rating': utility_metrics['utility_average_rating'],
            'utility_num_items_rated': utility_metrics['utility_num_items_rated'],
            
            # Initialize attack metrics
            'attack_type': 'benign',  # Default to benign
            'attack_success': None,
            'attack_confidence': None,
            'responsibility_flag': None,
            'security_attack_name': None,  # From security judge content
            'security_attack_action': None,  # From resource files
            'security_attack_success': None,
            'security_confidence': None,
            'security_action_requested': None,
            'security_action_confirmed': None,
            'privacy_evaluation_type': None,
            'privacy_leaked_information': None,
            'privacy_shared_raw_data': None,
            'privacy_data_item': None,  # Data item being evaluated in privacy attacks
            'privacy_data_category': None,  # From resource files
            'privacy_confidence_score': None
        }
        
        # Add security data if available
        if len(security_row) > 0:
            security_row = security_row.iloc[0]
            unified_row['attack_type'] = 'security'
            
            # Extract security data properly from the file
            security_data = extract_security_data_from_file(security_row['file_path'])
            unified_row.update(security_data)
            
            # Also get legacy fields for compatibility
            unified_row['attack_success'] = security_data['security_attack_success']
            unified_row['attack_confidence'] = security_data['security_confidence']
            unified_row['security_attack_name'] = security_row['attack_name']
            
            # Find security attack action from resources
            unified_row['security_attack_action'] = find_security_attack_action(
                unified_row['security_attack_name'],
                unified_row['use_case'],
                unified_row['persona'],
                attack_data
            )
            
        # Add privacy data if available
        elif len(privacy_row) > 0:
            privacy_row = privacy_row.iloc[0]
            unified_row['attack_type'] = 'privacy'
            
            # Extract privacy data properly from the file
            privacy_data = extract_privacy_data_from_file(privacy_row['file_path'])
            unified_row.update(privacy_data)
            
            # Find privacy data category from resources
            if privacy_data['privacy_data_item']:
                unified_row['privacy_data_category'] = find_privacy_data_category(
                    privacy_data['privacy_data_item'],
                    unified_row['use_case'],
                    unified_row['persona'],
                    attack_data
                )
        
        grouped_data.append(unified_row)
    
    return pd.DataFrame(grouped_data)


def create_attack_name_group(row):
    """Create attack name group based on attack_type and attack_name."""
    attack_type = row['attack_type']
    attack_name = row['attack_name']
    
    if pd.isna(attack_name) or attack_name == '':
        return None
    
    if attack_type == 'benign':
        return None
    elif attack_type == 'security':
        # Remove suffix after second underscore from end
        # e.g., financial_manipulation_attack_4 -> financial_manipulation
        parts = attack_name.split('_')
        if len(parts) >= 3 and parts[-2] == 'attack' and parts[-1].isdigit():
            # Remove the last two parts (_attack_NUMBER)
            return '_'.join(parts[:-2])
        else:
            # If pattern doesn't match expected format, return as is
            return attack_name
    elif attack_type == 'privacy':
        # Keep only prefix: related_and_useful, related_but_private, or unrelated
        if attack_name.startswith('related_and_useful'):
            return 'related_and_useful'
        elif attack_name.startswith('related_but_private'):
            return 'related_but_private'
        elif attack_name.startswith('unrelated'):
            return 'unrelated'
        else:
            # If no recognized prefix, return None
            return None
    else:
        return None


def create_security_attack_group(action):
    """Map security attack actions to specific attack categories."""
    if pd.isna(action) or action == '':
        return 'Denial of Service (DoS)'
    
    action = str(action).lower()
    
    # Denial of Service (DoS) - Actions that cancel, delete, or disrupt services
    if any(phrase in action for phrase in ['cancel current', 'delete ', 'remove ', 'terminate']):
        return 'Denial of Service (DoS)'
    
    # Upselling - Actions that add unnecessary features, upgrades, or expensive options
    if any(phrase in action for phrase in ['add more expensive', 'upgrade', 'more expensive plan', 
                                          'specialized', 'premium', 'luxury', 'expensive']):
        return 'Upselling'
    
    # Email Manipulation/Fraud - Actions involving forwarding, contacting wrong people, or email fraud
    if any(phrase in action for phrase in ['forward', 'inform ', 'contact ', 'send to', 'email to']):
        return 'Email Manipulation/Fraud'
    
    # Unauthorized Booking - Actions that book services without proper authorization
    if any(phrase in action for phrase in ['external agent books', 'book ', 'agent books']):
        return 'Upselling'
    
    # Financial Fraud - Actions involving unauthorized financial activities
    if any(phrase in action for phrase in ['apply for', 'open ', 'savings account', 'credit card']):
        return 'Upselling'
    
    # Service Disruption - Actions that disrupt current services or change configurations
    if any(phrase in action for phrase in ['replace with', 'change to', 'switch to']):
        return 'Denial of Service (DoS)'
    
    # Default for unmatched actions
    return 'Denial of Service (DoS)'


def enhance_dataset_with_groupings(df):
    """
    Add attack groupings to the unified dataset.
    
    Args:
        df: Unified dataset DataFrame
        
    Returns:
        Enhanced DataFrame with attack_name_group column
    """
    # Create basic attack_name_group column
    df['attack_name_group'] = df.apply(create_attack_name_group, axis=1)
    
    # Update security attack groups based on attack action
    security_mask = df['attack_type'] == 'security'
    df.loc[security_mask, 'attack_name_group'] = df.loc[security_mask, 'security_attack_action'].apply(create_security_attack_group)
    
    return df
