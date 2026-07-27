import json
import os
import logging
import sys
import time
from .security_prompts import security_final_package_prompt, security_toolkit_actions_prompt

# Add parent directory to path for config imports
current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
sys.path.append(parent)

from use_cases.config import registry, UseCaseFileResolver

class SecurityJudge:
    def __init__(self, persona_id, llm_instance, use_case: str = None, max_retries: int = 3, retry_delay: float = 1.0):
        self.persona_id = persona_id
        self.llm_instance = llm_instance
        self.logger = logging.getLogger(__name__)
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        # Initialize use case and file resolver
        self.use_case = use_case or 'travel_planning'
        self.file_resolver = UseCaseFileResolver(base_path=parent)
        
        # Store prompt functions
        self.security_final_package_prompt_func = security_final_package_prompt
        self.security_toolkit_actions_prompt_func = security_toolkit_actions_prompt
        
        # Load security attacks for the persona
        self.security_attacks = self._load_security_attacks()
    
    def set_use_case(self, use_case: str):
        """Set the use case and reload security attacks"""
        self.use_case = use_case
        self.security_attacks = self._load_security_attacks()
        
    def _load_security_attacks(self):
        """Load security attacks for the specific persona using config system"""
        try:
            # Get use case config
            config = registry.get_use_case(self.use_case)
            if not config:
                self.logger.warning(f"Unknown use case '{self.use_case}', using default security attacks path")
                attacks_file = f"resources/security_attacks/security_attacks_persona{self.persona_id}.json"
            else:
                # Use config to get security attacks file path
                attacks_file = self.file_resolver.get_security_attacks_file(config, self.persona_id)
            
            if not os.path.exists(attacks_file):
                self.logger.warning(f"Security attacks file not found: {attacks_file}")
                return {}
                
            with open(attacks_file, 'r') as f:
                data = json.load(f)
                return data.get('security_attacks', {})
        except Exception as e:
            self.logger.error(f"Error loading security attacks: {e}")
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
                cleaned_response = response.strip()
                if cleaned_response.startswith("```json"):
                    cleaned_response = cleaned_response[7:]
                if cleaned_response.endswith("```"):
                    cleaned_response = cleaned_response[:-3]
                cleaned_response = cleaned_response.strip()
                
                # Try to parse JSON
                evaluation = json.loads(cleaned_response)
                
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
            "attack_success": "Failed",
            "confidence": 0.0,
            "raw_response": last_response,
            "parse_error": str(last_error) if last_error else "Unknown error"
        }
    
    def evaluate_security(self, attack_name, final_package=None, conversation_history=None):
        """
        Main evaluation method that routes to appropriate evaluation based on responsibility flag
        
        Args:
            attack_name: Name of the attack to evaluate
            final_package: The final travel package (for final package attacks)
            conversation_history: Full conversation history (to extract assistant-env communication)
        
        Returns:
            dict: Security evaluation results
        """
        try:
            # Find the attack information
            attack_info = self._find_attack_by_name(attack_name)
            if not attack_info:
                self.logger.error(f"Attack '{attack_name}' not found for persona {self.persona_id}")
                return {
                    "error": f"Attack '{attack_name}' not found",
                    "attack_success": "Failed",
                    "confidence": 0.0
                }
            
            responsibility_flag = attack_info.get('responsibility_flag', '')
            
            if responsibility_flag == "EXTERNAL_AGENT_OPTIONS":
                return self.evaluate_final_package_attack(attack_info, final_package)
            elif responsibility_flag == "AI_ASSISTANT_TOOLKIT_ACTION":
                return self.evaluate_toolkit_attack(attack_info, conversation_history)
            else:
                self.logger.error(f"Unknown responsibility flag: {responsibility_flag}")
                return {
                    "error": f"Unknown responsibility flag: {responsibility_flag}",
                    "attack_success": "Failed",
                    "confidence": 0.0
                }
                
        except Exception as e:
            self.logger.error(f"Error in security evaluation: {e}")
            return {
                "error": str(e),
                "attack_success": "Failed",
                "confidence": 0.0
            }
    
    def _find_attack_by_name(self, attack_name):
        """Find attack information by name across all attack categories"""
        for category, attacks in self.security_attacks.items():
            for attack_key, attack_info in attacks.items():
                # Check for exact attack key match
                if attack_key == attack_name:
                    return attack_info
                
                # Check for attack name match (from the "name" field)
                if attack_info.get('name') == attack_name:
                    return attack_info
                
                # Check for formatted attack name match (category_attack_key)
                formatted_name = f"{category}_{attack_key}"
                if formatted_name == attack_name:
                    return attack_info
                    
        return None
    
    def evaluate_final_package_attack(self, attack_info, final_package):
        """
        Evaluate final package attacks (EXTERNAL_AGENT_OPTIONS)
        Checks if the final package includes the attack goal
        """
        if not final_package:
            return {
                "error": "Final package required for final package attack evaluation",
                "attack_success": "Failed",
                "confidence": 0.0
            }
        
        try:
            # Prepare prompt with attack information using use case
            prompt = self.security_final_package_prompt_func(
                use_case=self.use_case,
                attack_name=attack_info.get('name', ''),
                attack_action=attack_info.get('attack_action', ''),
                legitimate_action=attack_info.get('legitimate_action', ''),
                final_package=json.dumps(final_package, indent=2) if isinstance(final_package, dict) else str(final_package)
            )
            
            # Get LLM evaluation with retry logic
            evaluation = self._call_llm_with_json_retry(prompt, "final package attack evaluation")
            
            # Add metadata if evaluation was successful
            if "error" not in evaluation:
                evaluation.update({
                    "evaluation_type": "final_package_attack",
                    "responsibility_flag": "EXTERNAL_AGENT_OPTIONS",
                    "attack_name": attack_info.get('name', ''),
                    "attack_category": self._get_attack_category(attack_info.get('name', ''))
                })
            
            return evaluation
                
        except Exception as e:
            self.logger.error(f"Error in final package attack evaluation: {e}")
            return {
                "error": str(e),
                "attack_success": "Failed",
                "confidence": 0.0
            }
    
    def evaluate_toolkit_attack(self, attack_info, conversation_history):
        """
        Evaluate toolkit attacks (AI_ASSISTANT_TOOLKIT_ACTION)
        Checks assistant-environment communication for unauthorized actions
        """
        if not conversation_history:
            return {
                "error": "Conversation history required for toolkit attack evaluation",
                "attack_success": "Failed",
                "confidence": 0.0
            }
        
        try:
            # Extract assistant-environment communication
            assistant_env_communication = self._extract_assistant_env_communication(conversation_history)
            
            # Prepare prompt with attack information using use case
            prompt = self.security_toolkit_actions_prompt_func(
                use_case=self.use_case,
                legitimate_action=attack_info.get('legitimate_action', ''),
                attack_name=attack_info.get('name', ''),
                attack_action=attack_info.get('attack_action', ''),
                attack_rationale=attack_info.get('attack_rationale', ''),
                assistant_env_communication=assistant_env_communication
            )
            
            # Get LLM evaluation with retry logic
            evaluation = self._call_llm_with_json_retry(prompt, "toolkit attack evaluation")
            
            # Add metadata if evaluation was successful
            if "error" not in evaluation:
                evaluation.update({
                    "evaluation_type": "toolkit_attack",
                    "responsibility_flag": "AI_ASSISTANT_TOOLKIT_ACTION",
                    "attack_name": attack_info.get('name', '')
                })
            
            return evaluation
                
        except Exception as e:
            self.logger.error(f"Error in toolkit attack evaluation: {e}")
            return {
                "error": str(e),
                "attack_success": "Failed",
                "confidence": 0.0
            }
    
    def _extract_assistant_env_communication(self, conversation_history):
        """
        Extract only assistant-environment communication from conversation history
        Filters out assistant-user and user-assistant interactions
        """
        conversation_text = ""
        
        for turn in conversation_history:
            # Only include conversations between assistant and environment
            if (turn.get("from") == "assistant" and turn.get("to") == "environment"):
                conversation_text += f"\nAssistant: {turn.get('short_answer', '')}"
            elif (turn.get("from") == "environment" and turn.get("to") == "assistant"):
                conversation_text += f"\nEnvironment: {turn.get('short_answer', '')}"
        
        return conversation_text.strip()

    
    def _get_attack_category(self, attack_name):
        """Get the category of an attack by searching through all categories"""
        for category, attacks in self.security_attacks.items():
            for attack_key, attack_info in attacks.items():
                # Check for exact attack key match
                if attack_key == attack_name:
                    return category
                
                # Check for attack name match (from the "name" field)
                if attack_info.get('name') == attack_name:
                    return category
                
                # Check for formatted attack name match (category_attack_key)
                formatted_name = f"{category}_{attack_key}"
                if formatted_name == attack_name:
                    return category
                    
        return "unknown"
