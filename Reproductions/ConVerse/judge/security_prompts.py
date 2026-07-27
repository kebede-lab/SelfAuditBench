# Security evaluation prompts for LLM-based security attack evaluation

# Import the generic prompts
from judge.generic_prompts import generic_security_final_package_prompt, get_use_case_prompt

def security_final_package_prompt(use_case="travel_planning", **kwargs):
    """
    Generate security final package prompt for a specific use case
    
    Args:
        use_case: The use case name (travel_planning, insurance, real_estate)
        **kwargs: Additional template variables
        
    Returns:
        The formatted prompt
    """
    return get_use_case_prompt(generic_security_final_package_prompt, use_case, **kwargs)

from judge.generic_prompts import generic_security_toolkit_actions_prompt

def security_toolkit_actions_prompt(use_case="travel_planning", **kwargs):
    """
    Generate security toolkit actions prompt for a specific use case
    
    Args:
        use_case: The use case name (travel_planning, insurance, real_estate)
        **kwargs: Additional template variables
        
    Returns:
        The formatted prompt
    """
    return get_use_case_prompt(generic_security_toolkit_actions_prompt, use_case, **kwargs)
