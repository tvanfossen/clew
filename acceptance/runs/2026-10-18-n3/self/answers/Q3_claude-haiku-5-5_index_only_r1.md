The index detects its own staleness on two independent signals, reports it inside every query reply, and the caller's remedy depends on which signal fired.

**How it knows.** `db_status` (`clew/mcp_server/state.py:1140`) marks a database stale when any of these hold:
- the database file does not exist;
- the pipeline version that stamped it (`build_version`) differs from the running `CLEW_BUILD_VERSION`;
- source files have changed since the build (`source_changed_files > 0`), so editing a file makes the index stale even when the version matches.

It also reports `age_days` and `newest_changed_source`. The `staleness` key is present only when something is stale, so its presence is itself the signal.

**What it tells the caller.** Staleness is split into axes, and `stale` is interpreted rather than left as a bare boolean. Three different causes clear in three different ways:
- an older pipeline stamp is cleared by a rebuild;
- an index stamped with a newer version than the server expects (`expected_build_version` below `build_version`) cannot be cleared by a rebuild, because the rebuild re-stamps the same newer version, so the client must be restarted;
- anything else the consumer cannot change.

`status` also reports `coverage`, which is separate from staleness: an index can be current yet have parsed almost nothing. Each of these is reported separately.

**How it reaches the caller without `status`.** `staleness_notices` (`server.py:1548`) runs on the way out of every query reply and returns `{axis, message}` entries. The design choice is that the warning rides in the payload, because a consumer holding a plausible-looking answer would not think to call `status`. The measurement never raises: any failure just means no annotation. Notices are sized against the real payload, in three tiers: full prose, then a compact form, then a minimal "stale — call status". A large reply therefore still carries the warning, shortened rather than dropped. A routed reply is annotated only with the staleness of the repository it actually read, never the derived one's, so the caller is not warned about a database that was never opened.

**What the caller does.**
1. Read the `staleness` block on the reply. The compact text says to call `status` for the full diagnosis and the remedy.
2. Call `status`. It gives `stale`, the version numbers, the `refresh` cost measured on this target, and `target_source`, which shows why this repository was chosen.
3. Act on the cause:
   - rebuild with `index(action='refresh')`, using `force` if needed;
   - restart the client, for the newer-version case;
   - for old version-stamped databases, `index(action='cull')` removes them.
4. Re-query. A current index adds no `staleness` key at all.

Caveats: I read the body of `staleness_notices` and `db_status` but not `notices()` or `build_or_refresh`, so the exact wording of each axis message and the refresh internals are unverified. The index also flagged the line anchors of `_staleness` and `_staleness_within_budget` as mismatched with the current file, so their reported line numbers may be off.