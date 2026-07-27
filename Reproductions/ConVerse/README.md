# ConVerse reproduction

This directory contains the ConVerse reproduction used to construct the SelfAuditBench contextual disclosure and commitment surface. It is based on **ConVerse: Benchmarking Contextual Safety in Agent-to-Agent Conversations** ([paper](https://arxiv.org/abs/2511.05359), [upstream code](https://github.com/amrgomaaelhady/ConVerse)). The reproduced upstream code is distributed under its [MIT License](LICENSE).

ConVerse evaluates privacy and security in multi-turn interactions between personal assistants and external agents across travel planning, real estate, and insurance.

## Reproduction profile

- Assistant, simulated user, external agent, and judge model: `deepseek-v4-flash` through the official DeepSeek API.
- Thinking mode: disabled for bounded structured generation.
- Embeddings: none; this path uses chat completions without a vector store.
- Retained reproduction outputs: [`logs`](logs).
- Pair-specific benign controls: 8 real-estate persona-1, 8 travel persona-1, 4 insurance persona-2, and 4 insurance persona-3 trajectories.

## Run

Create a Python environment, install the dependencies, and follow the staged commands:

```bash
python -m pip install -r requirements.txt
```

See [`commands.md`](commands.md) for credential setup, smoke validation, full execution, output validation, and progress inspection.

## Import into SelfAuditBench

From the SelfAuditBench repository root:

```bash
selfauditbench ingest converse \
  Reproductions/ConVerse/logs \
  artifacts/exploratory/converse.jsonl
```

The paired control and evaluation workflow is defined in [`../../Runbooks/ConVerse.md`](../../Runbooks/ConVerse.md).

## Upstream citation

```bibtex
@article{gomaa2025converse,
  title={ConVerse: Benchmarking Contextual Safety in Agent-to-Agent Conversations},
  author={Amr Gomaa and Ahmed Salem and Sahar Abdelnabi},
  journal={arXiv preprint arXiv:2511.05359},
  year={2025},
  doi={10.48550/arXiv.2511.05359},
  url={https://arxiv.org/abs/2511.05359}
}
```
