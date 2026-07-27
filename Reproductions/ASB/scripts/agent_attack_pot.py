import argparse
import os
import subprocess
import sys

import yaml


API_MODEL_PREFIXES = ("gpt", "gemini", "claude", "deepseek")


def run_command(cmd, log_output, foreground):
    print(log_output, flush=True)
    with open(log_output, "w") as log_f:
        if foreground:
            result = subprocess.run(cmd, stdout=log_f, stderr=subprocess.STDOUT)
            if result.returncode != 0:
                raise SystemExit(f"Command failed with exit code {result.returncode}; see {log_output}")
        else:
            subprocess.Popen(cmd, stdout=log_f, stderr=subprocess.STDOUT, start_new_session=True)


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Load POT YAML config file')
    parser.add_argument('--cfg_path', type=str, default='config/POT.yml', help='Path to the POT YAML configuration file')
    args = parser.parse_args()

    with open(args.cfg_path, 'r') as file:
        cfg = yaml.safe_load(file)

    llms = cfg.get('llms', None)
    env_model = os.getenv('ASB_MODEL') or os.getenv('MODEL_NAME') or os.getenv('OPENAI_MODEL')
    if env_model:
        llms = [env_model]
        print(f"ASB env model override active: {env_model}", flush=True)
    attack_tool_types = cfg.get('attack_tool', None)
    defense_type = cfg.get('defense_type', None) # pot_paraphrase_defense, pot_shuffling_defense
    injection_methods = cfg['injection_method'] # 'pot_backdoor', 'pot_clean', 'clean'
    attack_types = cfg.get('attack_types', None)
    triggers = cfg.get('triggers', None) # 'through a prism of insight', 'with perspicacious discernment', 'conducting a comprehensive elucidation', ':)', '@_@'
    task_num = cfg.get('task_num', 1)
    foreground = os.getenv('ASB_FOREGROUND', '').lower() in {'1', 'true', 'yes'}

    for attack_tool_type in attack_tool_types:
        for injection_method in injection_methods:
            for trigger in triggers:
                for llm in llms:
                    for attack_type in attack_types:
                        if llm.startswith(API_MODEL_PREFIXES):
                            llm_name = llm
                            backend = None
                        elif llm.startswith('ollama'):
                            llm_name = llm.split('/')[-1]
                            backend = 'ollama'
                        else:
                            llm_name = llm.split('/')[-1]
                            backend = 'vllm'

                        log_path = f'logs/{injection_method}/{llm_name}'
                        db_suffix = os.getenv('ASB_MEMORY_DB_SUFFIX', os.getenv('ASB_EMBEDDING_MODEL', 'nomic-embed-text')).replace('/', '_')
                        database = f'memory_db/direct_prompt_injection/{attack_type}_{db_suffix}'

                        if trigger == ':)':
                            trigger_suffix = 'smile'
                        else:
                            trigger_suffix = trigger.replace(' ', '_')

                        if attack_tool_type == 'all':
                            attacker_tools_path = 'data/all_attack_tools.jsonl'
                        elif attack_tool_type == 'non-agg':
                            attacker_tools_path = 'data/all_attack_tools_non_aggressive.jsonl'
                        elif attack_tool_type == 'agg':
                            attacker_tools_path = 'data/all_attack_tools_aggressive.jsonl'
                        else:
                            raise ValueError(f"Unsupported attack_tool value: {attack_tool_type}. Use one of: all, non-agg, agg.")

                        log_memory_type = 'no_memory'
                        log_file = f'{log_path}/{defense_type}/{attack_type}-{attack_tool_type}' if defense_type else f'{log_path}/{log_memory_type}/{attack_type}-{attack_tool_type}'
                        os.makedirs(os.path.dirname(log_file), exist_ok=True)

                        if injection_method in ['pot_backdoor', 'pot_clean', 'clean']:
                            log_output = f'{log_file}_{trigger_suffix}.log'
                            cmd = [
                                sys.executable,
                                'main_attacker.py',
                                '--llm_name', llm,
                                '--attack_type', attack_type,
                                '--use_backend', str(backend),
                                '--attacker_tools_path', attacker_tools_path,
                                f'--{injection_method}',
                                '--defense_type', str(defense_type),
                                '--tasks_path', 'data/agent_task_pot.jsonl',
                                '--trigger', trigger,
                                '--task_num', str(task_num),
                                '--res_file', f'{log_file}_{trigger_suffix}.csv',
                            ]
                            if database:
                                cmd += ['--database', database]
                            run_command(cmd, log_output, foreground)
