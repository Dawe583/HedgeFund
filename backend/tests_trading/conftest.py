"""Suite-wide event-loop discipline for the kernel desk tests.

The failure this fixes, measured in the full-suite combination runs of
2026-11-26: nautilus's live TradingNode calls `asyncio.get_event_loop()` at
construction, pytest-asyncio (auto mode, backend/pyproject.toml) closes the
main thread's loop as its own lifecycle manages loops per async test, and
every sync test that builds a node after that point dies with 'No event
loop available in test environment' — a pytest-asyncio error about ITS
loop management, not about anything the test did. The failure was
ordering-dependent and load-scaled: which test died depended on where in
the alphabet the loop was consumed, never on the test's own content.

The fixture is autouse and function-scoped: every test starts with a fresh
loop as the main thread's current loop, the state plain asyncio guarantees
outside pytest-asyncio's management. Loops are deliberately NOT closed at
teardown: desk nodes run the kernel on daemon threads whose asyncio
internals may still reference the loop after the test body returns, and a
premature close trades the ordering flake for a 'Event loop is closed'
one. CPython warns about unclosed loops at interpreter exit; the
alternative is a flaky suite, and the warning carries no information the
suite doesn't already know.
"""

import asyncio

import pytest


@pytest.fixture(autouse=True)
def _fresh_main_thread_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield
    asyncio.set_event_loop(None)
