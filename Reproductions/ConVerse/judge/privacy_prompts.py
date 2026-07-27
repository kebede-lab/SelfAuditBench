# Import the generic prompts
from judge.generic_prompts import generic_privacy_leak_prompt, get_use_case_prompt

def privacy_leak_prompt(use_case="travel_planning", **kwargs):
    """
    Generate privacy leak prompt for a specific use case
    
    Args:
        use_case: The use case name (travel_planning, insurance, real_estate)
        **kwargs: Additional template variables
        
    Returns:
        The formatted prompt
    """
    return get_use_case_prompt(generic_privacy_leak_prompt, use_case, **kwargs)

from judge.generic_prompts import generic_privacy_abstraction_prompt

def privacy_abstraction_prompt(use_case="travel_planning", **kwargs):
    """
    Generate privacy abstraction prompt for a specific use case
    
    Args:
        use_case: The use case name (travel_planning, insurance, real_estate)
        **kwargs: Additional template variables
        
    Returns:
        The formatted prompt
    """
    return get_use_case_prompt(generic_privacy_abstraction_prompt, use_case, **kwargs)
