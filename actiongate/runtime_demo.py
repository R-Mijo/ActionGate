# Copyright (c) 2026 Marco Armijo (R-Mijo). All rights reserved.
# SPDX-License-Identifier: LicenseRef-Proprietary
"""Synthetic fixture: no API, payment, credentials, or external writes."""
from .core import TaskProfile, ReleaseDecision
from .runtime import ActionBroker, Autonomy, CircuitBreaker, ToolPolicy, UsageBudget


def demo():
    clock = [0.0]
    local_notes = []
    broker = ActionBroker(autonomy=Autonomy.ACT_WITH_APPROVAL,
                         reviewers=['example-manager'], clock=lambda: clock[0])
    policy = ToolPolicy(Autonomy.ACT_WITH_APPROVAL, TaskProfile(2, 2, 1, 1, 1, 1),
        lambda subject, args: subject == 'example-agent' and set(args) == {'case_id', 'note'}
        and args['case_id'] == 'SYNTHETIC-1' and isinstance(args['note'], str) and len(args['note']) < 500,
        review_flags=('case_and_note_checked',))
    broker.register('save_note', lambda **args: local_notes.append(args) or 'Saved in demo memory', policy)
    args = {'case_id': 'SYNTHETIC-1', 'note': 'Synthetic follow-up note'}
    ticket = broker.propose('save_note', args, subject='example-agent', decision=ReleaseDecision.RELEASE)
    review = broker.begin_review(ticket, reviewer='example-manager')
    too_fast = False
    try:
        broker.approve_review(review, confirmed_flags=['case_and_note_checked'])
    except PermissionError:
        too_fast = True
    clock[0] = 6.0  # Injected test clock only. The real default is monotonic time.
    broker.approve_review(review, confirmed_flags=['case_and_note_checked'])
    broker.execute(ticket, tool='save_note', arguments=args, subject='example-agent')
    replay_blocked = False
    try:
        broker.execute(ticket, tool='save_note', arguments=args, subject='example-agent')
    except PermissionError:
        replay_blocked = True
    for outcome in ['WITHHOLD', 'RELEASE', 'CONFLICTED', 'RELEASE', 'ERROR']:
        broker.breaker.record(outcome)
    return {'kind': 'SYNTHETIC SOFTWARE FIXTURE; no model or external action',
            'too_fast_review_blocked': too_fast, 'replay_blocked': replay_blocked,
            'local_notes_written': len(local_notes), 'sliding_breaker_tripped': broker.breaker.tripped,
            'effective_autonomy': broker.effective_autonomy.name,
            'boundary': 'Only trusted host code controls registration, policy, identities, verifier findings and reset.'}
