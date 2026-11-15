The "added" path writes the reaction through the shared operator with the server-sync delete logic turned off. The "removed" path skips that machinery entirely and destroys the row directly. The index supports this trace, but I did not read the `WebSocketMessage` parsing or the websocket manager, so the start of the chain is taken from the dispatcher's call sites.

**Added path**

```
WebSocket REACTION_ADDED
 └─ handleWebSocketEvent            app/actions/websocket/event.ts:44
     │  switch(msg.event) → REACTION_ADDED
 └─ handleReactionAddedToPostEvent  app/actions/websocket/reactions.ts:21
     │  operator = DatabaseManager.getServerDatabaseAndOperator(serverUrl)
     │  reaction = JSON.parse(msg.data.reaction)
     │  operator.handleReactions({prepareRecordsOnly: false,
     │                            skipSync: true,
     │                            postsReactions: [{post_id, reactions:[reaction]}]})
 └─ handleReactions                 server_data_operator/handlers/index.ts:124
     │  for each post: sanitizeReactions(...)
     │    └─ sanitizeReactions      operator/utils/reaction.ts:22
     │         loads existing REACTION rows for post_id
     │         key = userId-emojiName; if absent → createReactions
     │         skipSync=true → return {createReactions, deleteReactions: []}
     │  createReactions → prepareRecords({transformer: transformReactionRecord, tableName: REACTION})
     │    └─ transformReactionRecord  transformers/reaction.ts:19
     │         CREATE: _raw.id = raw.id; sets userId, postId, emojiName, createAt
     │  prepareRecordsOnly=false → batchRecords(...)
 └─ BaseDataOperator.batchRecords   base_data_operator/index.ts:191
        database.write(writer => writer.batch(...))   → SQLite row written
```

**Removed path**

```
WebSocket REACTION_REMOVED
 └─ handleWebSocketEvent            event.ts:44
 └─ handleReactionRemovedFromPostEvent  reactions.ts:39
        database = DatabaseManager.getServerDatabaseAndOperator(serverUrl).database
        msgReaction = JSON.parse(msg.data.reaction)
        queryReaction(database, emoji_name, post_id, user_id).fetch()   // queries/servers/reaction.ts:12
        if (reaction.length)
            database.write(() => reaction[0].destroyPermanently())
```

It does not take the operator path. It never calls `handleReactions`, `sanitizeReactions`, or `transformReactionRecord`, and it has no `prepareRecordsOnly`/`skipSync` flags.

**Flags that change what gets written**

- **`skipSync: true`** (added path only): `sanitizeReactions` returns right after the create list is built, so it never computes `deleteReactions`. A single-reaction event therefore cannot delete other reactions on the post. The same flag is what keeps the full-sync delete logic from running.
- **`prepareRecordsOnly: false`**: the records are written inside `batchRecords`. With `true`, `handleReactions` would only return prepared records without writing them. The `handlePosts` caller does not pass this flag, so its default `false` applies there too.
- **Existing rows are not updated.** If a row with the same user and emoji already exists, `sanitizeReactions` skips it, so there is no update branch for a duplicate add.
- **`skipSync` on removal does not apply.** The removal path never reads it. If it were routed through `handleReactions` without `skipSync`, a single-reaction removal would wrongly mark every other reaction on the post for deletion.
- **Redundant guard**: `handleReactions` checks `deleteReactions?.length && !skipSync`. Since `skipSync` already empties `deleteReactions`, that check does nothing extra.

**Error handling**

Both handlers wrap their work in `try { ... } catch { /* Do nothing */ }`, so failures are silent. `batchRecords` also swallows write errors by default (`propagateError = false`) after logging a warning, and it emits `DATABASE_CORRUPTION_DETECTED` for corruption errors.

**Differences between the two paths**

| | Added | Removed |
|---|---|---|
| Entry | `handleReactionAddedToPostEvent` | `handleReactionRemovedFromPostEvent` |
| Goes through operator | yes (`handleReactions`) | no (direct DB write) |
| Lookup | all REACTION rows for the post, keyed in memory | `queryReaction` on emoji, post and user |
| Write | `batchRecords` → `writer.batch` (create) | `database.write` → `destroyPermanently` on first match |
| Flags | `skipSync: true`, `prepareRecordsOnly: false` | none |
| Mutation | create only | hard delete only |