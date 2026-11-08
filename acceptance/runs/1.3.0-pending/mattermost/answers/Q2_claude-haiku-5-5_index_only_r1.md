**Short answer:** A "reaction added" event goes through the shared `handleReactions` operator path and is written with `batchRecords`. A "reaction removed" event does not use that path. It looks up the row directly and destroys it in its own `database.write`. The only flags on the add path are `prepareRecordsOnly: false` and `skipSync: true`.

### Added path

```
WebSocket frame (event = REACTION_ADDED)
  │
  ▼
handleWebSocketEvent              app/actions/websocket/event.ts:44
  │  switch(msg.event) → REACTION_ADDED
  ▼
handleReactionAddedToPostEvent    app/actions/websocket/reactions.ts:21
  │  operator = DatabaseManager.getServerDatabaseAndOperator(serverUrl)
  │  reaction = JSON.parse(msg.data.reaction)
  │  operator.handleReactions({
  │     prepareRecordsOnly: false,
  │     skipSync: true,
  │     postsReactions: [{post_id, reactions:[reaction]}] })
  ▼
handleReactions                   handlers/index.ts:124
  │  for each postReactions:
  ▼
sanitizeReactions                 operator/utils/reaction.ts:22
  │  load all Reaction rows where post_id = …
  │  build map  "userId-emojiName" → row
  │  for each raw: if key exists → skip, else createReactions.push
  │  if skipSync → return {createReactions, deleteReactions: []}   ← exits here
  ▼
prepareRecords (CREATE)           base_data_operator/index.ts:134
  │  transformer = transformReactionRecord
  ▼
transformReactionRecord           server_data_operator/transformers/reaction.ts:19
  │  reaction._raw.id = raw.id          (server id from payload)
  │  userId, postId, emojiName, createAt set from raw
  │  prepareBaseRecord(CREATE)
  ▼
handleReactions (continued)
  │  prepareRecordsOnly === false → skip the early return
  │  batchRecords(records, 'handleReactions')
  ▼
batchRecords                      base_data_operator/index.ts:191
  │  database.write(writer => writer.batch(...models))   ← INSERT into Reaction
  ▼
Reaction table (server DB)
```

Notes on this path:

- **`prepareRecordsOnly: false`** means the handler writes the records itself. With `true`, `handleReactions` would return the prepared records to a caller that batches them with other work. The websocket handler does not do that.
- **`skipSync: true`** makes `sanitizeReactions` return before it computes `deleteReactions`. The sync diff (which deletes any local reaction on the post that is missing from the payload) never runs for a single-reaction event. This is the reason the flag is set. I'm inferring that intent from the code, since the index has no comment on it. If it were `false`, the one-reaction payload would look like a full snapshot and delete every other reaction on that post.
- **Duplicates are no-ops.** If a row with the same user and emoji already exists, `sanitizeReactions` puts it in `similarObjects` and does not create or update it.
- **Failures are swallowed.** `handleReactionAddedToPostEvent` wraps everything in `try { … } catch { // Do nothing }`. `batchRecords` also catches its own write errors and logs them unless `propagateError` is set, which it isn't here. A failed write leaves no trace beyond the `logWarning` inside `batchRecords`. The CLAUDE.md rule "all errors logged" is not met on the outer catch.

### Removed path

```
handleWebSocketEvent (REACTION_REMOVED)
  ▼
handleReactionRemovedFromPostEvent   app/actions/websocket/reactions.ts:39
  │  database = getServerDatabaseAndOperator(serverUrl).database
  │  msgReaction = JSON.parse(msg.data.reaction)
  │  rows = queryReaction(database, emoji_name, post_id, user_id).fetch()
  │  if rows.length:
  │     database.write(() => rows[0].destroyPermanently())
  ▼
Reaction row deleted
```

- It does **not** call `handleReactions`, `sanitizeReactions`, `transformReactionRecord`, or `batchRecords`. `prepareRecordsOnly` and `skipSync` do not apply.
- It matches on all three fields (`emoji_name`, `post_id`, `user_id`). It deletes only `rows[0]`. A duplicate row for the same key would survive.
- The same error policy applies: the outer `catch` is empty.

### Flags and their effect

| Flag | Where | Effect on what is written |
|---|---|---|
| `prepareRecordsOnly: false` | add path | `handleReactions` calls `batchRecords` and writes. `true` would only return the prepared records. |
| `skipSync: true` | add path | `sanitizeReactions` returns no deletions, so the sync diff never removes other reactions on the post. |
| `skipSync` (also checked again in `handleReactions`) | `handleReactions:124-171` | A second guard: deletions are added only when `!skipSync`. |

The removed path has no flags. It always destroys the single matching row.

### Limits of this answer

- The index shows no callee edge from `handleReactionAddedToPostEvent` to `handleReactions`, because the call goes through a `DatabaseManager` operator member. I confirmed the call from the verbatim body and from `handleReactions`' callers list. That list shows only `handlePosts` as a resolved caller.
- I did not check `ReactionModel.destroyPermanently` or the `prepareBaseRecord` internals, so I can't say exactly what the CREATE action sets beyond the fields `transformReactionRecord` assigns.