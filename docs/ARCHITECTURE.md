# ActionGate: toolkit architecture and protocol relationship

**Role:** Python enforcement toolkit integrated into a trusted application. **Protocol home:** [Anchor Task Assurance](https://github.com/R-Mijo/Anchor_Task_Assurance). **Method:** Adaptive Grounded Prompting (AGP), an experimental evidence-and-review procedure. These are separate repositories; ActionGate adds tool-action controls to a shared evidence-checking foundation.

## Two software components

| Component | Responsibility | Boundary |
| --- | --- | --- |
| `actiongate/core.py` | Evidence-release policy: typed task profiles, source/claim records, mandatory checks and release decisions. | Trusted inputs are supplied by the integration. The gate does not itself establish semantic support or authenticate reviewers. |
| `actiongate/runtime.py` | Scoped action proposals, exact-argument checks, authorized review sessions, single-use tickets, autonomy ceilings, circuit breaking and usage reservations. | Host-owned identities, credentials, registered tools and business policy. State is in memory; production persistence and distributed enforcement remain integration work. |

The company supplies its application and review UI. A generator may propose content and arguments; it cannot administer policy, approve itself or hold credentials that bypass the broker. A valid evidence-release decision is a prerequisite in this broker, not a grant of tool permission. The broker currently accepts only its own `ReleaseDecision.RELEASE`; disclosure/escalation/withhold results do not authorize a proposal.

Read [RUNTIME.md](RUNTIME.md) for propose → preview → authenticated review → execute, resource limits and trust boundaries. The current CLI examples are synthetic and do not connect to a model provider or execute a real business transaction.

## Current compatibility snapshot

Inspected November 6, 2026:

| Item | Anchor reference | ActionGate toolkit |
| --- | --- | --- |
| Package | `anchor-task-assurance` 0.2.1, import `agp` | `actiongate` 0.3.1, import `actiongate` |
| Baseline commit | `5b14fb85c0d03d3ef90a0ea5a310b915451aa32a` | `3dcaee44cb96cf4b7265c655d459e3f546c3625a` |
| Code policy identifier | `agp-reference-controls-0.2.0` | `agp-reference-controls-0.2.0` |
| Evidence gate source | `agp/core.py` | `actiongate/core.py` |

The evidence gate files at these baselines are identical after normalizing line endings. ActionGate carries its own copy and declares no dependency on Anchor. Distinct Python classes and enum types are not interchangeable merely because their source text matches. Passing `agp.ReleaseDecision.RELEASE` straight to this action broker is not an integrated workflow. Use the toolkit's trusted gate path, or build and test a validated adapter preserving the exact reviewed draft and policy context.

This is a source inspection, not a formal conformance certification or a guarantee that future versions remain synchronized. A code-sharing refactor should first establish decision fixtures and a versioned data contract. A protocol update should trigger explicit review of this snapshot and any implementation differences. Package versions do not replace policy identifiers.

## Where to maintain documents

Anchor's [METHODOLOGY.md](https://github.com/R-Mijo/Anchor_Task_Assurance/blob/main/docs/METHODOLOGY.md) is the canonical operational method. Its [VALIDATION_PROTOCOL.md](https://github.com/R-Mijo/Anchor_Task_Assurance/blob/main/docs/VALIDATION_PROTOCOL.md) is the research study design. ActionGate retains matching documents as reference snapshots for its history and implementation context; they are not a second independently maintained protocol specification. Local runtime and migration documents remain maintained here.

## Shared company demonstration

Use a customer refund example: establish whether the policy-backed explanation may be delivered, then separately authorize an exact synthetic refund action. A stale source must withhold the explanation; changing the refund amount after review must invalidate execution; an unauthorized reviewer and a replayed ticket must fail. This joined demonstration is a proposed next milestone. Existing evidence and action demos are separate; neither proves a production integration or measured business benefit.

## Suggested GitHub About text

`Python enforcement toolkit for AI agents: scoped tool actions, approvals, autonomy limits and evidence-release checks.`

This text is ready for repository metadata; the documentation change does not itself update GitHub settings. Existing names, licenses, historical grants, imports, commands and runtime behavior remain unchanged.
