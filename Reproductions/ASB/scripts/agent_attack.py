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

    parser = argparse.ArgumentParser(description='Load YAML config file')
    parser.add_argument('--cfg_path', type=str, required=True, help='Path to the YAML configuration file')
    args = parser.parse_args()

    with open(args.cfg_path, 'r') as file:
        cfg = yaml.safe_load(file)

    llms = cfg.get('llms', None)
    env_model = os.getenv('ASB_MODEL') or os.getenv('MODEL_NAME') or os.getenv('OPENAI_MODEL')
    if env_model:
        llms = [env_model]
        print(f"ASB env model override active: {env_model}", flush=True)
    suffix = cfg.get('suffix', '')
    attack_tool_types = cfg.get('attack_tool', None)
    write_db = cfg.get('write_db', None)
    read_db = cfg.get('read_db', None)
    defense_type = cfg.get('defense_type', None)
    injection_method = cfg['injection_method'] # 'direct_prompt_injection', 'memory_attack', 'observation_prompt_injection', 'clean'
    attack_types = cfg.get('attack_types', None)
    task_num = cfg.get('task_num', 1)
    tasks_path = cfg.get('tasks_path', 'data/agent_task.jsonl')
    attacker_tools_path_override = cfg.get('attacker_tools_path')
    foreground = os.getenv('ASB_FOREGROUND', '').lower() in {'1', 'true', 'yes'}

    for attack_tool_type in attack_tool_types:
        for llm in llms:
            for attack_type in attack_types:
                if llm.startswith(API_MODEL_PREFIXES):
                    llm_name = llm
                    backend = None
                elif llm.startswith('ollama'):
                    llm_name = llm.split('/')[-1]
                    backend = 'ollama'
                else:
                    llm_name = llm
                    backend = None

                log_path = f'logs/{injection_method}/{llm_name}'
                db_suffix = os.getenv('ASB_MEMORY_DB_SUFFIX', os.getenv('ASB_EMBEDDING_MODEL', 'nomic-embed-text')).replace('/', '_')
                database = f'memory_db/direct_prompt_injection/{attack_type}_{db_suffix}'

                if attacker_tools_path_override:
                    attacker_tools_path = attacker_tools_path_override
                elif attack_tool_type == 'all':
                    attacker_tools_path = 'data/all_attack_tools.jsonl'
                elif attack_tool_type == 'non-agg':
                    attacker_tools_path = 'data/all_attack_tools_non_aggressive.jsonl'
                elif attack_tool_type == 'agg':
                    attacker_tools_path = 'data/all_attack_tools_aggressive.jsonl'
                else:
                    raise ValueError(f"Unsupported attack_tool value: {attack_tool_type}. Use one of: all, non-agg, agg.")

                log_memory_type = 'new_memory' if read_db else 'no_memory'
                log_base = f'{log_path}/{defense_type}' if defense_type else f'{log_path}/{log_memory_type}'
                log_file = f'{log_base}/{attack_type}-{attack_tool_type}'
                os.makedirs(os.path.dirname(log_file), exist_ok=True)

                cmd = [
                    sys.executable,
                    'main_attacker.py',
                    '--llm_name', llm,
                    '--attack_type', attack_type,
                    '--use_backend', str(backend),
                    '--attacker_tools_path', attacker_tools_path,
                    '--tasks_path', tasks_path,
                    '--task_num', str(task_num),
                    '--res_file', f'{log_file}_{suffix}.csv',
                ]

                if database:
                    cmd += ['--database', database]
                if write_db:
                    cmd += ['--write_db']
                if read_db:
                    cmd += ['--read_db']
                if defense_type:
                    cmd += ['--defense_type', defense_type]

                if injection_method in ['direct_prompt_injection', 'memory_attack', 'observation_prompt_injection', 'clean']:
                    cmd += [f'--{injection_method}']
                elif injection_method == 'mixed_attack':
                    cmd += ['--direct_prompt_injection', '--observation_prompt_injection']
                elif injection_method == 'DPI_MP':
                    cmd += ['--direct_prompt_injection']
                elif injection_method == 'OPI_MP':
                    cmd += ['--observation_prompt_injection']
                elif injection_method == 'DPI_OPI':
                    cmd += ['--direct_prompt_injection', '--observation_prompt_injection']

                log_output = f'{log_file}_{suffix}.log'
                run_command(cmd, log_output, foreground)
