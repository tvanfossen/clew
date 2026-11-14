**Short answer:** A "reaction added" event goes through the `handleReactions` operator with `skipSync: true`, which makes it a create-only write. A "reaction removed" event does not use the operator at all. It queries the one row and destroys it directly. The two paths share no write code.

## Reaction added

```
WS frame (event = REACTION_ADDED)
  └─ handleWebSocketEvent            app/actions/websocket/event.ts:44
       case REACTION_ADDED
  └─ handleReactionAddedToPostEvent  app/actions/websocket/reactions.ts:21
       • DatabaseManager.getServerDatabaseAndOperator(serverUrl)
       • Reaction = JSON.parse(msg.data.reaction)
       • operator.handleReactions({ prepareRecordsOnly: false,
                                    skipSync: true,
                                    postsReactions: [{post_id, reactions:[reaction]}] })
  └─ handleReactions                 server_data_operator/handlers/index.ts:124
       • sanitizeReactions({database, post_id, rawReactions, skipSync})
  └─ sanitizeReactions               database/operator/utils/reaction.ts:22
       • load all Reaction rows for post_id
       • key = `${userId}-${emojiName}`; if already present → skip
       • else push {raw} into createReactions
       • skipSync === true → return {createReactions, deleteReactions: []} (early return)
  └─ prepareRecords(transformReactionRecord, tableName REACTION)
       └─ transformReactionRecord  server_data_operator/transformers/reaction.ts:19
            • CREATE → database.collections.get(REACTION).prepareCreate(fieldsMapper)
            • fieldsMapper sets _raw.id (from server id), userId, postId, emojiName, createAt
  └─ prepareRecordsOnly is false → batchRecords(...)
       └─ BaseDataOperator.batchRecords   base_data_operator/index.ts:191
            • database.write(writer => writer.batch(...))
            • on error: logWarning, and emit DATABASE_CORRUPTION_DETECTED if applicable;
              does not rethrow (propagateError defaults to false)
```

### Flags on the add path

- **`skipSync: true`**: `sanitizeReactions` returns before computing `deleteReactions`, so the only output is `createReactions`. The `if (deleteReactions?.length && !skipSync)` guard in `handleReactions` is also not reached. This is the single-reaction, event-driven case, so it must not treat the rest of the post's reactions as stale.
- **`prepareRecordsOnly: false`**: the batch is actually written. With `true`, the handler would return prepared models and leave the write to the caller.
- **Duplicate protection** comes from the in-memory map in `sanitizeReactions`, not from a DB unique constraint. An existing `userId-emojiName` pair is not re-created.

## Reaction removed

```
WS frame (event = REACTION_REMOVED)
  └─ handleWebSocketEvent → handleReactionRemovedFromPostEvent   reactions.ts:39
       • database = DatabaseManager.getServerDatabaseAndOperator(serverUrl).database
       • msgReaction = JSON.parse(msg.data.reaction)
       • queryReaction(database, emoji_name, post_id, user_id).fetch()   queries/servers/reaction.ts:12
       • if found: database.write(() => reaction[0].destroyPermanently())
```

The removed path does **not** go through `handleReactions`, `sanitizeReactions`, or the transformers. It does not use `skipSync` or `prepareRecordsOnly`, and it does not use `batchRecords`. Those flags only exist on the operator path, so a removal event cannot change what gets written by setting them. The row is matched on `(emoji_name, post_id, user_id)` from the event payload, and the row is hard-deleted (`destroyPermanently`) inside its own write transaction.

## Differences to be aware of

| | Added | Removed |
|---|---|---|
| Entry | `operator.handleReactions` | `database` used directly |
| Flags | `skipSync: true`, `prepareRecordsOnly: false` | none |
| Write | `batchRecords` (create via `prepareCreate`) | `destroyPermanently` in `database.write` |
| Error handling | `batchRecords` logs and does not rethrow | own `try/catch` with `// Do nothing` |

Both handlers wrap the whole body in `try { … } catch { // Do nothing }`. A malformed payload, a failed write, or a missing DB silently drops the event with no log. The CLAUDE.md rule against swallowed errors is violated on both paths.

## Caveats

- This comes from the index alone. I did not read the code directly, so I'm trusting the indexed bodies. The `WebsocketEvents` constant values, which map `REACTION_ADDED` and `REACTION_REMOVED` to their event strings, were not checked.
- I did not trace what `prepareRecords` does internally beyond the transformer call, or how `ReactionModel.destroyPermanently` behaves.