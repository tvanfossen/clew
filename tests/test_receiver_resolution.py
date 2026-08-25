# SPDX-License-Identifier: MIT
"""Resolving a member call by the receiver's DECLARED type (#482).

`handle->engine->run_turn(input)` used to produce no edge at all, and that looked like a
principled refusal: the receiver's type was never checked, so asserting a target would be a
fabrication. It was a principled refusal to read evidence the index already held —
`memberdef.type` records that `engine` is a `std::unique_ptr< entropic::AgentEngine >`, so the
class that owns the method is a DOCUMENTED FACT, not an inference.

MEASURED ON entropic, before and after: 3073 resolved AST edges became 5040, plus 34 fuzzy,
with the facade-to-core boundary crossed for the first time.

FOUR NARROWING RULES WERE WRONG BEFORE THIS ONE, each caught by measuring the built index
rather than by reasoning, and each gets a test below because each is a live regression risk:

  1. UNION — accept a candidate matching ANY of the receiver's declared classes. 56 fuzzy
     groups then spanned several classes, `parse_tool_calls` reaching five classes in five
     files: the gh#347 fan-out with a type-resolution costume.
  2. SINGLE CLASS ONLY — refuse whenever the receiver name is declared more than once. Too
     strict: `engine` is declared in four classes on entropic, so `run_turn` refused again.
  3. COUNTING TYPE SPELLINGS — `entropic::AgentEngine` and `AgentEngine` are the same class
     written two ways, so counting spellings saw two owners where the index has one scope.
  4. UNGATED FUZZY — emitting the survivor set without checking the narrowing actually
     narrowed. When nothing matched, "survivors" was the untouched candidate list, so this put
     11,390 fuzzy edges into one build.

The surviving rule: intersect the receiver's possible classes with the classes that actually
declare the method, count DISTINCT SCOPES, and require exactly one.
"""

from __future__ import annotations

from clew.call_edges import _narrow_by_receiver, _receiver_class

## One method name, four definitions — the real shape on entropic.
ENGINE_A = 176  # entropic::AgentEngine::run_turn(const std::string&)
ENGINE_B = 180  # entropic::AgentEngine::run_turn(std::vector<Message>)
HELPER_A = 2132  # anonymous_namespace{...benchmark.cpp}::run_turn
HELPER_B = 2133  # anonymous_namespace{...feasibility.cpp}::run_turn

SCOPE_OF = {
    ENGINE_A: "entropic::AgentEngine",
    ENGINE_B: "entropic::AgentEngine",
    HELPER_A: "anonymous_namespace{test_gh108_agentic_benchmark.cpp}",
    HELPER_B: "anonymous_namespace{test_gh108_cpu_feasibility.cpp}",
}
ARGC_OF = {ENGINE_A: 1, ENGINE_B: 1, HELPER_A: 4, HELPER_B: 4}
ALL = [ENGINE_A, ENGINE_B, HELPER_A, HELPER_B]


##
# @brief A declared type must reduce to the class that owns the method.
# @return None.
# @version 1
def test_a_declared_type_reduces_to_its_class() -> None:
    """The wrapper is the common case, not the exception: a receiver is almost always a smart
    pointer, a raw pointer or a reference. `auto` and a multi-argument template name no single
    class and must return '' so the caller falls through to refusing.

    @brief Type strings reduce to class names, or to '' when they name none.
    @return None.
    @version 1
    """
    assert _receiver_class("std::unique_ptr< entropic::AgentEngine >") == "entropic::AgentEngine"
    assert _receiver_class("AgentEngine *") == "AgentEngine"
    assert _receiver_class("const Foo &") == "Foo"
    assert _receiver_class("std::shared_ptr< std::unique_ptr< Foo > >") == "Foo"
    assert _receiver_class("auto") == "", "`auto` names no class"
    assert _receiver_class("std::map< K, V >") == "", "a two-argument template names no receiver"
    assert _receiver_class("") == ""


##
# @brief The intersection must pin the class even when the receiver name is ambiguous.
# @return None.
# @version 1
def test_the_intersection_pins_the_class_a_name_alone_cannot() -> None:
    """RULE 2 WAS TOO STRICT AND THIS IS THE CASE THAT PROVES IT. `engine` is declared in four
    classes on entropic, so refusing on an ambiguous receiver name refuses the very call this
    feature exists for. Only ONE of those classes declares `run_turn`, so the PAIR pins it
    where neither half does alone.

    @brief An ambiguous receiver name still resolves when only one of its classes owns the
    method.
    @return None.
    @version 1
    """
    classes = {"engine": {"entropic::AgentEngine", "AgentEngine", "EntropicEngine", "ChessEngine"}}
    survivors, verified = _narrow_by_receiver("engine", 1, ALL, classes, SCOPE_OF, ARGC_OF)
    assert verified, "the receiver's type identified the owning class and should count as such"
    assert set(survivors) == {ENGINE_A, ENGINE_B}, (
        f"the two file-local helpers must be ELIMINATED, not merely deprioritised — the "
        f"receiver's declared type says they cannot be the target. Got {survivors}"
    )


##
# @brief Two spellings of one class are one owner, not two.
# @return None.
# @version 1
def test_two_spellings_of_one_class_are_one_owner() -> None:
    """RULE 3. `std::unique_ptr< entropic::AgentEngine >` and `AgentEngine *` are the same
    class; the index holds ONE scope for it. Counting type spellings saw two owners and refused,
    which is why the fix counts distinct SCOPES instead.

    @brief A qualified and an unqualified spelling do not make the receiver ambiguous.
    @return None.
    @version 1
    """
    classes = {"engine": {"entropic::AgentEngine", "AgentEngine"}}
    survivors, verified = _narrow_by_receiver("engine", 1, ALL, classes, SCOPE_OF, ARGC_OF)
    assert verified and set(survivors) == {ENGINE_A, ENGINE_B}, (
        f"two spellings of one class were treated as two owners: verified={verified} "
        f"survivors={survivors}"
    )


##
# @brief A receiver whose classes all own the method must refuse.
# @return None.
# @version 1
def test_a_receiver_owned_by_several_classes_refuses() -> None:
    """RULE 1, the fan-out. When the method exists on more than one of the receiver's possible
    classes, nothing here distinguishes them — `parse_tool_calls` on entropic exists on five —
    so the narrowing must report NOT verified and let the caller emit nothing. Returning the
    survivors as though they were verified is how 56 groups came to span several classes.

    @brief Several owning classes means unverified.
    @return None.
    @version 1
    """
    scope_of = {1: "ClassA", 2: "ClassB"}
    classes = {"parser": {"ClassA", "ClassB"}}
    survivors, verified = _narrow_by_receiver("parser", 0, [1, 2], classes, scope_of, {})
    assert not verified, (
        "two of the receiver's classes own this method, so the class is not pinned and no edge "
        "may be asserted"
    )
    assert survivors == [1, 2], "an unverified narrowing must leave the candidates untouched"


##
# @brief An unknown receiver leaves the candidates untouched and unverified.
# @return None.
# @version 1
def test_an_unknown_receiver_changes_nothing() -> None:
    """RULE 4's other half. A receiver that is a local, a parameter, an `auto`, or simply not
    indexed must return the input unchanged AND `verified=False`, so the caller falls through to
    the existing refusal. Reporting a narrowing here is what let the untouched candidate list be
    emitted as fuzzy — 11,390 edges in one build.

    @brief An unresolvable receiver is not a narrowing.
    @return None.
    @version 1
    """
    for receiver in ("", "not_indexed", "local_var"):
        survivors, verified = _narrow_by_receiver(receiver, 1, ALL, {}, SCOPE_OF, ARGC_OF)
        assert not verified, f"receiver {receiver!r} verified nothing"
        assert survivors == ALL, "candidates must pass through untouched"


##
# @brief Argument count separates overloads when it can.
# @return None.
# @version 1
def test_arity_separates_overloads_when_it_can() -> None:
    """Arity is the second narrowing, applied only after the class is pinned. On entropic it
    cannot help — both `run_turn` overloads take one argument — which is why the overload set
    is emitted as FUZZY rather than resolved. Where arities differ it does resolve, and that is
    worth pinning so the term is not quietly dropped as useless.

    @brief A differing argument count picks one overload.
    @return None.
    @version 1
    """
    classes = {"engine": {"entropic::AgentEngine"}}
    argc_of = {ENGINE_A: 1, ENGINE_B: 2, HELPER_A: 4, HELPER_B: 4}
    survivors, verified = _narrow_by_receiver("engine", 2, ALL, classes, SCOPE_OF, argc_of)
    assert verified and survivors == [ENGINE_B], (
        f"a call passing two arguments must select the two-parameter overload: {survivors}"
    )
