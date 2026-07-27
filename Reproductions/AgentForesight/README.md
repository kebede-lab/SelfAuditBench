# AgentForesight AFTraj reproduction

This directory contains the AgentForesight reproduction used for the separate SelfAuditBench prefix-localization diagnostic. It is based on **AgentForesight: Online Auditing for Early Failure Prediction in Multi-Agent Systems** ([paper](https://arxiv.org/abs/2605.08715), [project page](https://zbox1005.github.io/agent-foresight/), [upstream code](https://github.com/ZBox1005/AgentForesight), [AFTraj dataset](https://huggingface.co/datasets/ZBox008003/AFTraj)). The reproduced upstream code is distributed under its [MIT License](LICENSE); AFTraj is released under [CC BY 4.0](DATASET_LICENSE.md).

AFTraj supplies curated safe/unsafe trajectories and decisive-error steps across Math, Coding, and Agentic domains. Its label semantics remain separate from the ASB/ConVerse harm-boundary study.

## Reproduction profile

- Model: `deepseek-v4-flash`.
- Provider: CST Cloud OpenAI-compatible endpoint.
- Split: official 332-trajectory held-out paper split.
- Retained outputs: [`outputs/cstcloud-deepseek-v4-flash`](outputs/cstcloud-deepseek-v4-flash).

| Domain | n | Exact-F1 | Absolute step shift | False-alarm rate | Step accuracy |
|---|---:|---:|---:|---:|---:|
| Math | 116 | 40.32% | 3.44 | 15.52% | 43.10% |
| Coding | 91 | 12.82% | 4.59 | 35.19% | 13.51% |
| Agentic | 125 | 32.50% | 1.60 | 43.86% | 38.24% |
| Overall | 332 | 30.94% | 2.77 | 31.36% | 34.36% |

## Run

Create a Python environment, install the dependencies, and follow the staged commands:

```bash
python -m pip install -r requirements.txt
```

See [`commands.md`](commands.md) for dataset acquisition, credential setup, smoke checks, held-out inference, resume behavior, and result validation.

## Import into SelfAuditBench

From the SelfAuditBench repository root:

```bash
selfauditbench ingest agentforesight \
  Reproductions/AgentForesight/data \
  artifacts/exploratory/agentforesight-paper-test.jsonl \
  --paper-test-split

selfauditbench ingest agentforesight-results \
  Reproductions/AgentForesight/outputs/cstcloud-deepseek-v4-flash/per_sample.jsonl \
  artifacts/exploratory/agentforesight-paper-test.jsonl \
  artifacts/runs/agentforesight-deepseek-native-baseline
```

The integrated diagnostic workflow is defined in [`../../Runbooks/AgentForesight.md`](../../Runbooks/AgentForesight.md).

## Upstream citation

```bibtex
@article{zhang2026agentforesight,
  title={AgentForesight: Online Auditing for Early Failure Prediction in Multi-Agent Systems},
  author={Zhang, Boxuan and Zhu, Jianing and Shi, Zeru and Liu, Dongfang and Tang, Ruixiang},
  journal={arXiv preprint arXiv:2605.08715},
  year={2026}
}
```
