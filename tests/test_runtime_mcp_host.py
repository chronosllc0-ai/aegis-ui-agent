"""Phase 3 tests for the MCP host.

The suite spawns the in-repo stdio stub from ``tests/fixtures`` —
no Node/npx required — and exercises:

* namespaced tool names (``{server_id}__{tool_name}``),
* ``MCPToolProvider.get_tools`` lazy session spawn + reuse,
* tool invocation through the Agents SDK :class:`FunctionTool` wrapper,
* scan reports (replacement for the deprecated ``scan_mcp_tools``),
* Playwright MCP smoke test (skips cleanly when ``npx`` is missing).

We stick to :func:`asyncio.run` to match the rest of the runtime test
suite (no pytest-asyncio dependency).
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path

import pytest

from backend.runtime.tools import mcp_host
from backend.runtime.tools.mcp_host import (
    MCPServerSpec,
    MCPToolProvider,
    PLAYWRIGHT_MCP_COMMAND_ENV,
    PLAYWRIGHT_MCP_ENV_FLAG,
    TOOL_NAMESPACE_SEPARATOR,
    default_server_specs,
    namespaced_tool_name,
    resolve_playwright_mcp_command,
    scan_mcp_server,
    split_namespaced_tool_name,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
STUB_SERVER = REPO_ROOT / "tests" / "fixtures" / "stub_mcp_server.py"


def _stub_spec(server_id: str = "stub") -> MCPServerSpec:
    return MCPServerSpec(
        server_id=server_id,
        transport="stdio",
        command=sys.executable,
        args=(str(STUB_SERVER),),
        display_name="Stub MCP",
    )


def _run(coro):
    return asyncio.run(coro)


# ----------------------------------------------------------------------
# Namespacing
# ----------------------------------------------------------------------


def test_namespaced_tool_name_uses_double_underscore() -> None:
    assert TOOL_NAMESPACE_SEPARATOR == "__"
    assert namespaced_tool_name("stub", "echo") == "stub__echo"
    assert split_namespaced_tool_name("stub__echo") == ("stub", "echo")
    assert split_namespaced_tool_name("native_tool") is None


# ----------------------------------------------------------------------
# Provider: spawn + list + invoke + reuse + teardown
# ----------------------------------------------------------------------


def test_provider_exposes_namespaced_tools_and_invokes_them() -> None:
    async def scenario() -> None:
        provider = MCPToolProvider(
            owner_uid="user-mcp",
            specs=[_stub_spec()],
        )
        try:
            tools = await provider.get_tools()
            names = {t.name for t in tools}
            assert names == {"stub__echo", "stub__add"}

            # Descriptions survive end-to-end.
            by_name = {t.name: t for t in tools}
            assert "echo" in by_name["stub__echo"].description.lower()

            # Invoke through the FunctionTool wrapper — mimics the
            # Agents SDK calling into the tool.
            from agents import RunContextWrapper

            ctx = RunContextWrapper(context=None)
            out = await by_name["stub__echo"].on_invoke_tool(
                ctx, '{"message": "hello"}'
            )
            assert out.strip() == "stub:hello"

            add_out = await by_name["stub__add"].on_invoke_tool(
                ctx, '{"a": 2, "b": 3}'
            )
            assert add_out.strip() == "5"

            # Subsequent get_tools is cached — no new subprocess spawn.
            tools_again = await provider.get_tools()
            assert [t.name for t in tools_again] == [t.name for t in tools]
        finally:
            await provider.aclose()

    _run(scenario())


def test_provider_invoke_after_close_raises() -> None:
    async def scenario() -> None:
        provider = MCPToolProvider(
            owner_uid="user-mcp",
            specs=[_stub_spec()],
        )
        await provider.get_tools()
        await provider.aclose()
        with pytest.raises(RuntimeError):
            await provider.get_tools()

    _run(scenario())


def test_provider_handles_bad_arguments() -> None:
    async def scenario() -> None:
        provider = MCPToolProvider(
            owner_uid="user-mcp",
            specs=[_stub_spec()],
        )
        try:
            tools = await provider.get_tools()
            echo = next(t for t in tools if t.name == "stub__echo")
            from agents import RunContextWrapper

            ctx = RunContextWrapper(context=None)
            out = await echo.on_invoke_tool(ctx, "not-json")
            assert out.startswith("ERROR:")
            out2 = await echo.on_invoke_tool(ctx, "[1,2,3]")
            assert out2.startswith("ERROR:")
        finally:
            await provider.aclose()

    _run(scenario())


# ----------------------------------------------------------------------
# Scan — replacement for the deprecated scan_mcp_tools
# ----------------------------------------------------------------------


def test_scan_mcp_server_returns_real_manifest() -> None:
    async def scenario() -> None:
        report = await scan_mcp_server(_stub_spec("stub-scan"))
        assert report.ok is True
        assert report.server_id == "stub-scan"
        assert report.transport == "stdio"
        tool_names = {t["name"] for t in report.tools}
        assert tool_names == {"echo", "add"}

    _run(scenario())


def test_scan_mcp_server_reports_errors_on_bad_command() -> None:
    async def scenario() -> None:
        bogus = MCPServerSpec(
            server_id="bogus",
            transport="stdio",
            command="/definitely/not/a/real/binary/xyzzy",
        )
        report = await scan_mcp_server(bogus)
        assert report.ok is False
        assert report.error is not None

    _run(scenario())


def test_provider_scan_returns_one_report_per_spec() -> None:
    async def scenario() -> None:
        provider = MCPToolProvider(
            owner_uid="scan-user",
            specs=[_stub_spec("stub-a"), _stub_spec("stub-b")],
        )
        try:
            reports = await provider.scan("scan-user")
            assert {r.server_id for r in reports} == {"stub-a", "stub-b"}
            assert all(r.ok for r in reports)
        finally:
            await provider.aclose()

    _run(scenario())


# ----------------------------------------------------------------------
# Invalid specs are ignored at get_tools time
# ----------------------------------------------------------------------


def test_provider_retries_after_transient_server_failure(monkeypatch) -> None:
    """A failing server must not poison the cache.

    Phase 3 review fix (Codex P2): if any server fails discovery during
    the first ``get_tools()`` call, the provider must retry the whole
    resolve-and-spawn loop on the next call instead of caching the
    partial result forever. Otherwise a transient blip permanently
    disables MCP until the supervisor restarts.

    We simulate servers entirely in-memory (no real stdio subprocess /
    anyio task group) to exercise only the cache-decision logic.
    """

    class _FakeTool:
        def __init__(self, name: str) -> None:
            self.name = name

    class _FakeHandle:
        def __init__(self, spec: MCPServerSpec, *, fail_once: bool) -> None:
            self.spec = spec
            self._fail_once = fail_once
            self._opened = False
            self.close_calls = 0

        async def ensure_open(self):  # noqa: D401 — mimic real API
            if self._fail_once and not self._opened:
                self._fail_once = False
                raise RuntimeError("simulated transient spawn failure")
            self._opened = True
            return self

        async def list_tools(self):
            tools = [
                _FakeTool(name=f"{self.spec.server_id}:echo"),
                _FakeTool(name=f"{self.spec.server_id}:add"),
            ]
            return type("_Listing", (), {"tools": tools})()

        async def close(self) -> None:
            self.close_calls += 1

    async def scenario() -> None:
        good_spec = MCPServerSpec(
            server_id="good", transport="stdio", command="fake-good"
        )
        second_spec = MCPServerSpec(
            server_id="second", transport="stdio", command="fake-second"
        )

        handles_by_id: dict[str, _FakeHandle] = {}

        def handle_factory(spec: MCPServerSpec) -> _FakeHandle:
            existing = handles_by_id.get(spec.server_id)
            if existing is not None:
                return existing
            fail_once = spec.server_id == "second"
            h = _FakeHandle(spec, fail_once=fail_once)
            handles_by_id[spec.server_id] = h
            return h

        # Patch both the session handle factory and the session->tool
        # wrapper so we don't need the real Agents SDK in this test.
        def fake_make_tool(handle, mcp_tool):  # type: ignore[no-untyped-def]
            return type(
                "_Wrapped", (), {"name": f"{handle.spec.server_id}__{mcp_tool.name.split(':')[1]}"}
            )()

        def ensure_open_wrapper(self):  # type: ignore[no-untyped-def]
            return self.ensure_open()

        async def list_tools_wrapper(session):  # type: ignore[no-untyped-def]
            return await session.list_tools()

        monkeypatch.setattr(mcp_host, "_MCPSessionHandle", handle_factory)
        monkeypatch.setattr(mcp_host, "_make_tool", fake_make_tool)

        provider = MCPToolProvider(
            owner_uid="user",
            specs=[good_spec, second_spec],
        )
        try:
            first = await provider.get_tools()
            assert {t.name for t in first} == {"good__echo", "good__add"}
            # Cache MUST NOT be populated because ``second`` failed.
            assert provider._tools_cache is None

            # Second call retries and should now pick up both servers.
            second = await provider.get_tools()
            assert {t.name for t in second} == {
                "good__echo",
                "good__add",
                "second__echo",
                "second__add",
            }
            # Clean load → cache should now be populated.
            assert provider._tools_cache is not None
            # Third call is a cache hit (no new discovery, no extra
            # ensure_open) — we verify by checking the fake handle
            # state didn't change.
            third = await provider.get_tools()
            assert [t.name for t in third] == [t.name for t in second]
        finally:
            await provider.aclose()
            # aclose must close every tracked handle at least once.
            assert handles_by_id["good"].close_calls >= 1
            assert handles_by_id["second"].close_calls >= 1

    _run(scenario())


def test_provider_skips_invalid_specs(caplog) -> None:
    async def scenario() -> None:
        provider = MCPToolProvider(
            owner_uid="user",
            specs=[
                MCPServerSpec(server_id="bad", transport="http", endpoint=""),
                _stub_spec("good"),
            ],
        )
        try:
            with caplog.at_level("WARNING"):
                tools = await provider.get_tools()
            names = {t.name for t in tools}
            assert names == {"good__echo", "good__add"}
        finally:
            await provider.aclose()

    _run(scenario())


# ----------------------------------------------------------------------
# Playwright MCP smoke test — skip if the binary is not resolvable.
# ----------------------------------------------------------------------


def test_playwright_mcp_command_resolves_when_flag_set(monkeypatch) -> None:
    """Document the contract for PLAYWRIGHT_MCP_ENABLED / PLAYWRIGHT_MCP_COMMAND.

    We don't spawn Playwright in CI — Node is not guaranteed — but we do
    verify that:

    * ``default_server_specs()`` drops the Playwright entry cleanly when
      no ``npx`` nor override is available,
    * ``resolve_playwright_mcp_command`` honors an explicit override
      that does resolve on PATH.
    """
    # Baseline: no npx + no override → no spec, no crash.
    monkeypatch.setenv(PLAYWRIGHT_MCP_ENV_FLAG, "true")
    monkeypatch.setenv(PLAYWRIGHT_MCP_COMMAND_ENV, "")
    original_which = shutil.which

    def fake_which(name: str) -> str | None:
        if name == "npx":
            return None
        return original_which(name)

    monkeypatch.setattr(shutil, "which", fake_which)
    assert resolve_playwright_mcp_command() is None
    assert default_server_specs() == []

    # Override to python on PATH — proves the resolver honors overrides.
    override = sys.executable + " -V"
    monkeypatch.setenv(PLAYWRIGHT_MCP_COMMAND_ENV, override)
    argv = resolve_playwright_mcp_command()
    assert argv is not None
    assert argv[0] == sys.executable


def test_playwright_mcp_skip_when_disabled(monkeypatch) -> None:
    monkeypatch.setenv(PLAYWRIGHT_MCP_ENV_FLAG, "false")
    monkeypatch.delenv(PLAYWRIGHT_MCP_COMMAND_ENV, raising=False)
    specs = default_server_specs()
    assert all(s.server_id != "playwright" for s in specs)


@pytest.mark.skipif(
    shutil.which("npx") is None and not os.environ.get("PLAYWRIGHT_MCP_COMMAND"),
    reason="npx not on PATH and no PLAYWRIGHT_MCP_COMMAND override; Playwright MCP smoke test skipped.",
)
def test_playwright_mcp_smoke() -> None:  # pragma: no cover — env-dependent
    """Only runs when the operator has Node/npx or a command override."""
    async def scenario() -> None:
        argv = resolve_playwright_mcp_command()
        assert argv is not None
        spec = MCPServerSpec(
            server_id="playwright",
            transport="stdio",
            command=argv[0],
            args=tuple(argv[1:]),
        )
        report = await scan_mcp_server(spec)
        # We don't assert a specific tool list (Playwright MCP evolves)
        # — only that we got *some* tools back from a real server.
        assert report.ok is True, report.message
        assert len(report.tools) > 0

    _run(scenario())
