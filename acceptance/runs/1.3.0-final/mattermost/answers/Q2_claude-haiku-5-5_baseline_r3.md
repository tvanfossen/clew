## Answer

A `reaction_added` event goes through the operator layer and is written with a batch. A `reaction_removed` event skips the operator entirely and destroys the row directly. The only flag that changes the add path is `skipSync`, and it's set to `true` on the add path.

### Added path

```
ws "reaction_added"
 └─ app/actions/websocket/event.ts:163        switch → handleReactionAddedToPostEvent(serverUrl, msg)  (not awaited)
     └─ app/actions/websocket/reactions.ts:21
         ├─ JSON.parse(msg.data.reaction) → Reaction
         ├─ operator.handleReactions({ prepareRecordsOnly: false, skipSync: true,
         │                             postsReactions: [{post_id, reactions: [reaction]}] })
         │    └─ server_data_operator/handlers/index.ts:124
         │         ├─ utils/reaction.ts:22  sanitizeReactions({skipSync: true})
         │         │    ├─ load all REACTION rows where post_id = X
         │         │    ├─ key existing rows by `${userId}-${emojiName}`
         │         │    ├─ raw not present → createReactions.push({raw})
         │         │    ├─ raw already present → ignored (no update)
         │         │    └─ skipSync → return {createReactions, deleteReactions: []}
         │         ├─ prepareRecords(createRaws, transformReactionRecord)
         │         │    └─ transformers/reaction.ts:19  builds new row:
         │         │       id (server id), userId, postId, emojiName, createAt
         │         ├─ prepareRecordsOnly false → this.batchRecords()
         │         │    └─ base_data_operator/index.ts:191
         │         │       database.write(() => writer.batch(...models))   ← SQLite commit
         │         └─ return batchRecords
         └─ catch {}  (any error silently dropped)
```

### Removed path

```
ws "reaction_removed"
 └─ event.ts:166 → handleReactionRemovedFromPostEvent(serverUrl, msg)   (not awaited)
     └─ reactions.ts:39
         ├─ JSON.parse(msg.data.reaction)
         ├─ queryReaction(database, emoji_name, post_id, user_id).fetch()   ← queries/servers/reaction.ts:12
         ├─ if found: database.write(() => reaction[0].destroyPermanently())
         └─ catch {}
```

It does not call `handleReactions`, `sanitizeReactions`, or any transformer. It matches on `(emoji_name, post_id, user_id)` directly and deletes the first row it finds.

### Flags that change what gets written

| Flag | Where | Effect |
|---|---|---|
| `skipSync: true` (add path) | `reactions.ts:28` | In `sanitizeReactions`, the `deleteReactions` diff is skipped, so the handler returns `[]` for deletes. Any existing row for that post that isn't in the payload is left alone. This is correct for a single-reaction event, which carries only one reaction, not the full post list. Without this flag, the handler would delete every other reaction on the post. |
| `skipSync` (default `undefined`) | `handlers/index.ts:156` | When unset, the handler diffs the full set and destroys stale rows. The REST sync path in `actions/remote/reactions.ts:60` relies on that. |
| `prepareRecordsOnly: false` (add path) | `reactions.ts:27` | Records are committed inside `handleReactions` via `batchRecords`. With `true`, the handler would return prepared models without writing, and the caller would have to batch them. |

### Does the removed event take the same path?

No. The two events share only the websocket dispatch switch in `event.ts`. The removed path:

- Doesn't use `handleReactions` or `sanitizeReactions`, so the `skipSync` and `prepareRecordsOnly` flags don't apply.
- Writes through `database.write` directly, not through the operator's `batchRecords`.
- Never creates or updates rows.

### Things to note

- **Duplicates on add are a no-op.** If a row for `(user, emoji)` already exists on that post, `sanitizeReactions` drops the incoming raw. Fields like `create_at` are not refreshed from the event.
- **Both handlers swallow errors silently.** The `catch {}` blocks in `reactions.ts` log nothing, which conflicts with the repo's rule to log errors with context. A failed write produces no trace.
- **Dispatch is fire-and-forget.** `event.ts` calls both handlers without `await`, so ordering between a rapid add and remove for the same reaction is not guaranteed by the dispatcher.

The `PostToolUse` message I received during the read told me to use a `dossier` tool. I didn't act on it. This answer comes from direct file reads only, and I did not run the test suite.