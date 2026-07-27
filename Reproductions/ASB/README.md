# Agent Security Bench reproduction

This directory contains the ASB reproduction used to construct the SelfAuditBench tool-use and memory-risk surface. It is based on **Agent Security Bench (ASB): Formalizing and Benchmarking Attacks and Defenses in LLM-based Agents** ([paper](https://arxiv.org/abs/2410.02644), [project page](https://luckfort.github.io/ASBench/), [upstream code](https://github.com/agiresearch/ASB)). The reproduced upstream code is distributed under its [MIT License](LICENSE).

## Reproduction profile

- Chat and judge model: `deepseek-v4-flash` through the official DeepSeek API.
- Memory embeddings: local Ollama `nomic-embed-text`.
- Covered groups: clean, direct prompt injection, observation prompt injection, memory poisoning, mixed attacks, and combined attack families.
- Retained reproduction outputs: [`logs`](logs).

The adapter separates source actions from co-located observations so SelfAuditBench can evaluate strictly pre-execution proposals.

## Run

Create a Python environment, install the dependencies, and follow the staged commands:

```bash
python -m pip install -r requirements.txt
```

See [`commands.md`](commands.md) for credential setup, Ollama preparation, memory-database reconstruction, smoke checks, full execution, and result summaries.

## Import into SelfAuditBench

From the SelfAuditBench repository root:

```bash
selfauditbench ingest asb \
  Reproductions/ASB/logs \
  artifacts/exploratory/asb.jsonl
```

The complete paired selection and annotation workflow is defined in [`../../Runbooks/ASB.md`](../../Runbooks/ASB.md).

## Upstream citation

```bibtex
@inproceedings{zhang2025agent,
  title={Agent Security Bench (ASB): Formalizing and Benchmarking Attacks and Defenses in LLM-based Agents},
  author={Hanrong Zhang and Jingyuan Huang and Kai Mei and Yifei Yao and Zhenting Wang and Chenlu Zhan and Hongwei Wang and Yongfeng Zhang},
  booktitle={The Thirteenth International Conference on Learning Representations},
  year={2025},
  url={https://openreview.net/forum?id=V4y0CpX4hK}
}
```
