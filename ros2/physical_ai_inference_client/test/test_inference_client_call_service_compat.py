"""P.3 _call_service backward compatibility — the new response_timeout_s
argument must not break existing callers that pass only 3 positional args."""
from __future__ import annotations

import inspect


def test_call_service_signature_accepts_response_timeout_kwarg(make_client):
    """The new kwarg must be optional with a default of None so existing
    callers (send_start_inference, send_stop, send_finish) still work."""
    node = make_client()
    sig = inspect.signature(node._call_service)
    assert 'response_timeout_s' in sig.parameters
    assert sig.parameters['response_timeout_s'].default is None


def test_existing_callers_unchanged_signature_works(make_client):
    """send_start_inference / send_stop / send_finish call _call_service
    with only the original 3 positional args. They must still succeed."""
    node = make_client()
    # send_finish uses the original 3-arg call pattern
    ok = node.send_finish()
    assert ok is True
    req = node._command_client.calls[-1]
    assert req.command == 6  # FINISH


def test_swap_uses_larger_response_timeout(make_client):
    """send_swap_policy should override response_timeout_s with the larger
    swap_response_timeout_s parameter value."""
    node = make_client()
    captured = {}
    original = node._call_service

    def spy(client, request, service_name, response_timeout_s=None):
        captured['response_timeout_s'] = response_timeout_s
        return original(client, request, service_name,
                        response_timeout_s=response_timeout_s)

    node._call_service = spy
    node.send_swap_policy()
    assert captured['response_timeout_s'] == node.parameters[
        'swap_response_timeout_s']


def test_preload_uses_preload_response_timeout(make_client):
    """send_preload_policy must override response_timeout_s with
    preload_response_timeout_s since PRELOAD is now sync and may take
    tens of seconds."""
    node = make_client()
    captured = {}
    original = node._call_service

    def spy(client, request, service_name, response_timeout_s=None):
        captured['response_timeout_s'] = response_timeout_s
        return original(client, request, service_name,
                        response_timeout_s=response_timeout_s)

    node._call_service = spy
    node.send_preload_policy('/X')
    assert captured['response_timeout_s'] == node.parameters[
        'preload_response_timeout_s']


def test_swap_response_timeout_s_parameter_declared(make_client):
    node = make_client()
    assert 'swap_response_timeout_s' in node.parameters
    val = node.parameters['swap_response_timeout_s']
    assert isinstance(val, (int, float))
    assert val > 0


def test_preload_response_timeout_s_parameter_declared(make_client):
    node = make_client()
    assert 'preload_response_timeout_s' in node.parameters
    val = node.parameters['preload_response_timeout_s']
    assert isinstance(val, (int, float))
    assert val > 0
    # should be at least as long as the swap response timeout — the worker
    # has to actually load the model
    assert val >= node.parameters['swap_response_timeout_s']
