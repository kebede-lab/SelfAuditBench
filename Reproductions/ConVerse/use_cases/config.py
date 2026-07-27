"""
Use Case Configuration System

This module defines the configuration structure for different use cases
(travel planning, real estate, insurance, etc.)
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
from abc import ABC, abstractmethod
import os


@dataclass
class UseCaseConfig:
    """Configuration for a specific use case"""
    name: str
    external_agent_role: str
    resource_folder: str
    options_file: str
    env_file_pattern: str  # e.g., "env_persona{}.txt"
    security_attacks_pattern: str  # e.g., "security_attacks/security_attacks_persona{}.json"
    privacy_attacks_pattern: str  # e.g., "privacy_attacks/privacy_attacks_persona{}.json"
    ratings_pattern: str  # e.g., "ratings/ratings_persona{}.json"
    supported_personas: List[int]
    description: str = ""


class UseCaseRegistry:
    """Registry for managing different use cases"""
    
    def __init__(self):
        self.use_cases: Dict[str, UseCaseConfig] = {}
        self._register_default_use_cases()
    
    def _register_default_use_cases(self):
        """Register the default use cases"""
        
        # Travel Planning Use Case
        self.register_use_case(UseCaseConfig(
            name="travel_planning",
            external_agent_role="Travel agency",
            resource_folder="resources/travel_planning_usecase",
            options_file="options.txt",
            env_file_pattern="env_persona{}.txt",
            security_attacks_pattern="security_attacks/security_attacks_persona{}.json",
            privacy_attacks_pattern="privacy_attacks/privacy_attacks_persona{}.json",
            ratings_pattern="ratings/ratings_persona{}.json",
            supported_personas=[1, 2, 3, 4],
            description="Travel planning and booking simulation"
        ))
        
        # Real Estate Use Case
        self.register_use_case(UseCaseConfig(
            name="real_estate",
            external_agent_role="Real estate agent",
            resource_folder="resources/real_estate_usecase",
            options_file="options.txt",
            env_file_pattern="env_persona{}.txt",
            security_attacks_pattern="security_attacks/security_attacks_persona{}.json",
            privacy_attacks_pattern="privacy_attacks/privacy_attacks_persona{}.json",
            ratings_pattern="ratings/ratings_persona{}.json",
            supported_personas=[1, 2, 3, 4],
            description="Real estate buying/renting simulation"
        ))
        
        # Insurance Use Case
        self.register_use_case(UseCaseConfig(
            name="insurance",
            external_agent_role="Insurance agent",
            resource_folder="resources/insurance_usecase",
            options_file="options.txt",
            env_file_pattern="env_persona{}.txt",
            security_attacks_pattern="security_attacks/security_attacks_persona{}.json",
            privacy_attacks_pattern="privacy_attacks/privacy_attacks_persona{}.json",
            ratings_pattern="ratings/ratings_persona{}.json",  # Note: different pattern for insurance
            supported_personas=[1, 2, 3, 4],
            description="Insurance policy recommendation and purchase simulation"
        ))
    
    def register_use_case(self, config: UseCaseConfig):
        """Register a new use case"""
        self.use_cases[config.name] = config
    
    def get_use_case(self, name: str) -> Optional[UseCaseConfig]:
        """Get use case configuration by name"""
        return self.use_cases.get(name)
    
    def list_use_cases(self) -> List[str]:
        """List all available use cases"""
        return list(self.use_cases.keys())
    
    def get_use_case_for_persona(self, use_case_name: str, persona_id: int) -> Optional[UseCaseConfig]:
        """Get use case config and validate persona support"""
        config = self.get_use_case(use_case_name)
        if config and persona_id in config.supported_personas:
            return config
        return None


class UseCaseFileResolver:
    """Resolves file paths for different use cases"""
    
    def __init__(self, base_path: str = ""):
        self.base_path = base_path
    
    def resolve_file_path(self, config: UseCaseConfig, pattern: str, persona_id: int) -> str:
        """Resolve the full file path for a given pattern and persona"""
        full_path = os.path.join(self.base_path, config.resource_folder, pattern.format(persona_id))
        return full_path
    
    def get_env_file(self, config: UseCaseConfig, persona_id: int) -> str:
        """Get environment file path"""
        return self.resolve_file_path(config, config.env_file_pattern, persona_id)
    
    def get_security_attacks_file(self, config: UseCaseConfig, persona_id: int) -> str:
        """Get security attacks file path"""
        return self.resolve_file_path(config, config.security_attacks_pattern, persona_id)
    
    def get_privacy_attacks_file(self, config: UseCaseConfig, persona_id: int) -> str:
        """Get privacy attacks file path"""
        return self.resolve_file_path(config, config.privacy_attacks_pattern, persona_id)
    
    def get_ratings_file(self, config: UseCaseConfig, persona_id: int) -> str:
        """Get ratings file path"""
        return self.resolve_file_path(config, config.ratings_pattern, persona_id)
    
    def get_options_file(self, config: UseCaseConfig) -> str:
        """Get options file path"""
        return os.path.join(self.base_path, config.resource_folder, config.options_file)


# Global registry instance
registry = UseCaseRegistry()
