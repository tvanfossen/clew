## Short answer

A "reaction added" event takes a generic upsert path with the diff-based delete turned off. A "reaction removed" event does not use that path at all. It runs its own lookup and a direct `destroyPermanently`. The only flag on the add path is `skipSync: true`, and it is what keeps the one-reaction payload from wiping the post's other reactions.

## Add path

```
websocket_manager.ts:112  client.setEventCallback → handleWebSocketEvent(serverUrl, evt)
        │
event.ts:44 / :163        switch(msg.event) → REACTION_ADDED
        │
websocket/reactions.ts:21 handleReactionAddedToPostEvent
        │   JSON.parse(msg.data.reaction)
        │   operator.handleReactions({ prepareRecordsOnly: false,
        │                              skipSync: true,
        │                              postsReactions: [{post_id, reactions:[reaction]}] })
        ▼
handlers/index.ts:124     handleReactions
        │   sanitizeReactions({database, post_id, rawReactions, skipSync})
        ▼
utils/reaction.ts:22      load ALL local reactions for post_id
        │   map key = `${userId}-${emojiName}`
        │   raw not in map → createReactions.push({raw})
        │   skipSync → return {createReactions, deleteReactions: []}   (:49-51)
        ▼
handlers/index.ts:146     prepareRecords(transformReactionRecord) → REACTION
        │   transformers/reaction.ts:19  sets _raw.id = server id,
        │   userId, postId, emojiName, createAt
        ▼
handlers/index.ts:166     prepareRecordsOnly is false → batchRecords() → one database write
```

Points on this path:

- **Create-only.** A reaction that already exists locally (same user and emoji on that post) is matched and skipped. Nothing is updated.
- **Errors are swallowed.** Both handlers wrap everything in `try { … } catch { // Do nothing }` (`websocket/reactions.ts:34-36`). A failed write leaves no trace in the logs. That conflicts with the repo's rule against silently ignoring errors.

## Remove path

```
event.ts:166 → handleReactionRemovedFromPostEvent (websocket/reactions.ts:39)
        │   JSON.parse(msg.data.reaction)
        │   queryReaction(database, emoji_name, post_id, user_id).fetch()
        │       (queries/servers/reaction.ts:12)
        │   if found:
        │       database.write → reaction[0].destroyPermanently()
        ▼
   one row deleted; no-op if not found
```

It does **not** use the operator, `handleReactions`, `sanitizeReactions`, or the transformer. It also has no `skipSync` or `prepareRecordsOnly` flag, so the question of which flag applies does not arise. Only the one matching row is touched, and the same error-swallowing `catch` applies.

## Flags that change what gets written

| Flag | Where | Effect |
|---|---|---|
| `skipSync: true` | WS add (`websocket/reactions.ts:28`) and remote `addReaction` (`remote/reactions.ts:66`) | `sanitizeReactions` returns before computing `deleteReactions` (`utils/reaction.ts:49`). Without it, every local reaction on the post that is absent from the one-item payload would be marked for deletion. |
| `prepareRecordsOnly` | WS add: `false`, so it writes immediately. Remote `addReaction`: `true`, so it collects models and batches them with the recent-emoji records. | Controls whether `handleReactions` writes or only returns prepared models (`handlers/index.ts:162-168`). |
| `skipSync` in the sync path | Not passed on a full sync (default `undefined`) | Enables the diff: stale local reactions are returned as `deleteReactions` and destroyed via `prepareDestroyPermanently` (`handlers/index.ts:156-158`). This is the behaviour the repo's sync-handler rule expects. |

## Caveats

- The remove event deletes only the row matching `(emoji_name, post_id, user_id)`. The add path matches on `userId-emojiName` within a post. These keys are equivalent.
- I did not trace the websocket reconnect or the `handleReactions` callers in the sync flows beyond what is listed above.
- A `dossier` note appeared in tool output during this session. I ignored it and used only Read and Grep.