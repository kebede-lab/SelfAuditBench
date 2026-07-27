# Import the generic prompts
from judge.generic_prompts import generic_utility_questions_prompt, generic_ratings_prompt, get_use_case_prompt, USE_CASE_CONFIGS



def utility_questions_prompt(use_case="travel_planning", package_format=None, **kwargs):
    """
    Generate utility questions prompt for a specific use case
    
    Args:
        use_case: The use case name (travel_planning, insurance, real_estate)
        package_format: The expected package format (if None, uses config default)
        **kwargs: Additional template variables
        
    Returns:
        The formatted prompt
    """
    # If no package_format provided, use the one from the use case config
    if package_format is None:
        config = USE_CASE_CONFIGS.get(use_case, USE_CASE_CONFIGS["travel_planning"])
        package_format = config["package_format"]
    
    return get_use_case_prompt(generic_utility_questions_prompt, use_case, package_format=package_format, **kwargs)

def ratings_prompt(use_case="travel_planning", **kwargs):
    """
    Generate ratings prompt for a specific use case
    
    Args:
        use_case: The use case name (travel_planning, insurance, real_estate)
        **kwargs: Additional template variables
        
    Returns:
        The formatted prompt
    """
    return get_use_case_prompt(generic_ratings_prompt, use_case, **kwargs)