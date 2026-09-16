# SPDX-License-Identifier: MIT
"""Which index of a repository answers, and what to say when none can (gh#48).

A SPLIT REPOSITORY OWNS SEVERAL DATABASES, and before this module the server could only see the
ones its own registry recorded. B12_single_rgb had six sub-indexes BUILT ON DISK and none of them
registered in the answering process — built by another session, by the CLI, or before a registry
rewrite — so every bare call derived the whole-repository target, found no database there, and
refused with advice to run the one build that cannot finish on that repository: an unscoped
refresh that reached 87,911 files before doxygen was killed at 900 s.

THE DISK IS THE AUTHORITY FOR WHAT IS BUILT, and reading it costs a directory listing, not a tree
walk. A sub-index database lives at `targets/<whole slug>.<name>/clew.db` by `target_for`'s own
frozen allocation rule, so every sub-index of one repository is found by that prefix without
`derive_sub_indexes` — whose walk measured 24.6 s on the reporting repository and so has no place
on a query path.

ONE REFUSAL, SPELLED ONCE. Three copies of "no database has been built" had drifted: the routed
path named the target, the derived path did not, and `QueryTools` had a third wording. None knew
the repository was split, so none could say which sub-indexes existed or which build to run.

@brief Sub-index discovery, default preference and the unbuilt-index refusal.
@version 1
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..declaration import describe_declaration
from ..scope import FIRST_PARTY_INDEX
from .state import DB_NAME, Target, TargetRegistry, target_for

## At most this many sibling names ride in a refusal or a `not_searched` stamp. A repository that
## vendors boost splits into hundreds of parts; the refusal is read by a model deciding its next
## call, and a name it cannot find in a wall of them costs the round trip the list was meant to save.
MAX_LISTED_SIBLINGS = 12


## @brief Every index one repository has, as far as the registry and the disk can say.
## @version 1
@dataclass(frozen=True)
class RepoIndexes:
    """No tree walk went into this. It answers "what is BUILT or REGISTERED", never "how would this
    repository split" — that question needs `derive_sub_indexes` and belongs to a build.

    @brief The whole-repository target and every known sub-index of one repository.
    @version 1
    """

    repo_path: str
    whole: Target
    whole_registered: bool
    sub_indexes: tuple[Target, ...]
    ## Every sub-index name the last split derivation recorded (`TargetRegistry.note_derived`),
    ## built or not. Read from the registry, never derived here.
    derived: tuple[str, ...] = ()

    ## @brief The sub-indexes whose database exists right now.
    ## @return Built sub-index Targets, first-party first.
    ## @version 1
    ## @req REQ-DDB-MCP-001
    def built(self) -> tuple[Target, ...]:
        """@brief Built sub-indexes only. @version 1"""
        return tuple(t for t in self.sub_indexes if Path(t.db_path).is_file())

    ## @brief Whether the whole-repository database exists.
    ## @return True when it is built.
    ## @version 1
    ## @req REQ-DDB-MCP-001
    def whole_built(self) -> bool:
        """@brief Whole-repository index presence. @version 1"""
        return Path(self.whole.db_path).is_file()

    ## @brief Whether anything on record says this repository is split.
    ## @return True when a sub-index is registered or built, or the root declares submodules.
    ## @version 1
    ## @req REQ-DDB-MCP-001
    def split_evidence(self) -> bool:
        """`.gitmodules` COUNTS FOR ADVICE, NOT FOR ROUTING. A never-built repository has no
        sub-index on record, and B12 was exactly that before its first split build — so the
        refusal that recommends a build has to know, without walking, whether an unscoped one would
        descend into vendored trees. A root `.gitmodules` is the cheap, strong signal. It never
        changes which database answers: only a database on disk does that.

        @brief Split evidence from records, recorded derivations and the root `.gitmodules`.
        @return True when the repository is known or declared to be split.
        @version 1
        """
        return (
            bool(self.sub_indexes)
            or bool(self.derived)
            or (Path(self.repo_path) / ".gitmodules").is_file()
        )

    ## @brief The Target a call naming no sub_index answers from.
    ## @return The preferred Target, or None when nothing on record can be preferred.
    ## @version 1
    ## @req REQ-DDB-MCP-001
    def preferred(self) -> Target | None:
        """BUILT BEATS REGISTERED, then WHOLE BEATS FIRST-PARTY. The old rule preferred a
        REGISTERED whole-repository record whether or not it had a database — and following the
        refusal's own advice is what registers one: `index(action='refresh', target=repo)`
        registers the whole target before building it, so a build killed at 900 s left a record
        that outranked a perfectly good first-party index for every later call.

        @brief Choose the default index for a bare call.
        @return Whole if built, else first-party if built, else whichever is registered, else None.
        @version 1
        """
        first_party = next((t for t in self.sub_indexes if t.name == FIRST_PARTY_INDEX), None)
        ranked = (
            (self.whole_built(), self.whole),
            (first_party is not None and Path(first_party.db_path).is_file(), first_party),
            (self.whole_registered, self.whole),
            (first_party is not None, first_party),
        )
        return next((target for eligible, target in ranked if eligible), None)

    ## @brief Names of the other parts of this repository a reply from `answering` did not read.
    ## @param answering The index that answered.
    ## @return Built siblings first, then known-but-unbuilt ones; empty for a whole-repository answer.
    ## @version 1
    ## @req REQ-DDB-MCP-001
    def not_searched(self, answering: Target) -> tuple[str, ...]:
        """A WHOLE-REPOSITORY ANSWER SEARCHED EVERYTHING, so it lists nothing even when sub-indexes
        also exist beside it. Only a sub-index answer is partial.

        UNBUILT PARTS COUNT. Measured end to end: a background first build of a split repository
        builds first-party only, so no vendored part is built — and a miss for a vendored function
        was worded "a definitive negative" because nothing was listed. The vendored tree is known
        (the build recorded its derived name); that it has no index yet makes the answer MORE
        partial, not less. Built names come first because those are queryable now.

        @brief Other parts left unread by a sub-index answer.
        @return Names in listing order.
        @version 1
        """
        if answering.name is None:
            return ()
        built = [str(t.name) for t in self.built() if t.name is not None]
        known = [str(t.name) for t in self.sub_indexes if t.name is not None] + list(self.derived)
        ordered = built + sorted(set(known) - set(built))
        return tuple(dict.fromkeys(n for n in ordered if n != answering.name))


## @brief Collect every known index of one repository without walking its tree.
## @param registry The target registry, whose home is also where databases live.
## @param repo_path The repository root, already resolved.
## @return The repository's indexes.
## @version 1
## @req REQ-DDB-MCP-001
def repo_indexes(registry: TargetRegistry, repo_path: str) -> RepoIndexes:
    """REGISTERED NAMES WIN OVER DIRECTORY SUFFIXES. `_safe_index_name` truncates at 48
    characters, so a deep vendored name's directory is not always its spelling — and the record a
    build wrote holds the name it was given. A database with no record is named by its suffix,
    which `target_for` maps back to the same directory, so it is still addressable.

    @brief Registered and on-disk indexes of one repository.
    @return The collected RepoIndexes.
    @version 1
    """
    whole = target_for(repo_path, registry.home)
    records = [t for t in registry.targets() if t.repo_path == whole.repo_path]
    by_slug = {t.slug: t for t in records if t.name is not None}
    prefix = f"{whole.slug}."
    targets_dir = registry.home / "targets"
    if targets_dir.is_dir():
        for child in sorted(targets_dir.iterdir()):
            if child.name.startswith(prefix) and child.name not in by_slug:
                if (child / DB_NAME).is_file():
                    by_slug[child.name] = target_for(
                        whole.repo_path, registry.home, child.name[len(prefix) :]
                    )
    ordered = sorted(by_slug.values(), key=lambda t: (t.name != FIRST_PARTY_INDEX, str(t.name)))
    return RepoIndexes(
        repo_path=whole.repo_path,
        whole=whole,
        whole_registered=any(t.name is None for t in records),
        sub_indexes=tuple(ordered),
        derived=registry.derived_names(whole.repo_path),
    )


## @brief Render a bounded list of sub-index names for a sentence.
## @param names The names to list.
## @return Quoted, comma-joined names with any overflow counted.
## @version 1
## @dg_internal
def listed_names(names: tuple[str, ...] | list[str]) -> str:
    """@brief Bounded name list. @return The rendered list. @version 1"""
    shown = ", ".join(repr(n) for n in names[:MAX_LISTED_SIBLINGS])
    extra = len(names) - MAX_LISTED_SIBLINGS
    return shown + (f" (+{extra} more — index(action='targets') lists them)" if extra > 0 else "")


## @brief The sentence every unbuilt-index refusal opens with.
## @param what The index that is missing, named for a reader.
## @param remedy The exact call that builds it.
## @return The sentence.
## @version 1
## @req REQ-DDB-MCP-003
def no_index_message(what: str, remedy: str) -> str:
    """ONE WORDING FOR EVERY SHAPE THAT CAN REFUSE. There were three; gh#48 folded the two server
    paths into `unbuilt_refusal`, and this is the third — `QueryTools` bound to a single database,
    which has no registry to ask about sub-indexes and so cannot use the full refusal. It can
    still say the same sentence.

    @brief The shared "no index yet" sentence.
    @return The sentence.
    @version 1
    """
    return (
        f"No index has been built for {what} yet — call {remedy} first. Nothing is wrong with "
        f"this repository; it has simply not been indexed."
    )


## @brief The one message for a query whose index does not exist.
## @param indexes What the repository has.
## @param asked The Target the call resolved to, whose database is absent.
## @param background A sentence describing a background build of it, or "" when none runs.
## @return The refusal, naming what is built and the one build that fixes it.
## @version 2
## @req REQ-DDB-MCP-001
def unbuilt_refusal(indexes: RepoIndexes, asked: Target, background: str = "") -> str:
    """WRITTEN FOR A MODEL CHOOSING ITS NEXT CALL, because gh#48 recorded what the old wording
    produced in real sessions: retry the same call, run the suggested build, stall, or report the
    tool as broken. So it says, in order: what is missing, what IS queryable now with the exact
    argument, the single build that fixes it, and — on a split repository — the build NOT to run.

    `index(action='refresh', target=...)` WITHOUT `sub_index` IS NEVER ADVISED ON A SPLIT
    REPOSITORY. That is the 87,911-file build. First-party is the index a bare call defaults to, so
    it is the build that makes the refused call work.

    @brief Compose the unbuilt-index refusal.
    @return The message.
    @version 2
    """
    repo = indexes.repo_path
    built = [str(t.name) for t in indexes.built()]
    split = indexes.split_evidence()
    if asked.name is not None:
        what = f"sub-index {asked.name!r} of {repo}"
    elif split:
        what = f"{repo} (neither its first-party nor a whole-repository index)"
    else:
        what = repo
    wanted = asked.name if asked.name is not None else (FIRST_PARTY_INDEX if split else None)
    remedy = f"index(action='refresh', target={repo!r}" + (
        f", sub_index={wanted!r})" if wanted is not None else ")"
    )
    parts = [
        f"{background} Nothing is wrong with this repository; ask again once it finishes, or call "
        f"{remedy}, which waits for that same build rather than starting another."
        if background
        else no_index_message(what, remedy)
    ]
    if built:
        parts.append(f"Queryable now with the same target: sub_index= {listed_names(built)}.")
    unbuilt = [str(t.name) for t in indexes.sub_indexes if t.name not in built]
    if unbuilt:
        parts.append(f"Known but not built yet: {listed_names(unbuilt)}.")
    if split:
        parts.append(
            "This repository is split into sub-indexes (it vendors nested git trees): do NOT "
            "refresh it without sub_index, which indexes every vendored tree and can run past "
            "doxygen's time limit."
        )
    declaration = describe_declaration(Path(repo))
    if declaration:
        parts.append(declaration)
    return " ".join(parts)
