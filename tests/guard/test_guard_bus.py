"""The bus-tag rule (1.4.0 W10, #67's fifth consumer).

A function that CROSSES A BUS must say so with a bus tag (`@emits MQTT cmd/req`, `@handles ...`).
The rule is SCOPED, never blanket — only functions whose name matches a configured handler glob, or
whose body calls a configured sender — and it HONOURS THE EXISTING EXEMPTIONS (`@callback`,
`@utility`, `@dg_internal`). A bus name outside the configured vocabulary is refused. With no
`validate.bus` section the rule does nothing.

@brief Tests for clew.guard.checks.check_bus_tags.
@version 1
"""

from __future__ import annotations

from clew.guard.checks import check_bus_tags, check_unknown_tags
from clew.guard.config import validate_config_schema
from clew.guard.parser import DoxygenBlock, Function

_BUS = {
    "validate": {
        ## 2.0.0 (R5-CFG F10): the bus tags are the event vocabulary (`event_tags:` / the index's
        ## built-in words); `validate.bus.tags` moved there.
        "bus": {
            "vocabulary": ["MQTT", "HTTP"],
            "handlers": ["on_*"],
            "senders": ["publish"],
        }
    }
}


## @brief A documented function with the given tags, spanning lines 2..4.
## @param name The function name.
## @param tags Extra tags.
## @return The Function.
## @version 1
def _fn(name: str, **tags: list[str]) -> Function:
    """@brief Make a function. @return Function."""
    block = DoxygenBlock(start_line=0, end_line=1, tags={"brief": ["x"], "version": ["1"], **tags})
    return Function(name=name, def_line=2, body_end=4, doxygen=block)


def _lines(body: str) -> list[str]:
    return ["## @brief x", "## @version 1", "def f():", f"    {body}", "    return 1"]


def test_a_handler_without_a_bus_tag_is_a_violation() -> None:
    """@brief A name matching a handler glob must carry a bus tag."""
    out = check_bus_tags([_fn("on_message")], "a.py", _BUS, _lines("pass"))
    assert len(out) == 1 and "on_message" in out[0].message and out[0].check == "bus"


def test_a_tagged_handler_passes_and_exemptions_are_honoured() -> None:
    """THE EXISTING EXEMPTION MODEL, reused: a blanket rule would push repos to exempt everything.

    @brief A bus tag or an exemption tag satisfies the rule.
    """
    tagged = _fn("on_message", handles=["MQTT cmd/req"])
    exempt = _fn("on_click", callback=[""])
    assert check_bus_tags([tagged, exempt], "a.py", _BUS, _lines("pass")) == []


def test_a_caller_of_a_sender_must_name_the_bus() -> None:
    """THE CROSSING IS THE CALLER THAT CHOOSES THE TOPIC (#67, Python consumer), not only a named
    handler.

    @brief A body that calls a configured sender is in scope; the sender itself is not.
    """
    caller = _fn("send_status")
    sender = _fn("publish")
    out = check_bus_tags([caller, sender], "a.py", _BUS, _lines("publish(topic, data)"))
    assert [v.message.split("'")[1] for v in out] == ["send_status"]


def test_a_bus_outside_the_vocabulary_is_refused() -> None:
    """@brief `@emits KAFKA x` names a bus the vocabulary does not hold."""
    out = check_bus_tags([_fn("on_x", emits=["KAFKA x"])], "a.py", _BUS, _lines("pass"))
    assert len(out) == 1 and "KAFKA" in out[0].message


def test_no_bus_section_means_no_rule() -> None:
    """@brief Unconfigured, the rule checks nothing."""
    assert check_bus_tags([_fn("on_message")], "a.py", {"validate": {}}, _lines("pass")) == []


def test_bus_tags_are_known_tags_when_configured() -> None:
    """@brief A configured bus tag is not reported as unknown."""
    assert check_unknown_tags(_fn("on_x", emits=["MQTT x"]), "a.py", _BUS) == []


def test_the_bus_section_is_part_of_the_validated_schema() -> None:
    """@brief `validate.bus` is accepted; an unknown key inside it is not."""
    assert validate_config_schema(_BUS) == []
    bad = {"validate": {"bus": {"vocabulary": ["MQTT"], "colour": "blue"}}}
    assert validate_config_schema(bad)
