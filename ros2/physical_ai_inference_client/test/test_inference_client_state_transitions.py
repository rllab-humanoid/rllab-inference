"""P.2 _pending_policy_path / _current_policy_path transitions."""
from __future__ import annotations


def test_initial_pending_is_none(make_client):
    node = make_client()
    assert node._pending_policy_path is None


def test_preload_success_sets_pending(make_client):
    node = make_client()
    assert node.send_preload_policy('/B') is True
    assert node._pending_policy_path == '/B'


def test_preload_failure_keeps_pending_none(make_client):
    node = make_client()
    node._command_client.response_factory = lambda req: type('R', (), {
        'success': False, 'message': 'bad'})()
    assert node.send_preload_policy('/B') is False
    assert node._pending_policy_path is None


def test_cancel_clears_pending(make_client):
    node = make_client()
    node.send_preload_policy('/B')
    assert node._pending_policy_path == '/B'
    node.send_cancel_preload()
    assert node._pending_policy_path is None


def test_swap_promotes_pending_to_current(make_client):
    node = make_client()
    node._current_policy_path = '/A'
    node.send_preload_policy('/B')
    assert node._pending_policy_path == '/B'
    assert node._current_policy_path == '/A'
    node.send_swap_policy()
    assert node._current_policy_path == '/B'
    assert node._pending_policy_path is None


def test_failed_swap_does_not_promote(make_client):
    node = make_client()
    node._current_policy_path = '/A'
    node.send_preload_policy('/B')
    node._command_client.response_factory = lambda req: type('R', (), {
        'success': False, 'message': 'not ready'})()
    node.send_swap_policy()
    # current path unchanged on failure
    assert node._current_policy_path == '/A'


def test_swap_updates_ros_policy_path_parameter(make_client):
    node = make_client()
    node._current_policy_path = '/A'
    node.parameters['policy_path'] = '/A'
    node.send_preload_policy('/B')
    node.send_swap_policy()
    assert node.parameters['policy_path'] == '/B'
