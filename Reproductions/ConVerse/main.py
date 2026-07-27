import sys
import json
import datetime
import os
import argparse 
import threading
import time
from user_environment.environment_agent import UserEnvironmentAgent
from assistant.assistant_agent import Assistant
from external_agent.external_agent import External
from assistant.assistant_prompts import simulation_ended

# Import judge system directly
from judge.utility_judge import UtilityJudge
from judge.privacy_judge import PrivacyJudge
from judge.security_judge import SecurityJudge

# Import use case data loading functions
from use_cases.data_loader import (
    load_persona_data_for_use_case, 
    load_options_file_for_use_case,
    get_external_agent_role_for_use_case,
    validate_use_case_and_persona,
    list_available_use_cases
)

from model import LLM
from utils import Logger, log_conversations

# Import new utility modules
from simulation_utils import (
    print_safe_config, 
    create_output_directory_structure,
    create_security_attack_instruction,
    create_privacy_attack_instruction,
    create_timestamped_filename,
    save_conversation_log,
    load_persona_data
)
from attack_execution import execute_simulation_based_on_type

parser = argparse.ArgumentParser(description="ConVerse Benchmark")
parser.add_argument("--logs_folder", type=str, default="logs", help="Path to the logs folder")

## Use case selection
parser.add_argument("--use_case", type=str, choices=["travel_planning", "real_estate", "insurance"], 
                   default="travel_planning", help="Use case to simulate")

## Options related to the files of each persona 
parser.add_argument("--persona_id", type=int, default=1, help="Persona ID, this will be used to read the corresponding files")

## Options related to the design of the assistant 
parser.add_argument("--baseline_mode", action="store_true", help="Enable baseline mode")
parser.add_argument("--taskconfined_mode", action="store_true", help="Enable task-confined mode")

## Options related to the agents LLM
parser.add_argument("--llm_name", type=str, default="gpt-3.5-turbo", help="Name of the LLM model for agents")
parser.add_argument("--provider", type=str, choices=["azure", "openai", "anthropic", "anthropic_vertex", "google", "huggingface"], help="LLM provider (auto-detected if not specified)")
parser.add_argument("--azure_endpoint", type=str, help="Azure endpoint URL (overrides environment variable)")
parser.add_argument("--use_azure_credentials", action="store_true", default=True, help="Use DefaultAzureCredential for Azure (recommended)")

## Options related to the judge LLM
parser.add_argument("--judge_llm_name", type=str, default="gpt-4o-2024-11-20", help="Name of the LLM model for judge")
parser.add_argument("--judge_provider", type=str, choices=["azure", "openai", "anthropic", "anthropic_vertex", "google", "huggingface"], help="Judge LLM provider (auto-detected if not specified)")
parser.add_argument("--judge_azure_endpoint", type=str, help="Judge Azure endpoint URL (overrides environment variable)")
parser.add_argument("--judge_use_azure_credentials", action="store_true", default=True, help="Use DefaultAzureCredential for Judge Azure (recommended)")

## Options related to the design of the external agent and attacks 
# External agent role will be determined by use case, but can be overridden
parser.add_argument("--external_agent_role", type=str, default="", help="Role of the external agent (auto-determined from use case if not specified)")
parser.add_argument("--simulation_type", type=str, choices=["security", "privacy", "benign_easy", "benign_hard"], default="benign_hard", help="Type of attack to run")
parser.add_argument("--attack_name", type=str, default="", help="Specific attack name to run (leave empty to run all)")
parser.add_argument("--run_all_attacks", action="store_true", help="Run all attacks for the specified persona and attack type")

parser.add_argument("--enable_utility_judge", action="store_true", default=True, help="Enable utility judge evaluation after each attack")
parser.add_argument("--enable_privacy_judge", action="store_true", default=True, help="Enable privacy judge evaluation after each privacy attack")
parser.add_argument("--enable_security_judge", action="store_true", default=True, help="Enable security judge evaluation after each security attack")
parser.add_argument("--judge_max_retries", type=int, default=3, help="Maximum number of retries for judge JSON parsing failures")
parser.add_argument("--judge_retry_delay", type=float, default=1.0, help="Delay in seconds between judge retry attempts")
parser.add_argument("--repetitions", type=int, default=3, help="Number of times to run each attack to account for LLM randomness")
parser.add_argument("--simulation_timeout", type=int, default=600, help="Timeout in seconds for individual simulation runs (default: 600 = 10 minutes)")

args = parser.parse_args()

# Timeout handler for simulation timeouts
class TimeoutError(Exception):
    pass

class SimulationTimeout:
    def __init__(self, timeout_seconds):
        self.timeout_seconds = timeout_seconds
        self.timer = None
        self.timed_out = False
        
    def _timeout_handler(self):
        self.timed_out = True
        
    def start(self):
        self.timed_out = False
        self.timer = threading.Timer(self.timeout_seconds, self._timeout_handler)
        self.timer.start()
        
    def stop(self):
        if self.timer:
            self.timer.cancel()
            
    def check_timeout(self):
        if self.timed_out:
            raise TimeoutError(f"Simulation timed out after {self.timeout_seconds} seconds")

# Validate use case and persona
if not validate_use_case_and_persona(args.use_case, args.persona_id):
    print(f"Error: Use case '{args.use_case}' does not support persona {args.persona_id}")
    print(f"Available use cases: {list_available_use_cases()}")
    sys.exit(1)

# Set external agent role from use case if not specified
if not args.external_agent_role:
    args.external_agent_role = get_external_agent_role_for_use_case(args.use_case)
    print(f"Using external agent role from use case: {args.external_agent_role}")

# Load options file for the use case
try:
    package_options = load_options_file_for_use_case(args.use_case)
    print(f"Loaded options for use case '{args.use_case}'")
except Exception as e:
    print(f"Error: Could not load options for use case '{args.use_case}': {e}")
    sys.exit(1)

# Load persona data
persona_env_file, persona_security_attacks, persona_privacy_attacks, user_task = load_persona_data(args)

# Create LLM instance for agents (assistant, external, environment)
agent_llm_instance = LLM(llm_name=args.llm_name, config=args)
# Determine and print the actual provider being used
agent_provider = agent_llm_instance._determine_provider() if hasattr(agent_llm_instance, '_determine_provider') else getattr(args, 'provider', 'auto-detected')
print(f"Agent LLM: {args.llm_name} (Provider: {agent_provider})")
if agent_provider == "anthropic_vertex":
    print(f"  → Using Anthropic Claude via Google Cloud Vertex AI (Region: {os.getenv('GOOGLE_CLOUD_REGION', 'us-east5')})")
elif agent_provider == "anthropic":
    print(f"  → Using Anthropic Claude via direct API")
elif agent_provider == "google":
    print(f"  → Using Google Gemini API")

# Create separate config object for judge with judge-specific arguments
class JudgeConfig:
    def __init__(self, args):
        # Copy all attributes from args
        for attr in dir(args):
            if not attr.startswith('_'):
                setattr(self, attr, getattr(args, attr))
        
        # Override with judge-specific values
        self.llm_name = args.judge_llm_name
        if args.judge_provider:
            self.provider = args.judge_provider
        if args.judge_azure_endpoint:
            self.azure_endpoint = args.judge_azure_endpoint
        if hasattr(args, 'judge_use_azure_credentials'):
            self.use_azure_credentials = args.judge_use_azure_credentials

judge_config = JudgeConfig(args)
judge_llm_instance = LLM(llm_name=args.judge_llm_name, config=judge_config)
# Determine and print the actual provider being used for judge
judge_provider = judge_llm_instance._determine_provider() if hasattr(judge_llm_instance, '_determine_provider') else getattr(judge_config, 'provider', 'auto-detected')
print(f"Judge LLM: {args.judge_llm_name} (Provider: {judge_provider})")
if judge_provider == "anthropic_vertex":
    print(f"  → Using Anthropic Claude via Google Cloud Vertex AI (Region: {os.getenv('GOOGLE_CLOUD_REGION', 'us-east5')})")
elif judge_provider == "anthropic":
    print(f"  → Using Anthropic Claude via direct API")
elif judge_provider == "google":
    print(f"  → Using Google Gemini API")

# Initialize utility judge (only if enabled)
utility_judge = None
if args.enable_utility_judge:
    try:
        utility_judge = UtilityJudge(args.persona_id, judge_llm_instance, use_case=args.use_case, 
                                   max_retries=args.judge_max_retries, retry_delay=args.judge_retry_delay)
        print(f"Utility judge enabled for {args.use_case} persona {args.persona_id} (max_retries={args.judge_max_retries})")
    except Exception as e:
        print(f"Warning: Could not initialize utility judge: {e}")
        utility_judge = None

# Initialize privacy judge (only if enabled)
privacy_judge = None
if args.enable_privacy_judge:
    try:
        privacy_judge = PrivacyJudge(args.persona_id, judge_llm_instance, use_case=args.use_case,
                                   max_retries=args.judge_max_retries, retry_delay=args.judge_retry_delay)
        print(f"Privacy judge enabled for {args.use_case} persona {args.persona_id} (max_retries={args.judge_max_retries})")
    except Exception as e:
        print(f"Warning: Could not initialize privacy judge: {e}")
        privacy_judge = None

# Initialize security judge (only if enabled)
security_judge = None
if args.enable_security_judge:
    try:
        security_judge = SecurityJudge(args.persona_id, judge_llm_instance, use_case=args.use_case,
                                     max_retries=args.judge_max_retries, retry_delay=args.judge_retry_delay)
        print(f"Security judge enabled for {args.use_case} persona {args.persona_id} (max_retries={args.judge_max_retries})")
    except Exception as e:
        print(f"Warning: Could not initialize security judge: {e}")
        security_judge = None

def run_judges_for_attack(conversations_history, timestamp, attack_output_folder, judge_llm_safe_name, attack_name, user_task):
    """Helper function to run all judges for a completed attack"""
    # Utility judge
    if utility_judge is not None:
        try:
            judge_results = utility_judge.evaluate_utility(conversations_history, user_task)
            judge_filename = os.path.join(attack_output_folder, f"utility_judge_{judge_llm_safe_name}_{timestamp}.json")
            with open(judge_filename, "w") as f:
                json.dump(judge_results, f, indent=2)
            if "utility_evaluation" in judge_results and "ratings_evaluation" in judge_results:
                utility_eval = judge_results['utility_evaluation']
                ratings_eval = judge_results['ratings_evaluation']
                if 'UTILITY' in utility_eval:
                    items_covered = utility_eval['UTILITY'].get('HOW_MANY_ITEMS_COVERED', '0/0')
                    print(f"Items covered: {items_covered}")
                print(f"Average rating: {ratings_eval.get('average_rating', 0)}")
                print(f"Items rated: {ratings_eval.get('num_items_rated', 0)}")
        except Exception as e:
            print(f"Error running utility judge: {e}")
    
    # Privacy judge
    if privacy_judge is not None and args.simulation_type == "privacy":
        try:
            privacy_results = privacy_judge.evaluate_privacy(conversations_history, attack_name)
            privacy_filename = os.path.join(attack_output_folder, f"privacy_judge_{judge_llm_safe_name}_{timestamp}.json")
            with open(privacy_filename, "w") as f:
                json.dump(privacy_results, f, indent=2)
        except Exception as e:
            print(f"Error running privacy judge: {e}")
    
    # Security judge
    if security_judge is not None and args.simulation_type == "security":
        try:
            final_package = None
            if conversations_history:
                final_turn = conversations_history[-1]
                final_package_text = final_turn.get("short_answer", "")
                if "\n\n Final output:" in final_package_text:
                    final_package = final_package_text.split("\n\n Final output:")[-1].strip()
                else:
                    final_package = final_package_text
            security_results = security_judge.evaluate_security(
                attack_name=attack_name,
                final_package=final_package,
                conversation_history=conversations_history
            )
            security_filename = os.path.join(attack_output_folder, f"security_judge_{judge_llm_safe_name}_{timestamp}.json")
            with open(security_filename, "w") as f:
                json.dump(security_results, f, indent=2)
        except Exception as e:
            print(f"Error running security judge: {e}")

def run_single_attack(user_task, attack_info=None, attack_name="", max_retries=3):
    """Run a single attack simulation with retry capability for format errors and multiple repetitions for LLM randomness"""
    
    # Run the attack multiple times based on repetitions argument
    for repetition in range(args.repetitions):
        print(f"\n{'='*60}")
        print(f"Running repetition {repetition + 1}/{args.repetitions} for attack: {attack_name}")
        print(f"{'='*60}")
        
        run_single_attack_repetition(user_task, attack_info, attack_name, repetition, max_retries)

def run_single_attack_repetition(user_task, attack_info=None, attack_name="", repetition=0, max_retries=3):
    """Run a single repetition of an attack simulation with retry capability for format errors and timeout protection"""
    attack_output_folder = create_output_directory_structure(args, attack_name)
    judge_llm_safe_name = args.judge_llm_name.replace("/", "_").replace(":", "_").replace("\\", "_")
    
    # Resume each repetition independently. A successful rep1 must not suppress
    # generation of rep2..repN in the same target directory.
    repetition_marker = f"_rep{repetition + 1}"

    def matches_repetition(filename: str) -> bool:
        return filename.endswith(f"{repetition_marker}.json") or (
            f"{repetition_marker}_retry" in filename and filename.endswith(".json")
        )

    # Check if output JSON exists for this specific repetition.
    existing_output_jsons = [
        f for f in os.listdir(attack_output_folder) 
        if f.startswith("output_") and matches_repetition(f)
    ]
    
    # Check if the utility judge exists for this specific repetition and judge LLM.
    existing_utility_judges = [
        f for f in os.listdir(attack_output_folder) 
        if f.startswith(f"utility_judge_{judge_llm_safe_name}_")
        and matches_repetition(f)
    ]
    
    # If output JSON exists, check if we need to run/re-run judge
    if len(existing_output_jsons) > 0:
        # Check if judge exists and is valid
        if len(existing_utility_judges) > 0:
            # Check for errors in existing judge
            try:
                with open(os.path.join(attack_output_folder, existing_utility_judges[0]), "r") as f:
                    judge_data = json.load(f)
                # Check if there's an error key
                has_error = ("error" in judge_data or 
                           ("utility_evaluation" in judge_data and "error" in judge_data["utility_evaluation"]) or 
                           ("ratings_evaluation" in judge_data and "error" in judge_data["ratings_evaluation"]))
                if not has_error:
                    # Everything is complete and valid, skip
                    return
            except:
                pass  # Judge file is corrupt, will re-run
        
        # Load conversation history and re-run judges
        with open(os.path.join(attack_output_folder, existing_output_jsons[0]), "r") as f:
            conversations_history = json.load(f)
        timestamp = os.path.basename(existing_output_jsons[0]).replace("output_", "").replace(".json", "")
        
        # Re-run judges
        run_judges_for_attack(conversations_history, timestamp, attack_output_folder, judge_llm_safe_name, attack_name, user_task)
        return
    
    # Run full simulation with retries
    for attempt in range(max_retries):
        # Get the current timestamp and format it, include repetition number
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        timestamp += f"_rep{repetition + 1}"
        if attempt > 0:
            timestamp += f"_retry{attempt}"
        log_filename = os.path.join(attack_output_folder, f"output_{timestamp}.txt")

        # save conversations
        conversations_history = []

        # Redirect sys.stdout to the Logger object
        original_stdout = sys.stdout
        sys.stdout = Logger(log_filename)

        if attempt > 0:
            print(f"\n=== Retrying Attack: {attack_name} (Rep {repetition + 1}/{args.repetitions}, Attempt {attempt + 1}/{max_retries}) ===")
        else:
            print(f"\n=== Running Attack: {attack_name} (Rep {repetition + 1}/{args.repetitions}) ===")
        print_safe_config(args)
        if attack_info:
            print(f"Attack Info: {attack_info}")

        # Set up timeout mechanism
        timeout = SimulationTimeout(args.simulation_timeout)  
        timeout.start()
        simulation_start_time = time.time()

        try:
            simulator = UserEnvironmentAgent(
                llm_instance=agent_llm_instance,
                user_env=user_env,
                user_task=user_task,
            )
            
            assistant = Assistant(
                user_task,
                args.external_agent_role,
                agent_llm_instance,
                baseline_mode=args.baseline_mode,
                use_case=args.use_case,
            )

            # external_agent_mode is either "benign_easy", "benign_hard", or "adv"
            if args.simulation_type == "security" or args.simulation_type == "privacy":
                external_agent_mode = "adv"
            else:
                external_agent_mode = args.simulation_type
                
            external = External(
                args.external_agent_role,
                external_agent_mode,
                agent_llm_instance,
                curated_package_options=package_options,
                external_agent_additional_info=attack_info,
            )

            # generate initial plan
            print("\n=== assistant ===")
            plan_str_output, extracted_plan = assistant.generate_initial_plan()
            conversations_history.append(
                log_conversations(plan_str_output, extracted_plan, "assistant", "assistant")
            )

            previous_turn, previous_turn_str = None, None
            task_done = False

            while not task_done:
                # Check for timeout
                timeout.check_timeout()
                
                print("\n=== assistant ===")
                # start with assistant always
                if previous_turn:
                    if previous_turn.type == "external_agent_return":
                        conversations_history.append(
                            log_conversations(
                                previous_turn_str,
                                previous_turn.answer,
                                "external_agent",
                                "assistant",
                            )
                        )
                    if previous_turn.type == "environment_return":
                        conversations_history.append(
                            log_conversations(
                                previous_turn_str, previous_turn.answer, "environment", "assistant"
                            )
                        )

                # Check for timeout before assistant generation
                timeout.check_timeout()
                response, response_str = assistant.generate_turn(previous_turn)

                # check if is done
                if (
                    response.type == "assistant_return"
                    and (simulation_ended + "\n\n Final output:") in response.answer
                ):
                    task_done = True
                    conversations_history.append(
                        log_conversations(response_str, response.answer, "assistant", "assistant")
                    )
                    break

                # check if the answer is addressed to the env
                if response.type == "to_environment":
                    print("\n=== user_environment ===")
                    conversations_history.append(
                        log_conversations(response_str, response.answer, "assistant", "environment")
                    )

                    # Check for timeout before environment simulation
                    timeout.check_timeout()
                    previous_turn, previous_turn_str = simulator.simulate_env(
                        response.answer,
                    )

                # check if the answer is addressed to the external agent
                if response.type == "to_external_agent" and external:
                    print("\n=== external ===")
                    conversations_history.append(
                        log_conversations(
                            response_str, response.answer, "assistant", "external_agent"
                        )
                    )

                    # Check for timeout before external agent generation
                    timeout.check_timeout()
                    previous_turn, previous_turn_str = external.generate_turn(response)

            # Stop the timeout since simulation completed successfully
            timeout.stop()
            simulation_end_time = time.time()
            simulation_duration = simulation_end_time - simulation_start_time
            print(f"\nSimulation completed in {simulation_duration:.1f} seconds")

            conv_filename = os.path.join(attack_output_folder, f"output_{timestamp}.json")
            sys.stdout.flush()
            with open(conv_filename, "w") as f:
                json.dump(conversations_history, f)
            
            # Restore stdout before running judges
            sys.stdout = original_stdout
            
            # Run all judges using helper function
            judge_llm_safe_name = args.judge_llm_name.replace("/", "_").replace(":", "_").replace("\\", "_")
            run_judges_for_attack(conversations_history, timestamp, attack_output_folder, judge_llm_safe_name, attack_name, user_task)
                
            print(f"\nSimulation {attack_name} (Rep {repetition + 1}/{args.repetitions}) completed successfully")
            return  # Success, exit the retry loop
            
        except TimeoutError:
            timeout.stop()
            simulation_end_time = time.time()
            simulation_duration = simulation_end_time - simulation_start_time
            print(f"\nSimulation timed out after {simulation_duration:.1f} seconds")
            if attempt < max_retries - 1:
                print(f"Retrying (attempt {attempt + 2}/{max_retries})...")
            else:
                print("Max retries reached. Skipping.")
                
        except RuntimeError as e:
            timeout.stop()
            print(f"\nSimulation failed with format error: {e}")
            if attempt < max_retries - 1:
                print(f"Retrying (attempt {attempt + 2}/{max_retries})...")
            else:
                print("Max retries reached. Skipping.")
                
        except Exception as e:
            timeout.stop()
            print(f"\nSimulation failed with error: {e}")
            if attempt < max_retries - 1:
                retry_delay = min(2 ** attempt, 8)
                print(
                    f"Retrying after provider/runtime error in {retry_delay}s "
                    f"(attempt {attempt + 2}/{max_retries})..."
                )
                time.sleep(retry_delay)
            else:
                print("Max retries reached. Skipping.")
            
        finally:
            timeout.stop()
            sys.stdout = original_stdout
    
    # If we get here, all retries failed
    print(f"\nAttack {attack_name} (Rep {repetition + 1}/{args.repetitions}) failed after {max_retries} attempts")# Read persona environment
with open(persona_env_file, "r", encoding="utf-8") as file:
    user_env = file.read()

# create main output dir
os.makedirs(args.logs_folder, exist_ok=True)

# Run attacks based on type and mode using the utility function
execute_simulation_based_on_type(args, persona_security_attacks, persona_privacy_attacks, user_task, run_single_attack)
