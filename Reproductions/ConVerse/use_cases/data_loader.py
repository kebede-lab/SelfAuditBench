"""
Data loading utilities for different use cases
"""

import json
import os
from typing import Dict, Tuple, Optional
from use_cases.config import registry, UseCaseFileResolver


def load_persona_data_for_use_case(use_case_name: str, persona_id: int, 
                                 base_path: str = "") -> Tuple[str, Dict, Dict, str]:
    """
    Load persona environment and attack data for a specific use case
    
    Args:
        use_case_name: Name of the use case (travel_planning, real_estate, insurance)
        persona_id: ID of the persona (1, 2, 3, 4)
        base_path: Base path for file resolution
    
    Returns:
        Tuple of (persona_env_file_path, security_attacks, privacy_attacks, user_task)
    """
    
    # Get use case configuration
    config = registry.get_use_case_for_persona(use_case_name, persona_id)
    if not config:
        raise ValueError(f"Use case '{use_case_name}' not found or persona {persona_id} not supported")
    
    # Initialize file resolver
    resolver = UseCaseFileResolver(base_path)
    
    # Get file paths
    persona_env_file = resolver.get_env_file(config, persona_id)
    security_attacks_file = resolver.get_security_attacks_file(config, persona_id)
    privacy_attacks_file = resolver.get_privacy_attacks_file(config, persona_id)
    
    # Load security attacks
    try:
        with open(security_attacks_file, "r") as f:
            security_attacks_data = json.load(f)
            persona_security_attacks = security_attacks_data.get("security_attacks", {})
            user_task = security_attacks_data.get("representative_user_task", {}).get("base_request", "")
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
        print(f"Error loading security attacks for {use_case_name} persona {persona_id}: {e}")
        persona_security_attacks = {}
        user_task = ""
    
    # Load privacy attacks
    try:
        with open(privacy_attacks_file, "r") as f:
            privacy_attacks_data = json.load(f)
            # Handle different file structures for different use cases
            if "categories" in privacy_attacks_data:
                persona_privacy_attacks = privacy_attacks_data
            else:
                # Assume it's a flat structure, wrap it
                persona_privacy_attacks = {"categories": privacy_attacks_data}
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error loading privacy attacks for {use_case_name} persona {persona_id}: {e}")
        persona_privacy_attacks = {"categories": {}}
    
    return persona_env_file, persona_security_attacks, persona_privacy_attacks, user_task


def load_options_file_for_use_case(use_case_name: str, base_path: str = "") -> str:
    """
    Load the options file for a specific use case
    
    Args:
        use_case_name: Name of the use case
        base_path: Base path for file resolution
    
    Returns:
        Content of the options file
    """
    
    # Get use case configuration
    config = registry.get_use_case(use_case_name)
    if not config:
        raise ValueError(f"Use case '{use_case_name}' not found")
    
    # Initialize file resolver
    resolver = UseCaseFileResolver(base_path)
    
    # Get options file path
    options_file = resolver.get_options_file(config)
    
    # Load options file
    try:
        with open(options_file, "r") as f:
            return f.read()
    except FileNotFoundError as e:
        print(f"Error loading options file for {use_case_name}: {e}")
        return ""


def get_external_agent_role_for_use_case(use_case_name: str) -> str:
    """
    Get the external agent role for a specific use case
    
    Args:
        use_case_name: Name of the use case
    
    Returns:
        External agent role string
    """
    
    config = registry.get_use_case(use_case_name)
    if config:
        return config.external_agent_role
    else:
        print(f"Use case '{use_case_name}' not found, using default role")
        return "External agent"


def validate_use_case_and_persona(use_case_name: str, persona_id: int) -> bool:
    """
    Validate that a use case exists and supports the given persona
    
    Args:
        use_case_name: Name of the use case
        persona_id: ID of the persona
    
    Returns:
        True if valid, False otherwise
    """
    
    config = registry.get_use_case_for_persona(use_case_name, persona_id)
    return config is not None


def list_available_use_cases() -> Dict[str, Dict]:
    """
    List all available use cases with their details
    
    Returns:
        Dictionary of use case details
    """
    
    result = {}
    for name in registry.list_use_cases():
        config = registry.get_use_case(name)
        if config:
            result[name] = {
                "description": config.description,
                "external_agent_role": config.external_agent_role,
                "supported_personas": config.supported_personas
            }
    
    return result
