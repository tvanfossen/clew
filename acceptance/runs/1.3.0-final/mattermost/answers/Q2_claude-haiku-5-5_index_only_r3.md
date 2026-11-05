## Short answer

Both events enter through the same `switch` in `handleWebSocketEvent`, but they diverge immediately after. The added path goes through the operator's `handleReactions` batch-write machinery with `skipSync: true`. The removed path skips the operator entirely: it queries the one matching row and calls `destroyPermanently()` inside `database.write`. Neither path reads or writes a flag that changes what the removed path writes, because the removed path has no flags.

## Added path

```
WS frame (event = REACTION_ADDED)
 └─ handleWebSocketEvent(serverUrl, msg)          app/actions/websocket/event.ts:44
     └─ case REACTION_ADDED
         └─ handleReactionAddedToPostEvent        app/actions/websocket/reactions.ts:21
             ├─ DatabaseManager.getServerDatabaseAndOperator(serverUrl)
             ├─ reaction = JSON.parse(msg.data.reaction)
             └─ operator.handleReactions({
                  prepareRecordsOnly: false,
                  skipSync: true,
                  postsReactions: [{post_id, reactions:[reaction]}] })
                 └─ ServerDataOperatorBase.handleReactions   handlers/index.ts:124
                     ├─ sanitizeReactions({database, post_id, rawReactions, skipSync})
                     │    utils/reaction.ts:22
                     │    - loads all Reaction rows for post_id
                     │    - map key "user_id-emoji_name"
                     │    - raw not present  → createReactions.push({raw})
                     │    - skipSync → return {createReactions, deleteReactions: []}
                     ├─ prepareRecords({createRaws, transformer: transformReactionRecord,
                     │                  tableName: REACTION})   base_data_operator:134
                     │    - transformer with action CREATE (transformers/reaction.ts:19)
                     │      _raw.id = raw.id from server
                     │      userId, postId, emojiName, createAt set
                     │      via prepareBaseRecord
                     ├─ deleteReactions branch skipped (!skipSync is false)
                     ├─ prepareRecordsOnly false → continue
                     └─ batchRecords(batch, 'handleReactions')   base_data_operator:191
                         └─ database.write(writer => writer.batch(...))  → SQLite row inserted
```

What lands in the database: one new `Reaction` row (server `id`, `user_id`, `post_id`, `emoji_name`, `create_at`). If the same user already has that emoji on the post locally, `sanitizeReactions` drops it and nothing is written.

## Removed path

```
WS frame (event = REACTION_REMOVED)
 └─ handleWebSocketEvent  (same switch, case REACTION_REMOVED)
     └─ handleReactionRemovedFromPostEvent          reactions.ts:39
         ├─ database = getServerDatabaseAndOperator(serverUrl).database
         ├─ msgReaction = JSON.parse(msg.data.reaction)
         ├─ queryReaction(database, emoji_name, post_id, user_id).fetch()
         │    queries/servers/reaction.ts:12   (matches on the three fields, not id)
         └─ if found: database.write(() => reaction[0].destroyPermanently())
```

It does not call `handleReactions`, `sanitizeReactions`, `prepareRecords`, or the transformer. There is no `skipSync` or `prepareRecordsOnly` in this path, and no flag can change what it writes. It deletes at most one row, the first match.

## Flags and what they change

| Flag | Where | Effect |
|---|---|---|
| `skipSync: true` (added path) | `sanitizeReactions` | Returns early, before computing `deleteReactions`. Only creates are produced. |
| `skipSync` | `handleReactions` | Guards the `deleteReactions` branch, so no stale rows are destroyed. |
| `prepareRecordsOnly: false` | `handleReactions` | Writes immediately through `batchRecords`. With `true`, it would return the prepared models without writing, so the caller could batch them into a larger transaction. |

The consequence of `skipSync: true` is that a websocket add is incremental. If the local DB holds a reaction the server has since removed, the add event will not clean it up. Only the removed event or a full sync fixes that.

## Observations

- **Silent failure in both handlers.** Both wrap the whole body in `try { … } catch { // Do nothing }`. A parse error or DB error is swallowed with no log. This conflicts with the repo's rule to log errors with context.
- **Wasted read in the add path.** `sanitizeReactions` queries every reaction on the post before the `skipSync` early return, so the skip saves the delete computation but not the query.
- **Two different database handles.** The add path uses the operator's `this.database`, and the removed path uses the `database` handle directly. Both end up in `database.write`, so the write mechanics are the same.

## Gaps in this answer

- I did not trace the socket-level dispatch above `handleWebSocketEvent`. The index links that function's caller only to `WebsocketManagerSingleton.createClient`, which probably wires an `onMessage` closure. I did not confirm that wiring.
- I did not inspect `prepareBaseRecord`, which sets the record's id and `_changed` / `_status` bookkeeping. The claim that it creates a new record rests on the `CREATE` action passed in.