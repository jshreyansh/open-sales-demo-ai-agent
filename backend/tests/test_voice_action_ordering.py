"""Regression coverage for the visitor 80d20cb9 screen-share bug: a
straggling voice action from an already-superseded turn landed on the
frontend right after an explicit "close the screen" action and silently
reopened the share. See server.py's report_voice_action and
agent_processor.py's _report_action for the fix (a per-visitor monotonic
seq that lets a stale report be dropped instead of queued)."""
from __future__ import annotations

from src.server import VoiceActionReport, _last_action_seq, _pending_voice_actions, get_voice_action, report_voice_action


def test_stale_action_is_dropped_not_queued():
    visitor = "test-visitor-stale-action"
    close_action = {"page": "meeting", "component": "screen", "method": "close"}
    stale_action = {"page": "content-studio", "component": "magicreel", "method": "open"}

    report_voice_action(VoiceActionReport(visitorId=visitor, action=close_action, seq=2))
    report_voice_action(VoiceActionReport(visitorId=visitor, action=stale_action, seq=1))

    assert get_voice_action(visitor) == close_action
    assert get_voice_action(visitor) == {}


def test_actions_in_increasing_seq_order_are_all_delivered():
    visitor = "test-visitor-in-order-actions"
    first = {"page": "content-studio", "component": "magicreel", "method": "open"}
    second = {"page": "meeting", "component": "screen", "method": "close"}

    report_voice_action(VoiceActionReport(visitorId=visitor, action=first, seq=1))
    report_voice_action(VoiceActionReport(visitorId=visitor, action=second, seq=2))

    assert get_voice_action(visitor) == first
    assert get_voice_action(visitor) == second


def test_unset_seq_keeps_old_always_accepted_behavior():
    visitor = "test-visitor-unset-seq"
    first = {"page": "content-studio", "component": "magicreel", "method": "open"}
    second = {"page": "meeting", "component": "screen", "method": "close"}

    report_voice_action(VoiceActionReport(visitorId=visitor, action=first))
    report_voice_action(VoiceActionReport(visitorId=visitor, action=second))

    assert get_voice_action(visitor) == first
    assert get_voice_action(visitor) == second
    assert visitor not in _last_action_seq
