# Copyright (c) 2026 Marco Armijo (R-Mijo). All rights reserved.
# SPDX-License-Identifier: LicenseRef-Proprietary
"""Trusted-host action broker and local resource controls.

Only the trusted host may register tools, set autonomy, record verifier decisions,
authenticate reviewers, or reset controls. Never expose these management methods
or underlying credentials as agent tools. A receipt checksum is NOT a capability.
Tickets live in one process and become invalid on restart. Use one broker per
credential boundary; distributed deployments need an equivalent shared broker.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import IntEnum
import json
import inspect
from secrets import token_urlsafe
from threading import RLock
import time
from typing import Callable, Mapping, Any

from .core import PAL, ReleaseDecision, Source, TaskProfile, build_receipt


class Autonomy(IntEnum):
    OBSERVE = 0
    ADVISE = 1
    ACT_WITH_APPROVAL = 2
    ACT_AUTONOMOUSLY = 3


def _integer(value, label, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _positive(value, label):
    import math
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{label} must be positive and finite")
    return float(value)


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty text")
    return value


def _json(value):
    def validate(item):
        if isinstance(item, dict):
            if any(not isinstance(key, str) for key in item):
                raise ValueError('JSON object keys must be strings')
            for child in item.values():
                validate(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                validate(child)
    validate(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


class CircuitBreaker:
    """Sliding-window safety breaker; tripping revokes every outstanding ticket."""
    def __init__(self, window=20, threshold=3, on_trip=None):
        self.window = _integer(window, 'window', 1)
        self.threshold = _integer(threshold, 'threshold', 1)
        if threshold > window:
            raise ValueError('threshold cannot exceed window')
        self._outcomes = deque(maxlen=window)
        self._lock = RLock()
        self._tripped = False
        self._epoch = 0
        self.reason = ''
        self.on_trip = on_trip
        self.notification_error = None

    @property
    def tripped(self):
        with self._lock:
            return self._tripped

    @property
    def epoch(self):
        with self._lock:
            return self._epoch

    def trip(self, reason='Manual stop'):
        with self._lock:
            if self._tripped:
                return
            self._tripped = True
            self._epoch += 1
            self.reason = _text(reason, 'reason')
            if self.on_trip:
                try:
                    self.on_trip(self.reason)
                except Exception as error:
                    # Notification failure must never reopen execution.
                    self.notification_error = type(error).__name__

    def record(self, outcome):
        if outcome not in {'RELEASE', 'WITHHOLD', 'CONFLICTED', 'ERROR', 'ESCALATE'}:
            raise ValueError('Unknown breaker outcome')
        with self._lock:
            self._outcomes.append(outcome in {'WITHHOLD', 'CONFLICTED', 'ERROR'})
            if sum(self._outcomes) >= self.threshold:
                self.trip(f'{sum(self._outcomes)} blocked/conflicted/error outcomes in last {len(self._outcomes)} observations')

    def reset(self):
        """Trusted owner operation. Old tickets stay revoked after recovery."""
        with self._lock:
            self._epoch += 1
            self._tripped = False
            self._outcomes.clear()
            self.reason = ''


@dataclass(frozen=True)
class ToolPolicy:
    mode: Autonomy
    profile: TaskProfile
    authorize: Callable[[str, dict], bool]
    write: bool = True
    review_flags: tuple[str, ...] = ()

    def __post_init__(self):
        if not isinstance(self.mode, Autonomy) or not isinstance(self.profile, TaskProfile):
            raise ValueError('Explicit autonomy and task profile are required')
        if not callable(self.authorize) or type(self.write) is not bool:
            raise ValueError('A trusted authorization callback and boolean write flag are required')
        if not isinstance(self.review_flags, (list, tuple)):
            raise ValueError('review_flags must be a list or tuple of named flags')
        flags = tuple(self.review_flags)
        for flag in flags:
            _text(flag, 'review flag')
        if len(flags) != len(set(flags)):
            raise ValueError('Duplicate review flags')
        object.__setattr__(self, 'review_flags', flags)


@dataclass
class _Ticket:
    tool: str
    subject: str
    arguments_json: str
    expires: float
    epoch: int
    needs_review: bool
    approved_by: str | None = None
    consumed: bool = False


class ActionBroker:
    """Single-process reference boundary for exact, scoped, single-use actions.

    The host authenticates subject/reviewer identities before calling methods.
    A model can propose arguments, but cannot mint approval via a receipt, choose
    autonomy, register a tool, or provide a self-reported review duration.
    """
    def __init__(self, *, autonomy=Autonomy.ADVISE, reviewers=(), breaker=None,
                 min_review_seconds=5, ticket_ttl=120, clock=time.monotonic):
        if not isinstance(autonomy, Autonomy):
            raise ValueError('autonomy must be an Autonomy member')
        self._autonomy = autonomy
        self._reviewers = frozenset(_text(r, 'reviewer') for r in reviewers)
        self.min_review_seconds = _positive(min_review_seconds, 'min_review_seconds')
        self.ticket_ttl = _positive(ticket_ttl, 'ticket_ttl')
        self.breaker = breaker if breaker is not None else CircuitBreaker()
        self._clock = clock
        self._tools = {}
        self._tickets = {}
        self._reviews = {}
        self._lock = self.breaker._lock
        self.events = deque(maxlen=10000)

    @property
    def effective_autonomy(self):
        return min(self._autonomy, Autonomy.ADVISE) if self.breaker.tripped else self._autonomy

    def set_autonomy(self, mode):
        if not isinstance(mode, Autonomy):
            raise ValueError('autonomy must be an Autonomy member')
        with self._lock:
            self._autonomy = mode
            self._tickets.clear()
            self._reviews.clear()

    def register(self, name, function, policy):
        with self._lock:
            _text(name, 'tool name')
            if name in self._tools or not callable(function) or not isinstance(policy, ToolPolicy):
                raise ValueError('Unique tool name, callable and ToolPolicy are required')
            signature = inspect.signature(function)
            if any(p.kind in (p.POSITIONAL_ONLY, p.VAR_POSITIONAL) for p in signature.parameters.values()):
                raise ValueError('Tools must accept named JSON arguments')
            self._tools[name] = (function, policy)

    def _normalize(self, tool, arguments):
        if tool not in self._tools:
            self._deny('Unknown tool')
        if not isinstance(arguments, dict) or any(not isinstance(k, str) for k in arguments):
            raise ValueError('Arguments must be a JSON object with string keys')
        try:
            signature = inspect.signature(self._tools[tool][0])
            bound = signature.bind(**arguments)
            bound.apply_defaults()
        except TypeError as error:
            raise ValueError(f'Arguments do not match the tool signature: {error}') from None
        effective = {}
        for name, value in bound.arguments.items():
            if signature.parameters[name].kind == inspect.Parameter.VAR_KEYWORD:
                effective.update(value)
            else:
                effective[name] = value
        encoded = _json(effective)
        if len(encoded) > 65536:
            raise ValueError('Action arguments exceed 64 KiB')
        return encoded

    def _deny(self, reason):
        self.breaker.record('WITHHOLD')
        raise PermissionError(reason)

    def _check_policy(self, name, subject, arguments):
        if name not in self._tools:
            self._deny('Unknown tool')
        _, policy = self._tools[name]
        mode = min(self.effective_autonomy, policy.mode)
        if policy.write and (self.breaker.tripped or mode < Autonomy.ACT_WITH_APPROVAL):
            self._deny('Writes are disabled at the current autonomy level')
        try:
            allowed = policy.authorize(subject, arguments) is True
        except Exception:
            allowed = False
        if not allowed:
            self._deny('Subject, arguments or policy scope are not authorized')
        return policy, mode

    def propose(self, tool, arguments, *, subject, decision):
        """Host supplies a trusted gate decision, never a generator's assertion."""
        with self._lock:
            _text(subject, 'subject')
            encoded = self._normalize(tool, arguments)
            snapshot = json.loads(encoded)
            if not isinstance(decision, ReleaseDecision) or decision != ReleaseDecision.RELEASE:
                self._deny('A trusted RELEASE decision is required; it is not itself action authorization')
            policy, mode = self._check_policy(tool, subject, snapshot)
            self._tickets = {key: item for key, item in self._tickets.items()
                             if not item.consumed and item.expires > self._clock()
                             and item.epoch == self.breaker.epoch}
            self._reviews = {key: item for key, item in self._reviews.items() if item[0] in self._tickets}
            if len(self._tickets) >= 1000:
                raise PermissionError('Pending action limit reached')
            needs_review = policy.write and (mode == Autonomy.ACT_WITH_APPROVAL
                                            or policy.profile.pal >= PAL.CONTROLLED
                                            or bool(policy.review_flags))
            identifier = token_urlsafe(32)
            self._tickets[identifier] = _Ticket(tool, subject, encoded, self._clock() + self.ticket_ttl,
                                                self.breaker.epoch, needs_review)
            return identifier

    def preview(self, ticket):
        with self._lock:
            item = self._valid(ticket)
            return {'tool': item.tool, 'subject': item.subject,
                    'arguments': json.loads(item.arguments_json),
                    'required_flags': list(self._tools[item.tool][1].review_flags),
                    'needs_review': item.needs_review}

    def _valid(self, ticket):
        item = self._tickets.get(ticket) if isinstance(ticket, str) else None
        if (item is None or item.consumed or item.expires <= self._clock()
                or item.epoch != self.breaker.epoch):
            raise PermissionError('Unknown, consumed, expired or revoked action ticket')
        return item

    def begin_review(self, ticket, *, reviewer):
        with self._lock:
            item = self._valid(ticket)
            if reviewer not in self._reviewers or reviewer == item.subject:
                raise PermissionError('An authorized reviewer distinct from the subject is required')
            identifier = token_urlsafe(32)
            self._reviews[identifier] = (ticket, reviewer, self._clock())
            return identifier

    def approve_review(self, review, *, confirmed_flags):
        with self._lock:
            if review not in self._reviews:
                raise PermissionError('Unknown review session')
            ticket, reviewer, started = self._reviews[review]
            item = self._valid(ticket)
            required = self._tools[item.tool][1].review_flags
            if self._clock() - started < self.min_review_seconds:
                raise PermissionError('Review was submitted too quickly')
            if (not isinstance(confirmed_flags, (list, tuple))
                    or any(not isinstance(flag, str) for flag in confirmed_flags)
                    or set(confirmed_flags) != set(required)):
                raise PermissionError('Each specific review flag must be confirmed')
            item.approved_by = reviewer
            del self._reviews[review]
            return self.preview(ticket)

    def execute(self, ticket, *, tool, arguments, subject):
        # Lock also covers invocation: a second thread cannot replay a ticket.
        # An already-running external operation cannot be undone by a later trip.
        with self._lock, self.breaker._lock:
            item = self._valid(ticket)
            if tool != item.tool or subject != item.subject or self._normalize(tool, arguments) != item.arguments_json:
                self._deny('Action differs from the exact approved tool, subject or arguments')
            self._check_policy(tool, subject, json.loads(item.arguments_json))
            if item.needs_review and item.approved_by is None:
                self._deny('This action requires a completed trusted review session')
            item.consumed = True  # Consume before invocation, including on failure.
            try:
                output = self._tools[tool][0](**json.loads(item.arguments_json))
            except Exception:
                self.breaker.record('ERROR')
                self.events.append(build_receipt({'tool': tool, 'subject': subject,
                                                 'status': 'ERROR', 'ticket': ticket}))
                raise
            self.breaker.record('RELEASE')
            receipt = build_receipt({'tool': tool, 'subject': subject, 'arguments': json.loads(item.arguments_json),
                                     'reviewer': item.approved_by, 'status': 'EXECUTED'})
            self.events.append(receipt)
            return output, receipt


class UsageBudget:
    """Reserve input + maximum output tokens before a model call; settle actual usage.

    Provider adapters must enforce the reserved output limit. Counters are local
    and in-memory; restart does not preserve a daily budget. A shared persistent
    meter is required when multiple workers spend from one provider account.
    """
    def __init__(self, daily_tokens=250000, max_attempts_per_item=3,
                 day=lambda: datetime.now(timezone.utc).date()):
        self.limit = _integer(daily_tokens, 'daily_tokens', 1)
        self.max_attempts = _integer(max_attempts_per_item, 'max_attempts', 1)
        self._day = day
        self._date = day()
        self._used = 0
        self._attempts = {}
        self._reservations = {}
        self._lock = RLock()
        self.tripped = False

    def _rollover(self):
        if self._day() != self._date:
            self._date = self._day()
            self._used = 0
            self._attempts.clear()
            self.tripped = False

    def reserve(self, item_id, input_tokens, max_output_tokens):
        _text(item_id, 'item_id')
        amount = _integer(input_tokens, 'input_tokens') + _integer(max_output_tokens, 'max_output_tokens')
        with self._lock:
            self._rollover()
            if self.tripped or self._used + sum(self._reservations.values()) + amount > self.limit:
                raise PermissionError('Token budget exhausted')
            if self._attempts.get(item_id, 0) >= self.max_attempts:
                raise PermissionError('Per-item attempt limit exhausted')
            identifier = token_urlsafe(24)
            self._reservations[identifier] = amount
            self._attempts[item_id] = self._attempts.get(item_id, 0) + 1
            return identifier

    def settle(self, reservation, *, input_tokens, output_tokens):
        actual = _integer(input_tokens, 'input_tokens') + _integer(output_tokens, 'output_tokens')
        with self._lock:
            self._rollover()
            if reservation not in self._reservations:
                raise ValueError('Unknown or already settled reservation')
            reserved = self._reservations.pop(reservation)
            self._used += actual
            if actual > reserved or self._used > self.limit:
                self.tripped = True
                raise PermissionError('Provider usage exceeded the reserved bound; future calls stopped')

    @property
    def used(self):
        with self._lock:
            self._rollover()
            return self._used


def prepare_context(sources: Mapping[str, Source], selected: Mapping[str, tuple[str, ...]], *, now=None):
    """Select explicit host-defined policy bundles; never guess controlling rules.

    The host must include all applicable exceptions/dependencies. Returns actual
    context strings and character counts, not claimed provider token savings.
    """
    now = now or datetime.now(timezone.utc)
    full = []
    chosen = []
    for key, source in sources.items():
        if key != source.source_id:
            raise ValueError('Mismatched source registry')
        if source.is_current(now):
            full.extend(f'[{key} {loc}] {text}' for loc, text in source.sections.items())
    if not selected:
        raise ValueError('An explicit controlling policy bundle is required')
    for key, locators in selected.items():
        source = sources.get(key)
        if source is None or not source.is_current(now) or not locators:
            raise ValueError('Selected source is missing, unapproved, future or expired')
        for loc in dict.fromkeys(locators):
            if loc not in source.sections:
                raise ValueError(f'Unknown controlling section: {key}/{loc}')
            chosen.append(f'[{key} {loc}] {source.sections[loc]}')
    baseline, context = '\n'.join(full), '\n'.join(chosen)
    return {'context': context, 'baseline_characters': len(baseline),
            'selected_characters': len(context), 'characters_removed': max(0, len(baseline) - len(context))}
