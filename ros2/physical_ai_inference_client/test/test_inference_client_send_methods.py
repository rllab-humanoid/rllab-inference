"""P.1 New send_* methods build the correct SendCommand request."""
from __future__ import annotations


def _command_client(node):
    return node._command_client


def test_send_preload_policy_sends_command_8(make_client):
    node = make_client()
    ok = node.send_preload_policy('/path/B')
    assert ok is True
    cmd_client = _command_client(node)
    assert len(cmd_client.calls) >= 1
    req = cmd_client.calls[-1]
    assert req.command == 8  # PRELOAD_POLICY
    # policy_path is propagated into task_info
    assert req.task_info.policy_path == '/path/B'


def test_send_swap_policy_sends_command_9(make_client):
    node = make_client()
    node._current_policy_path = '/path/A'
    ok = node.send_swap_policy()
    assert ok is True
    req = _command_client(node).calls[-1]
    assert req.command == 9  # SWAP_POLICY


def test_send_cancel_preload_sends_command_10(make_client):
    node = make_client()
    ok = node.send_cancel_preload()
    assert ok is True
    req = _command_client(node).calls[-1]
    assert req.command == 10  # CANCEL_PRELOAD


def test_each_method_targets_the_command_service(make_client):
    node = make_client()
    cmd_client = _command_client(node)
    assert cmd_client.service_name == '/task/command'
    node.send_preload_policy('/B')
    node.send_swap_policy()
    node.send_cancel_preload()
    # All calls went through the same command client
    assert len(cmd_client.calls) == 3


def test_failed_preload_response_returns_false(make_client):
    node = make_client()
    cmd_client = _command_client(node)
    cmd_client.response_factory = lambda req: type('R', (), {
        'success': False, 'message': 'insufficient memory'})()
    ok = node.send_preload_policy('/B')
    assert ok is False


def test_failed_swap_response_returns_false(make_client):
    node = make_client()
    cmd_client = _command_client(node)
    cmd_client.response_factory = lambda req: type('R', (), {
        'success': False, 'message': 'not ready'})()
    ok = node.send_swap_policy()
    assert ok is False


def test_send_cancel_logs_pending_path_before_call(make_client):
    """When a pending path is known, cancel must log it before calling
    the service so users see what's being cancelled."""
    node = make_client()
    node._pending_policy_path = '/path/B'
    node.send_cancel_preload()
    info_msgs = [m for level, m in node.logger.messages if level == 'info']
    # at least one info message before the service-accepted line mentions /path/B
    assert any('/path/B' in m and 'cancel' in m.lower() for m in info_msgs)


def test_send_cancel_without_pending_path_falls_back(make_client):
    node = make_client()
    node._pending_policy_path = None
    node.send_cancel_preload()
    info_msgs = [m for level, m in node.logger.messages if level == 'info']
    # message should mention "no client-side record" or similar
    assert any('no client-side record' in m.lower() for m in info_msgs)
