![Product banner](docs/assets/banner.svg)

# ActionGate

**The AI Safety Brake — a software toolkit for governing AI tool actions.**

ActionGate is the software companion to the **AGP evidence-and-review protocol**, whose documentation lives in [Anchor Task Assurance](https://github.com/R-Mijo/Anchor_Task_Assurance). It supplies an evidence-release gate plus scoped tool authorization, required approvals, autonomy controls, circuit breaking and usage reservations. Evidence before release. Authority before action.

Created by **Marco Armijo (R-Mijo)**. The projects remain separate repositories and packages: Anchor is the protocol home with reference code; ActionGate is the enforcement toolkit. ActionGate currently includes its own copy of the evidence-checking foundation and has no package dependency on Anchor. It is not yet a certified protocol implementation or a ready-made company dashboard.

## Protocol and tool: choose the right repository

| Repository | Role | Start here |
| --- | --- | --- |
| **[Anchor Task Assurance](https://github.com/R-Mijo/Anchor_Task_Assurance)** | AGP protocol documentation, answer-assurance reference code and evaluation design. | [Protocol overview](https://github.com/R-Mijo/Anchor_Task_Assurance/blob/main/docs/METHODOLOGY.md) |
| **ActionGate — this repository** | Software controls for evidence release and agent tool execution inside a trusted application. | [Architecture and compatibility](docs/ARCHITECTURE.md), then [runtime integration](docs/RUNTIME.md) |

The company using ActionGate owns the application, identities, credentials, business policy and review interface. Its developers integrate the toolkit. Employees encounter its checks and approval requests through that application. A protocol release decision alone cannot authorize an external action.

**0.3.1 | Python 3.11+ | Proprietary | No third-party runtime dependencies**

## In plain English

ActionGate is the permission checkpoint for an AI using tools. It can allow a draft, require a named human review, or block a write operation. For example, an agent can prepare a refund request without having permission to issue the refund. The host must authenticate people and keep direct credentials away from the agent.

## Try it

From the repository folder:

```sh
python -m unittest discover -s tests -v
python -m actiongate demo
python -m actiongate action-demo
```

Install with `python -m pip install .` to use the `actiongate` command. Demos use synthetic data and local memory; they make no model calls or real business actions.

## Two gates, two decisions

| Component | What it checks |
| --- | --- |
| Evidence release gate | Typed risk scores, minimum assurance floors, all eight required checks, material claims, approved sources, valid locators and applicable dates. Unsupported claims withhold; conflicts and material inferences escalate. |
| Action broker | A registered tool's host-defined scope, subject, exact arguments, autonomy ceiling, review requirements, expiration, revocation and single-use execution. A draft receipt cannot authorize a write. |

The broker defaults to **Advise**. The trusted application configures `Observe`, `Advise`, `Act with Approval`, or `Act Autonomously` globally and per tool. Lower settings win. High-risk writes still require review. A sliding-window circuit breaker demotes write access and revokes outstanding tickets; owner resets do not revive old tickets.

Review sessions use a host clock and an authorized reviewer distinct from the agent subject. Reviewers see the exact action and confirm named checks. Elapsed time is a friction signal, **not proof of comprehension**. Unresolved policy conflicts must be resolved in the trusted workflow before a release decision is supplied.

## Resource controls

`UsageBudget` reserves input plus maximum output tokens before a provider call, limits attempts per item, and settles provider-reported usage afterward. The adapter must enforce the reserved output cap. Explicit policy bundles reduce context without guessing which exceptions matter. `prepare_context` reports character counts; measure actual provider usage before claiming token or cost savings.

## Integration boundary

The host authenticates identities and owns registration, policy, verifier findings, credentials, approvals and resets. Keep these management APIs and underlying credentials out of the agent's tool set. The broker cannot protect an API path the agent can call directly.

This is an **in-process reference implementation**. Tickets invalidate on restart; daily budgets and audit events are in memory. Multiple workers need an equivalent shared persistent service. Stops prevent subsequent invocations; they cannot undo an external action already in progress. See [runtime integration](docs/RUNTIME.md).

## Study real model behavior

The existing 30-case synthetic expense pack prepares consistent randomized prompt packets without putting gold answers in prompts:

```sh
python -m actiongate prepare --directory results/pilot --repeats 3 --seed 20261029
python -m actiongate --help
```

This prepares a study; it does not manufacture model outputs or demonstrate improved accuracy. Mechanical scoring is screening; substantive accuracy still needs independent review. This release has no validated accuracy, prompt-injection prevention, or percentage cost-saving claims.

## Read more

- [Toolkit architecture, protocol relationship and compatibility](docs/ARCHITECTURE.md)
- [Runtime API and trust boundary](docs/RUNTIME.md)
- [Migration from the Gemini packages](docs/MIGRATION.md)
- [Verification results](docs/TEST_RESULTS.md)
- [Original methodology](docs/METHODOLOGY.md) and [validation protocol](docs/VALIDATION_PROTOCOL.md)
- [Windows setup](docs/START_HERE_WINDOWS.md)
- [Contributing](CONTRIBUTING.md) and [license](LICENSE)

## Ownership and permitted access

Copyright (c) 2026 Marco Armijo (R-Mijo). **All rights reserved.** This is proprietary software with publicly visible source, not an open-source release. GitHub viewing and forking rights still apply. Repository access alone grants no license to run, copy, modify, distribute, host or commercialize it. Permission requires a separate written agreement signed by the owner. See [LICENSE](LICENSE). SlipSavvy is a separate Apache-2.0 project.

Earlier AGP 0.2 material was publicly offered under MIT. Existing grants for that material are not revoked; see [licensing history](docs/LICENSING_HISTORY.md).
