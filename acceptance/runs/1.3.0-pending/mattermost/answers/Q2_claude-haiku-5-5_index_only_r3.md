## Short answer

A `reaction added` event is stored by `handleReactionAddedToPostEvent` → `operator.handleReactions` → `sanitizeReactions` → `prepareRecords` → `transformReactionRecord` → `batchRecords`. A `reaction removed` event does **not** take that path. `handleReactionRemovedFromPostEvent` looks up the row and calls `destroyPermanently()` directly, with no operator, no sanitize step, and no `skipSync`/`prepareRecordsOnly` flags. Both handlers swallow every error.

## Add path

```
WebSocket frame (event = REACTION_ADDED)
  │
  ▼
handleWebSocketEvent            app/actions/websocket/event.ts:44
  │  switch(msg.event) → case REACTION_ADDED
  ▼
handleReactionAddedToPostEvent  app/actions/websocket/reactions.ts:21
  │  DatabaseManager.getServerDatabaseAndOperator(serverUrl)
  │  reaction = JSON.parse(msg.data.reaction)
  │  operator.handleReactions({
  │     prepareRecordsOnly: false,   ← write, don't just return records
  │     skipSync: true,              ← don't compute deletions
  │     postsReactions: [{post_id, reactions:[reaction]}] })
  ▼
handleReactions                 app/database/operator/server_data_operator/handlers/index.ts:124
  │  for each post → sanitizeReactions({database, post_id, rawReactions, skipSync})
  ▼
sanitizeReactions               app/database/operator/utils/reaction.ts:22
  │  load all Reaction rows for post_id
  │  map by "userId-emojiName"
  │  raw in map  → treated as existing (no-op)
  │  raw not in map → createReactions.push({raw})
  │  skipSync → return {createReactions, deleteReactions: []}   (early return)
  ▼
handleReactions (cont.)
  │  createReactions non-empty →
  │     prepareRecords({createRaws, transformer: transformReactionRecord, tableName: REACTION})
  │        └─ transformReactionRecord (reactions.ts transformer:19)
  │             action=CREATE → database.collections.get(REACTION).prepareCreate(fieldsMapper)
  │             id = raw.id (server id); userId, postId, emojiName, createAt from raw
  │  deleteReactions skipped (skipSync)
  │  prepareRecordsOnly false → batchRecords(batchRecords, 'handleReactions')
  ▼
batchRecords                    app/database/operator/base_data_operator/index.ts:191
     database.write(writer => writer.batch(...models))  → SQLite row written
```

Notes on the add path:

- **`skipSync: true`** only affects deletions. `sanitizeReactions` returns early before computing `deleteReactions`, so a single-event add cannot remove other reactions on the post. `handleReactions` also checks `!skipSync` before pushing deletes, which is redundant because the list is already empty.
- **`prepareRecordsOnly: false`** means the records are batched and written inside the handler. With `true`, the caller would get the prepared models back and would have to write them.
- **Idempotency:** if a matching `userId-emojiName` row already exists for the post (for example, from the local user's own optimistic or REST add), the event is a no-op. The existing row is not updated.

## Remove path

```
WebSocket frame (event = REACTION_REMOVED)
  │
  ▼
handleWebSocketEvent → case REACTION_REMOVED
  ▼
handleReactionRemovedFromPostEvent   app/actions/websocket/reactions.ts:39
  │  {database} = getServerDatabaseAndOperator(serverUrl)   ← raw database, not operator
  │  msgReaction = JSON.parse(msg.data.reaction)
  │  reaction = queryReaction(database, emoji_name, post_id, user_id).fetch()
  │     └─ app/queries/servers/reaction.ts:12  WHERE emoji_name, post_id, user_id
  │  if reaction.length:
  │     database.write(() => reaction[0].destroyPermanently())
  ▼
  row hard-deleted (no sanitize, no batchRecords, no transformer)
```

Differences from the add path:

| | Added | Removed |
|---|---|---|
| Entry | `operator.handleReactions` | `database.write` directly |
| Lookup | sanitize map on the whole post | query on emoji + post + user |
| Flags | `prepareRecordsOnly:false`, `skipSync:true` | none |
| Write | `batchRecords` via transformer | `destroyPermanently()` |
| Missing row | Creates it | Silent no-op |

So the removed event does not reach `sanitizeReactions`, `transformReactionRecord`, or the `skipSync` logic at all. The only shared pieces are the entry point (`handleWebSocketEvent`) and the `queryReaction`/database layer.

## Things to flag

- **Silent failure in both handlers.** Each wraps its body in `try { … } catch { // Do nothing }`. A parse error, a DB error, or a missing server database is dropped with no log. That violates the project rule to log errors with context before handling them.
- **Removal is not symmetric.** The remove path ignores `msg.data` beyond the reaction fields and never checks the result of `destroyPermanently`. It also never touches the `skipSync` logic, which only exists on the add path.
- **I inferred `operator` from `getServerDatabaseAndOperator`.** The index does not show that function's body, so I did not confirm that the operator's `database` is the same object the sanitize step reads from.