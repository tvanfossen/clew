## Answer

A "reaction added" event takes a short path: parse, sanitize, prepare, batch-write. A "reaction removed" event does not use that path at all. It queries the one matching row and destroys it directly. The only flag on the add path, `skipSync: true`, suppresses deletions, and the add path never reads `prepareRecordsOnly` as true.

### Add path

```
WS "reaction_added"
  └─ handleWebSocketEvent            app/actions/websocket/event.ts:163
       └─ handleReactionAddedToPostEvent   app/actions/websocket/reactions.ts:21
            ├─ DatabaseManager.getServerDatabaseAndOperator(serverUrl)
            ├─ JSON.parse(msg.data.reaction)           → Reaction
            └─ operator.handleReactions({
                 prepareRecordsOnly: false,
                 skipSync: true,
                 postsReactions: [{post_id, reactions:[reaction]}] })
                 └─ ServerDataOperatorBase.handleReactions   handlers/index.ts:124
                      ├─ sanitizeReactions({database, post_id, rawReactions, skipSync})
                      │    utils/reaction.ts:22
                      │    • load all local REACTION rows for post_id
                      │    • for each raw: if (userId-emojiName) exists → skip; else → createReactions
                      │    • if skipSync → return {createReactions, deleteReactions: []}
                      ├─ prepareRecords({createRaws, transformer: transformReactionRecord, tableName: REACTION})
                      │    transformers/reaction.ts:19 → prepareBaseRecord (CREATE)
                      │    sets _raw.id = server id, userId, postId, emojiName, createAt
                      ├─ deleteReactions skipped (guard: `deleteReactions?.length && !skipSync`)
                      └─ prepareRecordsOnly false → batchRecords(batchRecords, 'handleReactions')
                           base_data_operator/index.ts:191
                           database.write(writer => writer.batch(...))  → SQLite row inserted
```

Errors: `handleReactionAddedToPostEvent` wraps everything in `try { } catch { // Do nothing }`. `batchRecords` catches its own write errors, logs a warning, and emits `DATABASE_CORRUPTION_DETECTED` for corruption errors. It only rethrows if `propagateError` is set, and this call does not set it.

### Removed path

```
WS "reaction_removed"
  └─ handleWebSocketEvent            event.ts:166
       └─ handleReactionRemovedFromPostEvent   reactions.ts:39
            ├─ DatabaseManager.getServerDatabaseAndOperator(serverUrl)  → database only
            ├─ JSON.parse(msg.data.reaction)
            ├─ queryReaction(database, emoji_name, post_id, user_id).fetch()   queries/servers/reaction.ts:12
            └─ if found: database.write(() => reaction[0].destroyPermanently())
```

Differences from the add path:

- It does **not** call `handleReactions` or `sanitizeReactions`. No operator and no transformer are involved.
- It matches on `(emoji_name, post_id, user_id)` from the payload, not on the record id.
- It issues one `destroyPermanently()` inside its own `database.write`. Errors are swallowed by the same empty `catch`.
- If no row matches, nothing is written. A removal for a reaction the client never stored is a silent no-op.

### Flags that change what gets written

| Flag | Where | Effect |
|---|---|---|
| `skipSync: true` | add path (hardcoded) | `sanitizeReactions` returns early with `deleteReactions: []`, so the add event never deletes stale reactions for that post. Only the create set is computed. |
| `skipSync` (false) | full post sync via `handlePosts` | `sanitizeReactions` also computes local rows missing from the server payload as `deleteReactions`, and `handleReactions` calls `prepareDestroyPermanently()` on them. This is the only place reactions are deleted by diff. |
| `prepareRecordsOnly` | `handleReactions` | `false` here, so the records are written inside `handleReactions`. `true` would return the prepared records to the caller for a batch they control. The add event does not use it. |
| `exists` check in `sanitizeReactions` | always | A duplicate add for an existing `(user, emoji)` pair is skipped. No update is written. |

### Does removal take the same path?

No. The two events share only the outer `handleWebSocketEvent` switch. Removal bypasses the operator, the sanitize diff, and the batch writer. Its only write is a direct `destroyPermanently`.

### Observations

- Both websocket handlers swallow errors with an empty `catch`. That hides failures, and it conflicts with the project rule to log errors with context. A malformed payload or a DB error leaves no trace.
- I did not verify the model column mapping (`user_id` in the query versus `userId` on the model). I assumed it is a standard WatermelonDB field mapping.