"""Contract tests: the MCP wrapper surface must match the tools it exposes.

Why this exists
---------------
mcp_server.py is the tool definition layer. FastMCP builds each tool's JSON
Schema by introspecting the wrapper's name, type hints and docstring — never
tools.py. So when a parameter is renamed in tools.py and the wrapper is not
updated, the published schema is wrong and the failure appears at call time, in
whichever request happens to use that tool.

That is exactly what happened when the PTO tool moved from requested_hours to
days_requested: agent.py kept calling the old name and nothing caught it until a
request failed.

These tests need no database and no AWS. They are safe for CI.
"""
from __future__ import annotations

import inspect
import re

from quantic_hr import mcp_server, tools

# Every tool the agent may call, mapped to the function that implements it.
TOOL_MAP = {
    "search_policy_documents": tools.search_policy_documents,
    "get_policy_section": tools.get_policy_section,
    "lookup_employee_profile": tools.lookup_employee_profile,
    "check_pto_balance": tools.check_pto_balance,
    "lookup_benefits_status": tools.lookup_benefits_status,
    "check_policy_compliance": tools.check_policy_compliance,
    "draft_hr_email": tools.draft_hr_email,
    "create_mock_hr_ticket": tools.create_mock_hr_ticket,
}

# Tools that write. These must never run without explicit confirmation.
WRITE_TOOLS = {"create_mock_hr_ticket"}


def _parameters(func) -> dict[str, inspect.Parameter]:
    return {
        name: p for name, p in inspect.signature(func).parameters.items()
        if name != "self"
    }


def test_every_tool_has_a_wrapper():
    for name in TOOL_MAP:
        assert hasattr(mcp_server, name), f"{name} is not exposed by mcp_server.py"


def test_wrapper_signatures_match_tools():
    """A renamed parameter in tools.py must be reflected in the wrapper."""
    for name, impl in TOOL_MAP.items():
        wrapper = getattr(mcp_server, name)
        assert inspect.signature(wrapper) == inspect.signature(impl), (
            f"{name}: wrapper signature {inspect.signature(wrapper)} does not match "
            f"tools.py {inspect.signature(impl)}"
        )


def test_parameter_names_and_defaults_match():
    """Catches a default that differs, which would change the published schema."""
    for name, impl in TOOL_MAP.items():
        wrapper = _parameters(getattr(mcp_server, name))
        source = _parameters(impl)
        assert set(wrapper) == set(source), f"{name}: parameter names differ"
        for param, spec in source.items():
            assert wrapper[param].default == spec.default, (
                f"{name}.{param}: default {wrapper[param].default!r} != {spec.default!r}"
            )


def test_docstrings_describe_input_and_output():
    """The wrapper docstring is the only channel carrying semantics to the model.

    Reward the Args/Returns structure: without it the model sees a tool name and
    parameter names, and selects by name alone.
    """
    for name in TOOL_MAP:
        doc = (getattr(mcp_server, name).__doc__ or "").strip()
        assert doc, f"{name}: wrapper has no docstring"
        assert "Args:" in doc, f"{name}: docstring has no Args section"
        assert "Returns:" in doc, f"{name}: docstring has no Returns section"
        assert len(doc) > 120, f"{name}: docstring is too short to guide selection"


def test_docstrings_mention_when_to_use():
    """A 'Use ...' sentence is what separates two tools with similar names."""
    for name in TOOL_MAP:
        doc = (getattr(mcp_server, name).__doc__ or "").lower()
        assert re.search(r"\buse\b", doc), f"{name}: docstring does not say when to use it"


def test_write_tools_document_confirmation():
    """The one write path must state that confirmation is required."""
    for name in WRITE_TOOLS:
        doc = (getattr(mcp_server, name).__doc__ or "").lower()
        assert "confirm" in doc, f"{name}: docstring does not mention confirmation"


def test_units_are_days_not_hours():
    """The corpus is in days throughout; hours means a stale signature."""
    days_params = {
        "check_pto_balance": "days_requested",
        "check_policy_compliance": "days_requested",
    }
    for tool_name, param in days_params.items():
        params = _parameters(TOOL_MAP[tool_name])
        assert param in params, f"{tool_name}: expected parameter {param}"
        assert "hours" not in param, f"{tool_name}.{param} uses hours"
        assert not any("hours" in p for p in params), (
            f"{tool_name}: an hours parameter is still present"
        )
