## Short answer

A `reaction_added` event is parsed and written by the websocket handler through the server data operator. It is a create-only write: no deletions, no duplicate rows. A `reaction_removed` event does **not** take the same path. It skips the operator entirely and destroys the matching row directly. The two flags that matter (`skipSync`, `prepareRecordsOnly`) apply only to the add path.

## Add path

```
websocket msg (event = 'reaction_added')
  │
  ▼
handleWebSocketEvent            app/actions/websocket/event.ts:44
  switch(msg.event) case REACTION_ADDED
  │
  ▼
handleReactionAddedToPostEvent  app/actions/websocket/reactions.ts:21
  1. DatabaseManager.getServerDatabaseAndOperator(serverUrl)
  2. reaction = JSON.parse(msg.data.reaction)
  3. operator.handleReactions({
       prepareRecordsOnly: false,
       skipSync: true,
       postsReactions: [{post_id, reactions: [reaction]}] })
  │  (any exception is swallowed by an empty catch)
  ▼
handleReactions                 .../server_data_operator/handlers/index.ts:124
  sanitizeReactions({database, post_id, rawReactions, skipSync})
  │
  ▼
sanitizeReactions               app/database/operator/utils/reaction.ts:22
  - loads all Reaction rows for post_id
  - builds map keyed "userId-emojiName"
  - for each raw reaction: if key exists → skip, else → createReactions
  - if skipSync → return {createReactions, deleteReactions: []}   (early return)
  │
  ▼
handleReactions (cont.)
  - createReactions → prepareRecords(transformReactionRecord, tableName REACTION)
  - deleteReactions branch guarded by `&& !skipSync` (never runs on this path)
  - prepareRecordsOnly is false → batchRecords(...)
  │
  ▼
batchRecords                    base_data_operator/index.ts:191
  database.write(writer => writer.batch(...models))   ← the actual DB write
```

`transformReactionRecord` (`server_data_operator/transformers/reaction.ts:19`) sets `_raw.id` from the server's `raw.id` on create, plus `userId`, `postId`, `emojiName` and `createAt`.

## Remove path

```
handleWebSocketEvent case REACTION_REMOVED
  │
  ▼
handleReactionRemovedFromPostEvent   app/actions/websocket/reactions.ts:39
  1. database = getServerDatabaseAndOperator(serverUrl).database
  2. msgReaction = JSON.parse(msg.data.reaction)
  3. queryReaction(database, emoji_name, post_id, user_id).fetch()
  4. if found: database.write(() => reaction[0].destroyPermanently())
  (empty catch)
```

It does not use `handleReactions`, `sanitizeReactions`, the transformer or `batchRecords`. So `skipSync` and `prepareRecordsOnly` have no effect on it. It is a targeted, immediate delete of one row, matched on `(emoji_name, post_id, user_id)`.

## Flags and what they change

| Flag | Where | Effect |
|---|---|---|
| `skipSync: true` | add path | `sanitizeReactions` returns before computing `deleteReactions`. The `!skipSync` guard in `handleReactions` also blocks the delete branch. Without this, the single-reaction payload would look like a full snapshot and delete every other reaction on the post. |
| `prepareRecordsOnly: false` | add path | `handleReactions` runs `batchRecords` and writes. With `true` it would return prepared models and write nothing. |
| `skipSync` / `prepareRecordsOnly` | remove path | Not used. The remove handler has its own direct query and delete. |

The duplicate check in `sanitizeReactions` means a reaction already stored for the same user and emoji on that post is not re-created. Only creates are ever produced on the add path.

## Observations

- Both websocket handlers swallow every exception with an empty `catch`. A failed write is silent, which conflicts with the repo's CLAUDE.md logging rules.
- The `sanitizeReactions` doc comment says it also decides which custom emoji to create. The body does not do that. Custom emoji are handled by the separate `EMOJI_ADDED` → `handleAddCustomEmoji` path.
- I did not check which flags the bulk post-sync caller (`PostHandler.handlePosts`) passes into `handleReactions`, so I can't say how that path compares. I also did not read `prepareBaseRecord`, the `DatabaseManager` lookup or the websocket dispatch above `handleWebSocketEvent`. All of this comes from the index.