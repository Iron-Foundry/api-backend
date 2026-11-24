"""Resolve the variable tags the game writes into clan broadcast text.

A broadcast can set a variable (``<int_0=280000>``, ``<str_quest_name_0=...>``)
and then print it (``<int_0:spacer>``, ``<str_quest_name_0>``) or pick a word
by it (``<switch,int_p1,he's,she's,they're>``). Tags resolve left to right,
so a variable set twice prints its newest value. The escape tags ``<lt>``,
``<gt>`` and ``<at>`` become their symbols after that pass.
"""

from __future__ import annotations

import re

_VARIABLE = r"(?:int|str)_\w+"
_TAG_RE = re.compile(
    rf"<(?:(?P<name>{_VARIABLE})=(?P<value>[^>]*)"
    rf"|(?P<ref>{_VARIABLE})(?P<spacer>:spacer)?"
    rf"|switch,(?P<switch>{_VARIABLE}),(?P<options>[^>]*))>"
)
_ESCAPES = {"lt": "<", "gt": ">", "at": "@"}
_ESCAPE_RE = re.compile(r"<(lt|gt|at)>")


def _spaced(value: str) -> str:
    """Return an integer value with thousands separators, as the chatbox shows it."""
    return f"{int(value):,}" if value.lstrip("-").isdigit() else value


def _switch_option(index: str | None, options: str) -> str | None:
    """Return the option at ``index``, or None when the index does not select one."""
    choices = options.split(",")
    if index is None or not index.isdigit() or int(index) >= len(choices):
        return None
    return choices[int(index)]


def render_broadcast(message: str) -> str:
    """Return the message with each variable tag and escape tag resolved.

    A tag that names an unset variable, or a switch index out of range, stays
    as sent so the message still reaches the unknown-broadcast path intact.
    Escapes resolve last so an escaped ``<`` never opens a variable tag.
    """
    values: dict[str, str] = {}

    def resolved(match: re.Match[str]) -> str:
        if name := match.group("name"):
            values[name] = match.group("value")
            return ""
        if ref := match.group("ref"):
            if ref not in values:
                return match.group(0)
            return _spaced(values[ref]) if match.group("spacer") else values[ref]
        option = _switch_option(
            values.get(match.group("switch")), match.group("options")
        )
        return match.group(0) if option is None else option

    rendered = _TAG_RE.sub(resolved, message)
    return _ESCAPE_RE.sub(lambda match: _ESCAPES[match.group(1)], rendered)
