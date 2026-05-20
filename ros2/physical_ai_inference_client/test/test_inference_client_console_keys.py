"""P.4 Console menu dispatch — every key maps to the right handler."""
from __future__ import annotations


def test_console_help_text_lists_new_keys(monkeypatch, make_client):
    node = make_client()

    prompts = []

    def fake_input(p):
        prompts.append(p)
        raise EOFError

    monkeypatch.setattr('builtins.input', fake_input)
    node.run_console()
    joined = ' '.join(prompts) + ' '.join(
        msg for _, msg in node.logger.messages)
    assert '[p]' in joined or 'preload' in joined
    assert '[w]' in joined or 'swap' in joined
    assert '[c]' in joined or 'cancel' in joined


def test_console_dispatch_p_w_c(monkeypatch, make_client):
    node = make_client()
    calls = []
    node._handle_preload_input = lambda: calls.append('p')
    node.send_swap_policy = lambda: calls.append('w') or True
    node.send_cancel_preload = lambda: calls.append('c') or True
    # also keep s/f handlers callable
    node._handle_start_input = lambda: calls.append('s')
    node.send_finish = lambda: calls.append('f') or True

    inputs = iter(['p', 'w', 'c', 's', 'f', 'q'])

    monkeypatch.setattr('builtins.input', lambda p: next(inputs))
    node.run_console()
    assert calls == ['p', 'w', 'c', 's', 'f']


def test_console_unknown_key_prints_help(monkeypatch, make_client, capsys):
    node = make_client()
    inputs = iter(['zzz', 'q'])
    monkeypatch.setattr('builtins.input', lambda p: next(inputs))
    node.run_console()
    out = capsys.readouterr().out
    assert 'Unknown input' in out


def test_console_eof_exits_gracefully(monkeypatch, make_client):
    node = make_client()
    monkeypatch.setattr('builtins.input', lambda p: (_ for _ in ()).throw(
        EOFError))
    result = node.run_console()
    assert result is True


def test_console_q_exits_gracefully(monkeypatch, make_client):
    node = make_client()
    inputs = iter(['q'])
    monkeypatch.setattr('builtins.input', lambda p: next(inputs))
    result = node.run_console()
    assert result is True
