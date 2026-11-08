**Short answer:** Both events are dispatched from the same switch, but they take different paths after that. "Added" goes through the shared sync operator with `skipSync: true`, so it only creates rows. "Removed" bypasses the operator entirely and hard-deletes one row directly. Neither path logs its failures.

```
WS frame (event = reaction_added / reaction_removed)
  └─ handleWebSocketEvent  (app/actions/websocket/event.ts)
       switch(msg.event)
       ├─ REACTION_ADDED   → handleReactionAddedToPostEvent
       └─ REACTION_REMOVED → handleReactionRemovedFromPostEvent
```

### "Reaction added" path

1. **Dispatch.** `handleWebSocketEvent` routes `WebsocketEvents.REACTION_ADDED` to `handleReactionAddedToPostEvent` (`app/actions/websocket/reactions.ts:21`). The index does not show the caller chain above `handleWebSocketEvent`, but its only caller is `createClient` in `app/managers/websocket_manager.ts`.
2. **Parse.** It gets the server database and operator for `serverUrl`, then parses `msg.data.reaction` (a JSON string) into a `Reaction`.
3. **Call the operator.** It calls `operator.handleReactions({ prepareRecordsOnly: false, skipSync: true, postsReactions: [{ post_id, reactions: [reaction] }] })`.
4. **Diff against the DB.** `handleReactions` (`app/database/operator/server_data_operator/handlers/index.ts:124`) calls `sanitizeReactions` (`app/database/operator/utils/reaction.ts:22`). That function loads all Reaction rows for the post and builds a map keyed by `userId-emojiName`. A raw reaction already in the map is skipped; any other one goes into `createReactions`. Duplicate adds are therefore no-ops.
5. **Prepare.** For `createReactions`, `prepareRecords` calls `transformReactionRecord` with `CREATE`. That sets the id from the server's `raw.id`, plus `userId`, `postId`, `emojiName` and `createAt`, through `prepareBaseRecord`, which calls `prepareCreate`.
6. **Write.** Because `prepareRecordsOnly` is false, `batchRecords` runs `writer.batch(...)` inside `database.write`. Errors are caught and logged with `logWarning`, and a corruption error also emits `DATABASE_CORRUPTION_DETECTED`. The outer `handleReactionAddedToPostEvent` wraps everything in `try { … } catch { // Do nothing }`.

### "Reaction removed" path

1. **Dispatch.** `REACTION_REMOVED` goes to `handleReactionRemovedFromPostEvent` (`reactions.ts:39`).
2. **No operator.** It takes the raw `database` from `DatabaseManager`, not the operator, and parses `msg.data.reaction`.
3. **Lookup.** `queryReaction(database, emoji_name, post_id, user_id).fetch()` finds the row by the emoji, post and user triple.
4. **Hard delete.** If a row exists, it calls `reaction[0].destroyPermanently()` inside `database.write`. There is no diff, no `sanitizeReactions`, no `transformReactionRecord` and no `batchRecords`.
5. **Errors.** The whole body is wrapped in the same empty `catch`. If no row matches, nothing is written and nothing is logged.

### Does removal take the same path?

No. Only the dispatch switch is shared. The difference that matters is that removal never reaches `handleReactions`, so it never runs the sync logic that could delete other rows.

| | Reaction added | Reaction removed |
|---|---|---|
| Entry point | `handleReactionAddedToPostEvent` | `handleReactionRemovedFromPostEvent` |
| Goes through operator | Yes, `handleReactions` | No, raw `database` |
| Flags | `prepareRecordsOnly: false`, `skipSync: true` | None |
| Lookup | Full post reaction list, keyed by user+emoji | `queryReaction` by emoji+post+user |
| Write | `batchRecords` (batched create) | `destroyPermanently` in `database.write` |
| Error handling | Empty `catch` in the handler, plus `logWarning` in `batchRecords` | Empty `catch` only |

### Flags that change what gets written

- **`skipSync: true` (add path).** `sanitizeReactions` returns early with `deleteReactions: []` before computing deletions, and `handleReactions` also gates its delete branch on `!skipSync`. The payload holds only one reaction, so without this flag the sync would treat every other reaction on the post as stale and delete it. With the flag, the event can only create.
- **`prepareRecordsOnly: false` (add path).** The records are written immediately instead of being returned for a caller to batch. `batchRecords` is called without `propagateError`, so a write failure is logged and swallowed.
- **Removal has no flags.** Its hard delete (`destroyPermanently`) is not a soft delete, so the row is gone from the local DB.

### Problems I noticed

- Both handlers swallow every error in an empty `catch`, and the add path's `batchRecords` also drops write errors. That conflicts with the repo's CLAUDE.md rule to log errors with context. A failed reaction write leaves no trace.
- `handleReactions`'s JSDoc says it returns `ReactionModel | CustomEmojiModel`, and `sanitizeReactions`'s brief says it decides which custom emoji to create. Neither is implemented in the bodies I read. Custom emoji appears to be handled separately by `EMOJI_ADDED` → `handleAddCustomEmoji`.
- I could not check the `destroyPermanently` method on `ReactionModel` itself. The index does not list one for the reaction model, so I am assuming it is WatermelonDB's base `Model.destroyPermanently`.