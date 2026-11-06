# Integrating the action broker

The broker is a trusted-host component, not a tool the model can administer. Its tickets are opaque random references to immutable host-held proposals. Public receipt checksums detect changes against a trusted digest; they grant no permission.

## Host setup

```python
from actiongate import ActionBroker, Autonomy, ToolPolicy, TaskProfile, ReleaseDecision

broker = ActionBroker(
    autonomy=Autonomy.ACT_WITH_APPROVAL,
    reviewers={'manager-42'},  # IDs authenticated by your application.
)

def allowed(subject, args):
    return (
        subject == 'case-agent'
        and set(args) == {'case_id', 'note'}
        and args['case_id'] == 'CASE-123'
        and isinstance(args['note'], str)
        and len(args['note']) <= 500
    )

broker.register('save_note', your_database_adapter, ToolPolicy(
    mode=Autonomy.ACT_WITH_APPROVAL,
    profile=TaskProfile(2, 2, 1, 1, 1, 1),
    authorize=allowed,
    review_flags=('correct_case', 'note_checked'),
))
```

The authorization callback enforces resource ownership, action limits, argument schema and policy at proposal and immediately before execution. It must explicitly authorize the supplied JSON object; default function parameters cannot enlarge the approved object.

## Propose, preview, approve, execute

1. Obtain the draft decision from `decide_release` and trusted validators. The integration must prevent the model from controlling these trusted inputs.
2. Call `broker.propose(tool_name, arguments, subject=authenticated_subject, decision=decision)`.
3. Show `broker.preview(ticket)` in the trusted review UI. Show the real tool and arguments rather than the agent's summary.
4. Authenticate a reviewer, then call `broker.begin_review(ticket, reviewer=authenticated_reviewer)`. Keep the returned review session on the trusted side.
5. Call `broker.approve_review(review_id, confirmed_flags=[...])`. It checks elapsed host time and specific required flags. Comprehension and account authentication remain application responsibilities.
6. Call `broker.execute(ticket, tool=tool_name, arguments=arguments, subject=authenticated_subject)`. It rechecks scope, exact content, expiry and control state, consumes the ticket before invocation, and returns `(output, audit_receipt)`.

An exception consumes the ticket because the external result may be unknown. Reconcile the outcome before issuing a new action. Use provider idempotency and transaction controls as well. The broker serializes calls within its process, but is not a distributed transaction or rollback mechanism.

## Circuit breaker

`CircuitBreaker(window=20, threshold=3, on_trip=notify_owner)` trips after three `WITHHOLD`, `CONFLICTED` or `ERROR` observations in the last twenty. Supply trusted workflow outcomes with `record`; the broker records policy denials and tool errors. Ordinary `ESCALATE` is not automatically a violation. Configure a documented workflow policy.

`trip()` revokes outstanding tickets. `reset()` is an owner operation; old tickets stay revoked. `set_autonomy()` also invalidates proposals and reviews. Read tools marked `write=False` may continue; that flag is a trusted assertion about the real function.

Notification callbacks are application-owned. Callback failures appear in `notification_error` and never reopen execution. No messaging service is configured automatically.

## Usage and context

```python
from actiongate import UsageBudget

budget = UsageBudget(daily_tokens=250_000, max_attempts_per_item=3)
reservation = budget.reserve('CASE-123', input_tokens=known_input_tokens, max_output_tokens=500)
# Invoke your adapter with the enforced output cap.
budget.settle(reservation, input_tokens=actual_input_tokens, output_tokens=actual_output_tokens)
```

An unresolved reservation keeps occupying budget. After uncertain provider failure, retain it or conservatively settle the reserved amount. Usage over the reservation is recorded and stops future calls. Rollover uses UTC and preserves outstanding reservations. Restart clears counters, so account-wide limits need persistent provider-side or shared metering.

`prepare_context` selects explicit source/section bundles and rejects missing or stale selections. Include all controlling exceptions and dependencies. Character reduction is not tokenizer output or proof of provider savings.
