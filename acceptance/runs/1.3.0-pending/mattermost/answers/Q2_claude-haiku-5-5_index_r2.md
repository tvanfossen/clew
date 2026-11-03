**Short answer:** Both events are dispatched from the same switch, but they don't share a write path. "Added" goes through the operator's `handleReactions` with `skipSync: true`. "Removed" bypasses the operator entirely and destroys the row directly. Neither path can silently drop a failure, since both wrap their work in a catch that does nothing.

```
WS frame (event = "reaction_added")
  │
  ▼
handleWebSocketEvent            app/actions/websocket/event.ts:163
  │  switch(msg.event) → REACTION_ADDED
  │  calls handleReactionAddedToPostEvent(serverUrl, msg)   (not awaited)
  ▼
handleReactionAddedToPostEvent   app/actions/websocket/reactions.ts:21
  │  DatabaseManager.getServerDatabaseAndOperator(serverUrl)
  │  reaction = JSON.parse(msg.data.reaction)
  │  operator.handleReactions({prepareRecordsOnly:false, skipSync:true,
  │                            postsReactions:[{post_id, reactions:[reaction]}]})
  ▼
ServerDataOperatorBase.handleReactions   handlers/index.ts:124
  │  for each post: sanitizeReactions(...)
  ▼
sanitizeReactions                        utils/reaction.ts:22
  │  load all Reaction rows where post_id = …
  │  build map keyed "userId-emojiName"
  │  for each raw: exists → skip; missing → createReactions.push({raw})
  │  skipSync → return {createReactions, deleteReactions: []}   ← early return
  ▼
handleReactions (cont.)
  │  createReactions → prepareRecords({transformer: transformReactionRecord})
  │     └─ transformReactionRecord: id = raw.id (CREATE), user_id, post_id,
  │        emoji_name, create_at; then prepareBaseRecord
  │  deleteReactions branch is guarded by `&& !skipSync` (never runs here)
  │  prepareRecordsOnly=false → this.batchRecords(batch, 'handleReactions')
  ▼
batchRecords                             base_data_operator/index.ts:191
  │  database.write(writer => writer.batch(...models))
  ▼
Reaction row INSERTED in the server DB
```

**Flags that change what is written on the add path**

- **`skipSync: true`** is the important one. Without it, `sanitizeReactions` would diff the *whole* post's reaction table against `rawReactions`. The payload only carries the one new reaction, so every other reaction on that post would be marked for deletion. `skipSync` short-circuits that diff, so the path is create-only.
- **Duplicate suppression is built in.** If a row for the same user and emoji already exists on that post, it's skipped. Replayed or duplicate `reaction_added` events are no-ops.
- **`prepareRecordsOnly: false`** means the batch is written immediately. With `true`, the records would be returned and the caller would have to commit them.
- The custom-emoji side is not touched on this path. `handleReactions` only writes `REACTION` rows.

**Removal path** (`handleReactionRemovedFromPostEvent`, `reactions.ts:39`)

```
WS frame (event = "reaction_removed")
  → handleWebSocketEvent (event.ts:166)
  → handleReactionRemovedFromPostEvent
      reaction = JSON.parse(msg.data.reaction)
      queryReaction(database, emoji_name, post_id, user_id).fetch()
      if found: database.write(() => reaction[0].destroyPermanently())
```

It does **not** take the same path:

- It never calls `handleReactions` or `sanitizeReactions`, so no flags apply.
- It looks the row up by the natural key (emoji, post, user), not by server ID.
- It destroys the row directly with its own `database.write`, not through `batchRecords`. That means it also doesn't get the `DATABASE_CORRUPTION_DETECTED` emit that `batchRecords` performs on failure.
- If no row matches, it does nothing and reports nothing.

**Things worth knowing**

- Both handlers wrap everything in `try { … } catch { // Do nothing }`. A malformed payload, a missing database, or a write failure produces no log and no error. Given the repo's rule to log errors with context, that is a gap. Nothing in these two functions records a failure.
- `batchRecords` also swallows errors (`propagateError` defaults to `false`). It logs a warning, and only emits a corruption event for corruption errors.
- I did not check the `Reaction` model schema or whether the `reaction` table has a unique index on `(post_id, user_id, emoji_name)`. The dedupe in `sanitizeReactions` is the only guard I confirmed in code.