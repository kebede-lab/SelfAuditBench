import sys
import json
import os
import re
import time
import logging
from typing import Dict, List, Tuple, Optional

current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
sys.path.append(parent)

from model import LLM
from judge.utility_prompts import utility_questions_prompt, ratings_prompt
from use_cases.config import registry, UseCaseFileResolver


class UtilityJudge:
    """
    A utility judge that evaluates packages based on:
    1. Package completeness (dates, activities, items)
    2. User preference ratings from persona ratings files
    """
    
    def __init__(self, persona_id: int, llm_instance=None, llm_name="gpt-4o-2024-11-20", use_case: str = None, max_retries: int = 3, retry_delay: float = 1.0):
        """Initialize the utility judge with persona ID and LLM instance and prompts"""
        self.persona_id = persona_id
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.logger = logging.getLogger(__name__)
        
        if llm_instance is not None:
            self.llm_instance = llm_instance
        else:
            # Create a basic LLM instance if none provided
            self.llm_instance = LLM(llm_name=llm_name, config={})
        
        # Initialize use case and file resolver
        self.use_case = use_case or 'travel_planning'
        self.file_resolver = UseCaseFileResolver(base_path=parent)
        
        # Load persona ratings for this specific persona
        self.persona_ratings = self._load_persona_ratings(persona_id)
        
        self.utility_questions_prompt_func = utility_questions_prompt 
        self.ratings_prompt_func = ratings_prompt 
    
    def set_use_case(self, use_case: str):
        """Set the use case and reload persona ratings"""
        self.use_case = use_case
        self.persona_ratings = self._load_persona_ratings(self.persona_id)
        
    def _load_persona_ratings(self, persona_id: int) -> Dict:
        """Load ratings file for specific persona using config system"""
        # Get use case config
        config = registry.get_use_case(self.use_case)
        if not config:
            print(f"Warning: Unknown use case '{self.use_case}', using default ratings path")
            ratings_file = os.path.join(parent, "resources", "ratings", f"ratings_persona{persona_id}.json")
        else:
            # Use config to get ratings file path
            ratings_file = self.file_resolver.get_ratings_file(config, persona_id)
        
        if os.path.exists(ratings_file):
            try:
                with open(ratings_file, "r") as f:
                    return json.load(f)
            except (ValueError, json.JSONDecodeError) as e:
                print(f"Error loading ratings file for persona {persona_id}: {e}")
                return {}
        else:
            print(f"Warning: No ratings file found for persona {persona_id} at {ratings_file}")
            return {}
    
    def set_use_case(self, use_case: str):
        """Set the use case and reload persona ratings"""
        self.use_case = use_case
        # Reload ratings with the correct use case path
        self.persona_ratings = self._load_persona_ratings(self.persona_id)

    def _call_llm_with_json_retry(self, prompt: str, error_context: str = "LLM evaluation") -> dict:
        """
        Call LLM with retry logic for JSON parsing failures
        
        Args:
            prompt: The prompt to send to the LLM
            error_context: Context description for error messages
            
        Returns:
            dict: Parsed JSON response or error dict
        """
        last_response = None
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                # Call LLM
                response = self.llm_instance.call_model([{"role": "user", "content": prompt}])
                last_response = response
                
                # Clean response (remove markdown code blocks)
                response_text = response.strip()
                if response_text.startswith("```json"):
                    response_text = response_text[7:]
                if response_text.endswith("```"):
                    response_text = response_text[:-3]
                response_text = response_text.strip()
                
                # Try to parse JSON
                evaluation = json.loads(response_text)
                
                if attempt > 0:
                    self.logger.info(f"JSON parsing succeeded on attempt {attempt + 1}")
                
                return evaluation
                
            except json.JSONDecodeError as e:
                last_error = e
                self.logger.warning(f"JSON parsing failed on attempt {attempt + 1}: {e}")
                self.logger.warning(f"LLM response was: {response[:200]}...")
                
                if attempt < self.max_retries - 1:
                    # Add instruction to fix JSON format for next attempt
                    prompt += "\n\nIMPORTANT: Please ensure your response is valid JSON format. Do not include any text outside the JSON object."
                    time.sleep(self.retry_delay)
                    
            except Exception as e:
                last_error = e
                self.logger.error(f"Error calling LLM on attempt {attempt + 1}: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
        
        # All attempts failed
        self.logger.error(f"Failed to get valid JSON from LLM after {self.max_retries} attempts")
        return {
            "error": f"Failed to parse {error_context} response after {self.max_retries} attempts",
            "raw_response": last_response,
            "parse_error": str(last_error) if last_error else "Unknown error",
            "REASONING": f"Error in LLM evaluation: Failed to parse JSON after {self.max_retries} attempts",
            "UTILITY": {"HOW_MANY_ITEMS_COVERED": "0/0"}
        }
    
    def evaluate_utility(self, conversations_history: List[Dict], user_task: str) -> Dict:
        """
        Evaluate a single attack result - designed to be called from main.py
        
        Args:
            conversations_history: The conversation history from main.py
            
        Returns:
            Evaluation results dictionary
        """
        if not conversations_history:
            return {"error": "Empty conversation history"}
        
        # Get the final output from the last turn
        final_turn = conversations_history[-1]
        final_package_text = final_turn.get("short_answer", "")
        
        # Extract final package from the "Final output:" section if present
        if "\n\n Final output:" in final_package_text:
            final_package_text = final_package_text.split("\n\n Final output:")[-1].strip()
        
        
        # Get utility evaluation
        utility_evaluation = self.evaluate_package_utility(user_task, final_package_text)
        
        # Get ratings evaluation
        ratings_evaluation = self.evaluate_ratings(final_package_text)
        
        # Combine both evaluations
        combined_evaluation = {
            "persona_id": self.persona_id,
            "utility_evaluation": utility_evaluation,
            "ratings_evaluation": ratings_evaluation,
            "final_package_text": final_package_text
        }
        
        return combined_evaluation
    


    def evaluate_package_utility(self, user_task: str, final_package_text: str) -> Dict:
        """
        Evaluation function that calls the LLM judge 
        """
    
        
        # Format the utility questions prompt using the appropriate use case
        formatted_prompt = self.utility_questions_prompt_func(
            use_case=self.use_case,
            final_package_text=final_package_text,
            user_task=user_task
        )
        
        # Call LLM with the utility questions prompt and retry logic
        llm_evaluation = self._call_llm_with_json_retry(formatted_prompt, "utility evaluation")
        
        return llm_evaluation 
    
    def evaluate_ratings(self, final_package_text: str) -> Dict:
        """
        Evaluation function that calls the LLM that would map the ratings 
        """
        # Convert persona ratings to a string format for the LLM
        ground_truth_ratings = json.dumps(self.persona_ratings, indent=2)
        
        # Format the ratings prompt using the appropriate use case
        formatted_prompt = self.ratings_prompt_func(
            use_case=self.use_case,
            final_package_text=final_package_text,
            ground_truth_ratings=ground_truth_ratings
        )
        
        # Call LLM with the ratings prompt and retry logic
        ratings_evaluation = self._call_llm_with_json_retry(formatted_prompt, "ratings evaluation")
        
        # If there was an error, return early with error structure
        if "error" in ratings_evaluation:
            return {
                "error": ratings_evaluation["error"],
                "llm_ratings_evaluation": {
                    "REASONING": ratings_evaluation.get("REASONING", "Error in LLM evaluation"),
                    "RATINGS": {}
                },
                "ratings_mapping": {},
                "average_rating": 0,
                "num_items_rated": 0,
                "raw_response": ratings_evaluation.get("raw_response"),
                "parse_error": ratings_evaluation.get("parse_error")
            }
        
        # Extract the ratings mapping
        ratings_mapping = ratings_evaluation.get("RATINGS", {})
        
        # Calculate average rating from the mapped items
        if ratings_mapping:
            ratings_values = [v for v in ratings_mapping.values() if isinstance(v, (int, float))]
            average_rating = sum(ratings_values) / len(ratings_values) if ratings_values else 0
        else:
            average_rating = 0
        
        return {
            "llm_ratings_evaluation": ratings_evaluation,
            "ratings_mapping": ratings_mapping,
            "average_rating": round(average_rating, 2),
            "num_items_rated": len(ratings_mapping)
        }
