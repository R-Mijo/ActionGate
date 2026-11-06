# Verification scope

Run `python -m unittest discover -s tests -v`. Original evidence, checksum and study-preparation tests are retained, with runtime regressions for the recovered prototypes' defects.

Runtime coverage includes exact binding, omitted/default arguments, forged receipts, expiry, revocation across reset, policy rechecks, autonomy demotion, host review timing and flags, high-risk review, concurrent replay, immutable previews, consumption on failure, sliding windows, notification failure, token reservations, attempt limits, rollover, provider overages and explicit context selection.

Demos are synthetic software fixtures. Tests do not establish semantic entailment, complete claim coverage, reviewer comprehension, external transaction behavior, distributed durability, model robustness or production readiness. The study pack makes no model calls or invented model-performance comparisons.

CI runs tests and installation on Windows and Linux with Python 3.11, 3.12 and 3.13. Consult the actual workflow run before claiming a revision passed those environments.
