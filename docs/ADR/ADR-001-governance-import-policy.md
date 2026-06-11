# ADR-001: Governance Import Policy

Status: Accepted

Date: 2026-06-11

## Context

The hiring-demand project is becoming the first independent repo template for multiple topic repos. It should be understandable by Codex and Claude from the middle of a workflow, and it should remain movable across GitHub, Railway, or another host.

The parent project already uses several external workflow references as concept sources, including ZeroSpec, Superpowers, basic-memory, andrej-karpathy-skills, mattpocock/skills, OPA, Temporal, Langfuse, OpenTelemetry, Great Expectations, Prefect, Dagster, and Argo Workflows.

## Decision

Use external repos as governance concept sources only. Do not vendor them into this repo candidate and do not make local runs, Railway deploys, GitHub commits, or web uptime depend on them.

Imported concepts must land locally before they affect execution:

| Level | Meaning | Hiring-Demand Requirement |
|---|---|---|
| L0 | Research note | Mentioned in notes only; not an active rule. |
| L1 | Governance adoption | Recorded in ADR, `AGENTS.md`, or `docs/CURRENT_EXECUTION.md`. |
| L2 | Workflow adoption | Added to manifest, command docs, receipts, or active checklist. |
| L3 | Automation adoption | Enforced by a deterministic checker or test with fresh evidence. |

## Local Mapping

| Concept Source | Local Hiring-Demand Mapping |
|---|---|
| ZeroSpec | Short active-truth docs and manifests. |
| Superpowers | Planning, debugging, verification, and review discipline under repo-local rules. |
| basic-memory | Durable project knowledge through docs, pitfalls, ADRs, and receipts. |
| andrej-karpathy-skills | Anti-assumption, minimal change, and clarification-first behavior. |
| mattpocock/skills | Selective `diagnose`, `grill-with-docs`, and `zoom-out` patterns. |
| OPA | Protected-path and forbidden-action checks. |
| Temporal / Prefect | Explicit workflow states and step unlocks. |
| Langfuse / OpenTelemetry | Local JSONL trace and correlation IDs, without external collectors. |
| Great Expectations | Data contract checks, row counts, schema checks, freshness checks, negative controls. |
| Dagster / Argo | Artifact lineage and dependency ordering through manifests. |

## Consequences

- The project remains deployable without external governance runtimes.
- Codex and Claude can use external workflow ideas, but `AGENTS.md` and manifests remain authoritative.
- A concept is not a release gate until a local checker or test enforces it.
- Daily publication should stay small: JSON web artifacts, receipts, and scoped deploy paths instead of protected DB commits.

