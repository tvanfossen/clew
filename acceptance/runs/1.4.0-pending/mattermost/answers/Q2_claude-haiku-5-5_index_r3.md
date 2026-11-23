## Short answer

Yes, the removal event takes a different path, and it does not go through the operator at all. Both handlers are fire-and-forget from the dispatcher. The add path writes through `ServerDataOperator.handleReactions` with `skipSync: true`, which makes it create-only. The removal path looks up the row and calls `destroyPermanently()` directly. Nothing in the add path deletes, and nothing in the removal path uses the operator's create/update machinery.

## Add path

```
WebSocket "reaction_added"
  └─ app/actions/websocket/event.ts:163   switch(msg.event) → handleReactionAddedToPostEvent(serverUrl, msg)   (not awaited)
       └─ app/actions/websocket/reactions.ts:21
            ├─ DatabaseManager.getServerDatabaseAndOperator(serverUrl)
            ├─ reaction = JSON.parse(msg.data.reaction)
            └─ operator.handleReactions({prepareRecordsOnly: false, skipSync: true,
                                         postsReactions: [{post_id, reactions: [reaction]}]})
                 └─ handlers/index.ts:124  ServerDataOperatorBase.handleReactions
                      ├─ utils/reaction.ts:22  sanitizeReactions({database, post_id, rawReactions, skipSync: true})
                      │    ├─ load all Reaction rows for post_id
                      │    ├─ for each raw: if (user_id, emoji_name) exists → skip; else → createReactions.push
                      │    └─ if (skipSync) return {createReactions, deleteReactions: []}   ← early return
                      ├─ prepareRecords({createRaws, transformer: transformReactionRecord, tableName: REACTION})
                      │    └─ transformers/reaction.ts:19  sets _raw.id (server id), userId, postId, emojiName, createAt
                      └─ prepareRecordsOnly false → batchRecords(batch)   → written to the Reaction table
```

Things worth knowing about the add path:

- **`skipSync: true` is the flag that matters.** Without it, `sanitizeReactions` would compute `deleteReactions` as "every stored reaction on this post not in the payload." A payload carrying only one reaction would then wipe the post's other reactions. The early return in `utils/reaction.ts` prevents that, and `handleReactions` also guards deletes with `!skipSync`.
- **Duplicates are a no-op.** If a row with the same `(user, emoji)` already exists, it is skipped rather than updated, so a re-delivered event does nothing.
- **`prepareRecordsOnly: false`** is why this path commits. `handlePosts` calls the same handler with `true` and batches the result with post writes.
- **Errors are swallowed.** The whole body is in `try {} catch { // Do nothing }`, and the dispatcher doesn't await the promise, so a failed write leaves no trace.

## Removal path

```
WebSocket "reaction_removed"
  └─ event.ts:166 → handleReactionRemovedFromPostEvent(serverUrl, msg)   (not awaited)
       └─ reactions.ts:39
            ├─ database = DatabaseManager...   (note: no operator)
            ├─ msgReaction = JSON.parse(msg.data.reaction)
            ├─ queries/servers/reaction.ts:12  queryReaction(emoji_name, post_id, user_id).fetch()
            └─ if (reaction.length) database.write(() => reaction[0].destroyPermanently())
```

- It does **not** call `handleReactions`, so `sanitizeReactions`, `skipSync`, and `prepareRecordsOnly` are never involved.
- It deletes only the first match (`reaction[0]`) and does nothing if no row matches. The match key is `(emoji_name, post_id, user_id)`, not the server `id`.
- It uses its own `database.write` wrapper and the same silent `catch`.

## Flags summary

| Flag | Where | Effect |
|---|---|---|
| `skipSync: true` | add event | Create-only. Stored reactions not in the payload are kept. |
| `skipSync` unset | `handlePosts` (post sync) | Full reconciliation. Stored reactions missing from the payload are queued for `destroyPermanently`. |
| `prepareRecordsOnly: false` | add event | Commits the batch via `batchRecords`. |
| `prepareRecordsOnly: true` | `handlePosts` | Returns prepared models so they join the post batch. |

## Not verified

I read the code but did not run the tests. `reactions.test.ts` and `reaction.test.ts` cover these paths, and I haven't run them.