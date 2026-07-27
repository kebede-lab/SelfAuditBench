# Released artifacts

This directory contains only the study artifacts used for the paper:

- `annotations/final-96`: blinded scenarios, independent annotations, frozen hashes, adjudication, and protocol;
- `runs`: 15 full paper-facing runs;
- `comparisons`: 12 backend comparisons and two closed-loop treatment comparisons;
- `conformance`: deterministic action-sink conformance cases;
- `exploratory`: normalized ASB, ConVerse, and AFTraj source datasets;
- `paper/final-20260724_145758`: final manifest-hashed tables and figure data;
- `schemas-final`: exported JSON schemas;
- `verification`: AFTraj dataset and run verification records.

Every retained run includes an `integrity.json` manifest. Paths in released metadata are repository-relative, and the corresponding manifests bind that portable byte representation. Run `selfauditbench verify --run <run-directory>` before reusing it in analysis.
