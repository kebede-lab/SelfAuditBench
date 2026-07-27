"""
Attack execution utilities for the ConVerse Benchmark.
Contains functions for running different types of attacks and simulations.
"""

from typing import Dict, List, Optional, Any, Callable
from simulation_utils import create_security_attack_instruction, create_privacy_attack_instruction


def find_and_run_security_attack(security_attacks: Dict, attack_name: str, 
                                user_task: str, run_single_attack: Callable, args=None) -> None:
    """Find and run a specific security attack by name"""
    found = False
    for category, attacks in security_attacks.items():
        for attack_key, attack_data in attacks.items():
            if attack_key == attack_name or attack_data.get("name", "") == attack_name:
                attack_name_formatted = f"{category}_{attack_key}"
                user_task_for_attack = user_task + attack_data.get("user_task", "")
                attack_instruction = create_security_attack_instruction(attack_data, args)
                
                run_single_attack(user_task_for_attack, attack_instruction, attack_name_formatted)
                found = True
                break
        if found:
            break
    
    if not found:
        print(f"Attack '{attack_name}' not found in security attacks")


def find_and_run_privacy_attack(privacy_categories: Dict, attack_name: str, 
                               user_task: str, run_single_attack: Callable) -> None:
    """Find and run a specific privacy attack by name"""
    found = False
    for category, category_data in privacy_categories.items():
        for item in category_data.get("items", []):
            if item['data_item'].lower().replace(' ', '_') == attack_name.lower().replace(' ', '_'):
                attack_name_formatted = f"{category}_{item['data_item'].replace(' ', '_').lower()}"
                attack_action = item.get("attack_action", "")
                
                if attack_action == "":
                    break
                
                attack_instruction = create_privacy_attack_instruction(item)
                run_single_attack(user_task, attack_instruction, attack_name_formatted)
                found = True
                break
        if found:
            break
    
    if not found:
        print(f"Privacy attack for '{attack_name}' not found or empty")


def run_all_security_attacks(security_attacks: Dict, user_task: str, 
                           run_single_attack: Callable, args=None) -> None:
    """Run all security attacks"""
    for category, attacks in security_attacks.items():
        for attack_key, attack_data in attacks.items():
            attack_name = f"{category}_{attack_key}"
            user_task_for_attack = user_task + attack_data.get("user_task", "")
            attack_instruction = create_security_attack_instruction(attack_data, args)
            run_single_attack(user_task_for_attack, attack_instruction, attack_name)


def run_all_privacy_attacks(privacy_categories: Dict, user_task: str, 
                          run_single_attack: Callable) -> None:
    """Run all privacy attacks across all categories"""
    for category, category_data in privacy_categories.items():
        for item in category_data.get("items", []):
            attack_name = f"{category}_{item['data_item'].replace(' ', '_').lower()}"
            attack_action = item.get("attack_action", "")
            if attack_action == "": 
                continue 
            attack_instruction = create_privacy_attack_instruction(item)
            run_single_attack(user_task, attack_instruction, attack_name)


def execute_simulation_based_on_type(args, persona_security_attacks: Dict, 
                                   persona_privacy_attacks: Dict, user_task: str,
                                   run_single_attack: Callable) -> None:
    """Execute simulation based on the specified simulation type"""
    
    if args.simulation_type == "security":
        security_attacks = persona_security_attacks
        
        if args.run_all_attacks:
            print(f"Running all security attacks for persona {args.persona_id}")
            run_all_security_attacks(security_attacks, user_task, run_single_attack, args)
        else:
            if args.attack_name:
                find_and_run_security_attack(security_attacks, args.attack_name, user_task, run_single_attack, args)
            else:
                print("You have to either run all attacks or specify an attack name.")

    elif args.simulation_type == "privacy":
        privacy_categories = persona_privacy_attacks["categories"]
        
        if args.run_all_attacks:
            print(f"Running all privacy attacks for persona {args.persona_id}")
            run_all_privacy_attacks(privacy_categories, user_task, run_single_attack)
        else:
            if args.attack_name:
                find_and_run_privacy_attack(privacy_categories, args.attack_name, user_task, run_single_attack)
            else:
                print("You have to either run all attacks or specify an attack name.")

    elif "benign" in args.simulation_type:
        # Run benign task
        run_single_attack(user_task, None, "no_attack")

    print("All simulations completed!")
