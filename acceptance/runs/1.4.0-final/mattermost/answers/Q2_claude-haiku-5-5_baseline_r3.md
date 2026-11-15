**Short answer:** Reaction-added goes through the operator's `handleReactions` with `skipSync: true`, which makes it an insert-only write. Reaction-removed does not use the operator at all. It looks up the one row and destroys it directly. So the two events take different paths, and the removed path never uses the `skipSync` flag.

### Reaction added

```
WS frame (event = "reaction_added")
  └─ handleWebSocketEvent            app/actions/websocket/event.ts:45
       case REACTION_ADDED (:163)    → handleReactionAddedToPostEvent(serverUrl, msg)  (not awaited)
            └─ reactions.ts:21
                 DatabaseManager.getServerDatabaseAndOperator(serverUrl)
                 reaction = JSON.parse(msg.data.reaction)
                 operator.handleReactions({
                   prepareRecordsOnly: false,
                   skipSync: true,
                   postsReactions: [{post_id, reactions: [reaction]}] })
                   └─ handlers/index.ts:124  handleReactions
                        for each post:
                          sanitizeReactions({..., rawReactions, skipSync})
                            └─ handlers/reaction.ts:22
                                 load all reactions where post_id = X
                                 map by `${userId}-${emojiName}`
                                 for raw in rawReactions:
                                   exists? → add to similarObjects (no write)
                                   else    → createReactions.push({raw})
                                 if skipSync → return {createReactions, deleteReactions: []}
                          if createReactions:
                            prepareRecords(transformReactionRecord)  → ReactionModel
                        (deletion branch skipped because skipSync)
                        prepareRecordsOnly is false → batchRecords(...)  → one database write
```

The transformer (`transformers/reaction.ts:19`) takes the row ID from the server's `raw.id` and copies `user_id`, `post_id`, `emoji_name` and `create_at` onto the model.

### The flags that change what gets written

- **`skipSync: true`** (set in `reactions.ts:28`). Without it, `sanitizeReactions` would also return every stored reaction on the post that is absent from `rawReactions` as `deleteReactions`. Since `rawReactions` holds only the one new reaction, every other reaction on the post would be deleted. The flag turns this into an insert-only write. It is the only thing preventing that wipe.
- **`prepareRecordsOnly: false`**. The handler writes immediately through `batchRecords`. It does not return prepared records for an outer batch, which is what `handlePostEdited`-style callers do (`handlers/post.ts:564` uses `prepareRecordsOnly: true`).
- **Existing rows are not updated.** If a reaction with the same user and emoji is already stored, it lands in `similarObjects` and nothing is written. A duplicate `reaction_added` is a no-op.

### Reaction removed

```
WS frame (event = "reaction_removed")
  └─ event.ts:166 → handleReactionRemovedFromPostEvent   (not awaited)
       └─ reactions.ts:39
            database = getServerDatabaseAndOperator(serverUrl).database
            msgReaction = JSON.parse(msg.data.reaction)
            reaction = queryReaction(database, emoji_name, post_id, user_id).fetch()
            if reaction.length:
              database.write(() => reaction[0].destroyPermanently())
```

It does **not** go through `handleReactions`, `sanitizeReactions`, or the transformer. It locates the one row by emoji, post and user, then destroys it permanently inside a single write. This is a different path from added, not the same path with a delete flag.

Why not reuse `handleReactions`? With `skipSync` left off, the removed reaction would be missing from `rawReactions`, so `sanitizeReactions` would mark every reaction on the post for deletion. Passing `skipSync: true` would instead make the event a no-op. The dedicated handler avoids both problems. The removed path passes no `skipSync` flag and does not need one.

### Things worth noting

- Both handlers are fire-and-forget. `event.ts` does not `await` them, and both wrap everything in `try { … } catch { // Do nothing }`. A failed write is silent, with no `logError` as the CLAUDE.md asks.
- The removed handler takes `database` directly and calls `database.write`. The added handler goes through `operator`. Both are reasonable, but they are two different write styles.
- I did not check whether the reaction-removed path needs a sync-handler delete check, because it is not a sync handler. It is a single-record event handler.
- Tests cover the dispatch (`event.test.ts:267–276`) and both handlers (`reactions.test.ts`). I did not run them.