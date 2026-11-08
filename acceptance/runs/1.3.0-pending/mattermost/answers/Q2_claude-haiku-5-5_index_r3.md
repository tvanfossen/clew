## Short answer

A "reaction added" event goes through the server data operator, and `skipSync: true` means it only creates missing rows. A "reaction removed" event does **not** take the same path. It skips the operator entirely, queries the row directly, and destroys it. Neither path reports errors: both wrap their work in an empty `catch`.

## Reaction added

```
WS frame (event = REACTION_ADDED)
  └─ handleWebSocketEvent            app/actions/websocket/event.ts        (switch dispatch)
      └─ handleReactionAddedToPostEvent   app/actions/websocket/reactions.ts:21-37
          ├─ DatabaseManager.getServerDatabaseAndOperator(serverUrl)
          ├─ JSON.parse(msg.data.reaction)              → Reaction
          └─ operator.handleReactions({
               prepareRecordsOnly: false,   // write now, don't return records
               skipSync: true,              // add only, no pruning
               postsReactions: [{post_id, reactions: [reaction]}] })
              └─ ServerDataOperatorBase.handleReactions   handlers/index.ts:124-171
                  ├─ sanitizeReactions({database, post_id, rawReactions, skipSync})
                  │     utils/reaction.ts:22-58
                  │     • loads ALL Reaction rows for post_id
                  │     • map key = `${userId}-${emojiName}`
                  │     • raw not in map → createReactions.push({raw})
                  │     • skipSync → return {createReactions, deleteReactions: []}
                  ├─ createReactions non-empty?
                  │     prepareRecords({createRaws, transformer: transformReactionRecord, tableName: REACTION})
                  │       └─ transformReactionRecord  transformers/reaction.ts:19-43
                  │            id = raw.id, userId, postId, emojiName, createAt
                  ├─ deleteReactions branch → skipped (empty, and also gated by !skipSync)
                  ├─ prepareRecordsOnly false → skip the early return
                  └─ batchRecords(batch, 'handleReactions')   base_data_operator/index.ts:191-211
                        database.write(writer => writer.batch(...))
                        on error: logWarning, emit DATABASE_CORRUPTION_DETECTED if corruption
```

**Result:** a new `Reaction` row is written. If the user already has that emoji on the post locally, `createReactions` is empty and nothing is written. The duplicate check is on user + emoji, not on the server ID.

## Reaction removed

```
WS frame (event = REACTION_REMOVED)
  └─ handleWebSocketEvent
      └─ handleReactionRemovedFromPostEvent   app/actions/websocket/reactions.ts:39-54
          ├─ DatabaseManager.getServerDatabaseAndOperator(serverUrl)  → database only
          ├─ JSON.parse(msg.data.reaction)
          ├─ queryReaction(database, emoji_name, post_id, user_id).fetch()   queries/servers/reaction.ts:12-18
          └─ if found: database.write(() => reaction[0].destroyPermanently())
```

It does not use `handleReactions`, `sanitizeReactions`, `batchRecords`, or the transformer. It also has no `skipSync` or `prepareRecordsOnly` flags, so there is no flag that changes what gets written. It deletes exactly one row, the one matching emoji, post and user. If no row matches, nothing happens.

## Flags that change behaviour

| Flag | Where | Effect |
|---|---|---|
| `skipSync: true` (add path) | `sanitizeReactions` | Returns `deleteReactions: []`. Stale reactions on the post are not pruned. This is the "incremental add" mode; a full post sync would pass `false`. |
| `skipSync` (in `handleReactions`) | second gate on the delete branch | Redundant for the add path, since `sanitizeReactions` already returns no deletes. It matters only for callers that pass `skipSync: false`. |
| `prepareRecordsOnly: false` (add path) | `handleReactions` | Writes the batch immediately and returns it. `true` would return the models to a caller that batches them into a larger transaction. |

## Things to note

- **Error handling is silent in both paths.** Each handler has an empty `catch`. The add path's `batchRecords` logs a warning and does not rethrow, because `propagateError` defaults to `false`. A failed write is therefore only visible in logs.
- **Not verified:** I did not read `DatabaseManager.getServerDatabaseAndOperator` or `prepareBaseRecord`. Both are assumed to behave as their names suggest.