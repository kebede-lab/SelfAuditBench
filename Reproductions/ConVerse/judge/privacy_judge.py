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
from judge.privacy_prompts import privacy_leak_prompt, privacy_abstraction_prompt
from use_cases.config import registry, UseCaseFileResolver


class PrivacyJudge:
    """
    A privacy judge that evaluates whether the AI assistant leaked private information 
    based on:
    1. Extraction snippets for unrelated/private data (should never be leaked)
    2. Raw data vs acceptable abstraction for related_and_useful data
    """
    
    def __init__(self, persona_id: int, llm_instance=None, llm_name="gpt-4o-2024-11-20", use_case: str = None, max_retries: int = 3, retry_delay: float = 1.0):
        """Initialize the privacy judge with persona ID and LLM instance"""
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
        
        # Load privacy attacks data for this specific persona
        self.privacy_attacks = self._load_privacy_attacks(persona_id)
        
        # Store the prompt functions
        self.privacy_leak_prompt_func = privacy_leak_prompt
        self.privacy_abstraction_prompt_func = privacy_abstraction_prompt
    
    def set_use_case(self, use_case: str):
        """Set the use case and reload privacy attacks"""
        self.use_case = use_case
        self.privacy_attacks = self._load_privacy_attacks(self.persona_id)
        
    def _load_privacy_attacks(self, persona_id: int) -> Dict:
        """Load privacy attacks file for specific persona using config system"""
        # Get use case config
        config = registry.get_use_case(self.use_case)
        if not config:
            print(f"Warning: Unknown use case '{self.use_case}', using default privacy attacks path")
            attacks_file = os.path.join(parent, "resources", "privacy_attacks", f"privacy_attacks_persona{persona_id}.json")
        else:
            # Use config to get privacy attacks file path
            attacks_file = self.file_resolver.get_privacy_attacks_file(config, persona_id)
        
        if os.path.exists(attacks_file):
            try:
                with open(attacks_file, "r") as f:
                    return json.load(f)
            except (ValueError, json.JSONDecodeError) as e:
                print(f"Error loading privacy attacks file for persona {persona_id}: {e}")
                return {}
        else:
            print(f"Warning: No privacy attacks file found for persona {persona_id} at {attacks_file}")
            return {}

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
            "parse_error": str(last_error) if last_error else "Unknown error"
        }
    
    
    def _extract_assistant_external_conversation(self, conversations_history: List[Dict]) -> str:
        """Extract only the conversation between assistant and external agent"""
        conversation_text = ""
        
        for turn in conversations_history:
            # Only include conversations between assistant and external agent
            if (turn.get("from") == "assistant" and turn.get("to") == "external_agent"):
                conversation_text += f"\nAssistant: {turn.get('short_answer', '')}"
            elif (turn.get("from") == "external_agent" and turn.get("to") == "assistant"):
                conversation_text += f"\nExternal Agent: {turn.get('short_answer', '')}"
        
        return conversation_text.strip()
    
    def _find_attack_data(self, attack_name: str) -> Optional[Dict]:
        """Find the specific attack data from privacy attacks"""
        if not self.privacy_attacks or "categories" not in self.privacy_attacks:
            return None
        
        # Parse attack name to find the data item
        # Format is typically: category_data_item_name
        categories = self.privacy_attacks["categories"]
        
        for category_name, category_data in categories.items():
            for item in category_data.get("items", []):
                # Match by data item name (converted to lowercase with underscores)
                item_name_formatted = item["data_item"].lower().replace(" ", "_")
                if item_name_formatted in attack_name.lower():
                    return {
                        "category": category_name,
                        "data_item": item["data_item"],
                        "item_data": item
                    }
        
        return None
    
    def evaluate_privacy(self, conversations_history: List[Dict], attack_name: str) -> Dict:
        """
        Evaluate privacy leakage for a specific attack
        
        Args:
            conversations_history: The conversation history from main.py
            attack_name: The name of the privacy attack being evaluated
            
        Returns:
            Privacy evaluation results dictionary
        """
        if not conversations_history:
            return {"error": "Empty conversation history"}
        
        # Extract conversation between assistant and external agent
        assistant_external_conversation = self._extract_assistant_external_conversation(conversations_history)
        
        if not assistant_external_conversation:
            return {"error": "No conversation found between assistant and external agent"}
        
        # Find the attack data
        attack_data = self._find_attack_data(attack_name)
        
        if not attack_data:
            return {"error": f"Attack data not found for attack: {attack_name}"}
        
        # Determine evaluation type based on category
        category = attack_data["category"]
        item_data = attack_data["item_data"]
        
        if category in ["unrelated_to_travel", "unrelated_to_insurance", "unrelated_to_real_estate", "related_but_private"]:
            # Evaluate for information leakage (should never be shared)
            return self.evaluate_information_leak(
                assistant_external_conversation,
                item_data.get("extraction_snippets", []),
                item_data.get("data_item", ""),
                item_data.get("attack_action", "")
            )
        elif category == "related_and_useful":
            # Evaluate for appropriate abstraction
            return self.evaluate_abstraction_appropriateness(
                assistant_external_conversation,
                item_data.get("raw_data", []),
                item_data.get("acceptable_abstraction", ""),
                item_data.get("data_item", ""),
                item_data.get("attack_action", "")
            )
        else:
            return {"error": f"Unknown category: {category}"}
    
    def evaluate_information_leak(self, conversation: str, extraction_snippets: List[str], 
                                data_item: str, attack_action: str) -> Dict:
        """
        Evaluate if the assistant leaked information that should never be shared
        """
        # Format extraction snippets for the prompt
        snippets_text = "\n".join([f"- {snippet}" for snippet in extraction_snippets])
        
        # Format the prompt using the appropriate use case
        formatted_prompt = self.privacy_leak_prompt_func(
            use_case=self.use_case,
            data_item=data_item,
            attack_action=attack_action,
            extraction_snippets=snippets_text,
            conversation=conversation
        )
        
        # Call LLM with retry logic
        evaluation_result = self._call_llm_with_json_retry(formatted_prompt, "information leak evaluation")
        
        return {
            "evaluation_type": "information_leak",
            "data_item": data_item,
            "extraction_snippets": extraction_snippets,
            "llm_evaluation": evaluation_result,
            "conversation_analyzed": conversation
        }
    
    def evaluate_abstraction_appropriateness(self, conversation: str, raw_data: List[str], 
                                           acceptable_abstraction: str, data_item: str, 
                                           attack_action: str) -> Dict:
        """
        Evaluate if the assistant appropriately abstracted information vs sharing raw data
        """
        # Format raw data for the prompt
        raw_data_text = "\n".join([f"- {data}" for data in raw_data])
        
        # Format the prompt using the appropriate use case
        formatted_prompt = self.privacy_abstraction_prompt_func(
            use_case=self.use_case,
            data_item=data_item,
            attack_action=attack_action,
            raw_data=raw_data_text,
            acceptable_abstraction=acceptable_abstraction,
            conversation=conversation
        )
        
        # Call LLM with retry logic
        evaluation_result = self._call_llm_with_json_retry(formatted_prompt, "abstraction appropriateness evaluation")
        
        return {
            "evaluation_type": "abstraction_appropriateness",
            "data_item": data_item,
            "raw_data": raw_data,
            "acceptable_abstraction": acceptable_abstraction,
            "llm_evaluation": evaluation_result,
            "conversation_analyzed": conversation
        }