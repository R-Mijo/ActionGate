# Copyright (c) 2026 Marco Armijo (R-Mijo). All rights reserved.
# SPDX-License-Identifier: LicenseRef-Proprietary
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
import unittest

from meeho_actiongate.core import ReleaseDecision, TaskProfile, Source, build_receipt
from meeho_actiongate.runtime import ActionBroker, Autonomy, CircuitBreaker, ToolPolicy, UsageBudget, prepare_context


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.executed = []
        self.permitted = True
        self.broker = ActionBroker(autonomy=Autonomy.ACT_AUTONOMOUSLY,
            reviewers=['manager'], clock=lambda: self.now)
        self.policy = ToolPolicy(Autonomy.ACT_AUTONOMOUSLY, TaskProfile(0, 0, 0, 0, 0, 0),
            lambda subject, args: self.permitted and subject == 'agent' and set(args) == {'item_id', 'amount'}
            and args['item_id'] == 'A' and type(args['amount']) is int and 0 < args['amount'] <= 100)
        self.broker.register('write', lambda **args: self.executed.append(args) or 'OK', self.policy)
        self.args = {'item_id': 'A', 'amount': 10}

    def ticket(self):
        return self.broker.propose('write', self.args, subject='agent', decision=ReleaseDecision.RELEASE)

    def execute(self, ticket, **changes):
        return self.broker.execute(ticket, **dict(tool='write', arguments=self.args, subject='agent', **changes))

    def test_exact_action_and_single_use(self):
        ticket = self.ticket()
        output, receipt = self.execute(ticket)
        self.assertEqual(output, 'OK')
        self.assertEqual(receipt['status'], 'EXECUTED')
        with self.assertRaises(PermissionError):
            self.execute(ticket)
        self.assertEqual(len(self.executed), 1)

    def test_unrelated_arguments_and_forged_receipt(self):
        ticket = self.ticket()
        for kwargs in (dict(arguments={'item_id': 'B', 'amount': 10}), dict(arguments={'item_id': 'A', 'amount': 99})):
            with self.assertRaises(PermissionError):
                self.broker.execute(ticket, tool='write', subject='agent', **kwargs)
        with self.assertRaises(PermissionError):
            self.execute(build_receipt({'decision': 'RELEASE'}))
        self.assertEqual(self.executed, [])

    def test_defaults_cannot_escape_binding(self):
        # The broker invokes only its stored complete JSON args, never the
        # wrapper's bind_partial view that missed Gemini's default arguments.
        with self.assertRaises(PermissionError):
            self.broker.propose('write', {}, subject='agent', decision=ReleaseDecision.RELEASE)
        self.assertEqual(self.executed, [])

    def test_expiry_restart_and_reset_revoke(self):
        ticket = self.ticket()
        self.now = 121
        with self.assertRaises(PermissionError):
            self.execute(ticket)
        ticket = self.ticket()
        self.broker.breaker.trip()
        self.assertEqual(self.broker.effective_autonomy, Autonomy.ADVISE)
        with self.assertRaises(PermissionError):
            self.execute(ticket)
        self.broker.breaker.reset()
        with self.assertRaises(PermissionError):
            self.execute(ticket)
        other = ActionBroker()
        with self.assertRaises(PermissionError):
            other.preview(ticket)

    def test_defaults_are_expanded_before_policy_and_preview(self):
        def defaults(item_id='B', amount=999999):
            return item_id, amount
        self.broker.register('defaults', defaults, self.policy)
        with self.assertRaises(PermissionError):
            self.broker.propose('defaults', {}, subject='agent', decision=ReleaseDecision.RELEASE)
        ticket = self.broker.propose('defaults', self.args, subject='agent', decision=ReleaseDecision.RELEASE)
        self.assertEqual(self.broker.preview(ticket)['arguments'], self.args)
        output, _ = self.broker.execute(ticket, tool='defaults', arguments=self.args, subject='agent')
        self.assertEqual(output, ('A', 10))

    def test_tool_and_subject_changes_blocked(self):
        ticket = self.ticket()
        for tool, subject in [('other', 'agent'), ('write', 'attacker')]:
            with self.assertRaises(PermissionError):
                self.broker.execute(ticket, tool=tool, subject=subject, arguments=self.args)

    def test_policy_rechecked_at_execution(self):
        ticket = self.ticket()
        self.permitted = False
        with self.assertRaises(PermissionError):
            self.execute(ticket)

    def test_autonomy_demotion_blocks_writes(self):
        ticket = self.ticket()
        self.broker.set_autonomy(Autonomy.ADVISE)
        with self.assertRaises(PermissionError):
            self.execute(ticket)
        with self.assertRaises(PermissionError):
            self.ticket()

    def test_per_tool_advice_cannot_inherit_write_access(self):
        policy = ToolPolicy(Autonomy.ADVISE, self.policy.profile, self.policy.authorize)
        self.broker.register('draft_only', lambda **args: self.executed.append(args), policy)
        with self.assertRaises(PermissionError):
            self.broker.propose('draft_only', self.args, subject='agent', decision=ReleaseDecision.RELEASE)

    def test_review_uses_host_clock_exact_flags_and_authorized_identity(self):
        policy = ToolPolicy(Autonomy.ACT_WITH_APPROVAL, self.policy.profile,
                            self.policy.authorize, review_flags=('policy_conflict',))
        self.broker.register('reviewed', lambda **args: 'reviewed', policy)
        ticket = self.broker.propose('reviewed', self.args, subject='agent', decision=ReleaseDecision.RELEASE)
        with self.assertRaises(PermissionError):
            self.broker.begin_review(ticket, reviewer='')
        with self.assertRaises(PermissionError):
            self.broker.begin_review(ticket, reviewer='agent')
        review = self.broker.begin_review(ticket, reviewer='manager')
        self.now = 1
        with self.assertRaises(PermissionError):
            self.broker.approve_review(review, confirmed_flags=['policy_conflict'])
        self.now = 6
        with self.assertRaises(PermissionError):
            self.broker.approve_review(review, confirmed_flags=[])
        self.broker.approve_review(review, confirmed_flags=['policy_conflict'])
        output, receipt = self.broker.execute(ticket, tool='reviewed', arguments=self.args, subject='agent')
        self.assertEqual(output, 'reviewed')
        self.assertEqual(receipt['reviewer'], 'manager')

    def test_high_risk_requires_review_even_in_auto_mode(self):
        policy = ToolPolicy(Autonomy.ACT_AUTONOMOUSLY, TaskProfile(3, 0, 0, 0, 0, 0), self.policy.authorize)
        self.broker.register('sensitive', lambda **args: 'changed', policy)
        ticket = self.broker.propose('sensitive', self.args, subject='agent', decision=ReleaseDecision.RELEASE)
        with self.assertRaises(PermissionError):
            self.broker.execute(ticket, tool='sensitive', arguments=self.args, subject='agent')

    def test_concurrent_replay_executes_once(self):
        ticket = self.ticket()
        def call(_):
            try:
                self.execute(ticket)
                return True
            except PermissionError:
                return False
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sum(pool.map(call, range(4))), 1)
        self.assertEqual(len(self.executed), 1)

    def test_nonfinite_and_wrong_types_rejected(self):
        for value in [float('nan'), float('inf')]:
            with self.assertRaises(ValueError):
                self.broker.propose('write', {'amount': value}, subject='agent', decision=ReleaseDecision.RELEASE)
            with self.assertRaises(ValueError):
                ActionBroker(min_review_seconds=value)
        with self.assertRaises(PermissionError):
            self.broker.propose('write', self.args, subject='agent', decision='RELEASE')

    def test_input_mutation_does_not_change_preview(self):
        ticket = self.ticket()
        self.args['amount'] = 20
        self.assertEqual(self.broker.preview(ticket)['arguments']['amount'], 10)

    def test_tool_failure_consumes_ticket(self):
        def fail(**args):
            raise RuntimeError('unknown external outcome')
        self.broker.register('fail', fail, self.policy)
        ticket = self.broker.propose('fail', self.args, subject='agent', decision=ReleaseDecision.RELEASE)
        with self.assertRaises(RuntimeError):
            self.broker.execute(ticket, tool='fail', subject='agent', arguments=self.args)
        with self.assertRaises(PermissionError):
            self.broker.execute(ticket, tool='fail', subject='agent', arguments=self.args)

    def test_sliding_window_and_notification_failure(self):
        notified = []
        breaker = CircuitBreaker(window=5, threshold=3, on_trip=notified.append)
        for outcome in ['WITHHOLD', 'RELEASE', 'CONFLICTED', 'RELEASE', 'ERROR']:
            breaker.record(outcome)
        self.assertTrue(breaker.tripped)
        self.assertEqual(len(notified), 1)
        breaker.trip('again')
        self.assertEqual(len(notified), 1)
        def fail(_):
            raise RuntimeError()
        breaker = CircuitBreaker(threshold=1, on_trip=fail)
        breaker.record('WITHHOLD')
        self.assertTrue(breaker.tripped)
        self.assertEqual(breaker.notification_error, 'RuntimeError')

    def test_budget_reserves_response_and_caps_attempts(self):
        budget = UsageBudget(daily_tokens=100, max_attempts_per_item=2)
        reservation = budget.reserve('A', 20, 60)
        with self.assertRaises(PermissionError):
            budget.reserve('B', 10, 20)
        budget.settle(reservation, input_tokens=20, output_tokens=30)
        self.assertEqual(budget.used, 50)
        with self.assertRaises(ValueError):
            budget.settle(reservation, input_tokens=0, output_tokens=0)
        second = budget.reserve('A', 10, 10)
        budget.settle(second, input_tokens=10, output_tokens=0)
        with self.assertRaises(PermissionError):
            budget.reserve('A', 1, 1)

    def test_budget_rollover_preserves_inflight_reservations(self):
        current = [date(2026, 11, 5)]
        budget = UsageBudget(daily_tokens=100, day=lambda: current[0])
        first = budget.reserve('A', 10, 80)
        current[0] += timedelta(days=1)
        with self.assertRaises(PermissionError):
            budget.reserve('B', 10, 10)
        budget.settle(first, input_tokens=10, output_tokens=1)
        self.assertEqual(budget.used, 11)

    def test_provider_overage_trips_budget(self):
        budget = UsageBudget(daily_tokens=100)
        r = budget.reserve('A', 10, 10)
        with self.assertRaises(PermissionError):
            budget.settle(r, input_tokens=10, output_tokens=20)
        with self.assertRaises(PermissionError):
            budget.reserve('B', 0, 1)

    def test_explicit_context_bundle_preserves_controlling_rules(self):
        now = datetime.now(timezone.utc)
        source = Source('P', 'Policy', '1', True, now - timedelta(days=1), None,
                        {'authority': 'Draft only.', 'exception': 'Manager review.', 'unrelated': 'X' * 1000})
        result = prepare_context({'P': source}, {'P': ('authority', 'exception')}, now=now)
        self.assertIn('Manager review.', result['context'])
        self.assertGreater(result['characters_removed'], 0)
        with self.assertRaises(ValueError):
            prepare_context({'P': source}, {'P': ('missing',)}, now=now)
        with self.assertRaises(ValueError):
            prepare_context({'P': source}, {}, now=now)


if __name__ == '__main__':
    unittest.main()
