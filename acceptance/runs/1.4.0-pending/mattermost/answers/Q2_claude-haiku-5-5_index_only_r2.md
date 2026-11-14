The add path writes the row immediately and deduplicates in memory. The remove path does not use the handler at all: it looks up the row and destroys it directly. Neither path is a single flag-driven pipeline, and both swallow errors silently.

**Add path ("reaction_added")**

```
WS message ─► websocket_manager.createClient
  ─► handleWebSocketEvent (actions/websocket/event.ts:44)
       switch: WebsocketEvents.REACTION_ADDED ('reaction_added')  → line 163
  ─► handleReactionAddedToPostEvent (actions/websocket/reactions.ts:21)
       1. operator = DatabaseManager.getServerDatabaseAndOperator(serverUrl)
       2. reaction = JSON.parse(msg.data.reaction)
       3. operator.handleReactions({
            prepareRecordsOnly: false,
            skipSync: true,
            postsReactions: [{post_id, reactions:[reaction]}] })
  ─► handleReactions (db/operator/server_data_operator/handlers/index.ts:124)
       a. sanitizeReactions({database, post_id, rawReactions, skipSync})
            - loads all Reaction rows for post_id
            - keys them "userId-emojiName"
            - raw reaction whose key exists → skipped (not updated)
            - otherwise → createReactions
            - skipSync=true → returns here, deleteReactions = []
       b. prepareRecords({createRaws, transformer: transformReactionRecord, tableName: REACTION})
            - transformReactionRecord (transformers/reaction.ts:19)
              sets _raw.id = raw.id, userId, postId, emojiName, createAt
       c. prepareRecordsOnly false → this.batchRecords(batch) → database.write(writer.batch)
  ─► row persisted in the server DB's Reaction table
```

Flags on this path:
- `prepareRecordsOnly: false` means the handler writes the batch itself and returns it. The local `addReaction` action passes `true` and batches the models with recent-emoji records, so there is one transaction.
- `skipSync: true` does two things. In `sanitizeReactions` it returns before computing deletions, so it never removes other reactions on the post. In `handleReactions` the delete branch is guarded by `!skipSync`. This is the reason the WebSocket path can carry only one reaction and not wipe the rest.

**Remove path ("reaction_removed")**

```
WS message ─► handleWebSocketEvent → REACTION_REMOVED (event.ts:166)
  ─► handleReactionRemovedFromPostEvent (actions/websocket/reactions.ts:39)
       1. database = getServerDatabaseAndOperator(serverUrl).database
       2. msgReaction = JSON.parse(msg.data.reaction)
       3. rows = queryReaction(database, emoji_name, post_id, user_id).fetch()
       4. if rows.length → database.write(() => rows[0].destroyPermanently())
```

It does not go through `handleReactions`, `sanitizeReactions`, `prepareRecords` or `batchRecords`. It has no `prepareRecordsOnly` or `skipSync` flags, and it does not call `transformReactionRecord`. Its only write is the delete. It is the same path only in the sense that both start in `handleWebSocketEvent`. The local `removeReaction` action (remote/reactions.ts:94) follows the same query-and-destroy pattern after the server call.

**Things to note**
- Both WebSocket handlers wrap everything in `try { … } catch { // Do nothing }`. A malformed payload or DB error is dropped with no log, which conflicts with the repo's logging rules.
- Deduplication is a read-then-write check, not a unique constraint. The local `addReaction` writes its own row, and the server's echo of the same reaction then hits the `exists` check and is skipped. Two concurrent inserts could still both pass the check.
- The remove handler uses `msgReaction.emoji_name` as-is, while the local add and remove actions normalise with `getEmojiFirstAlias`. This works only if the server always sends the first alias.

I did not verify the test coverage or the schema doc for the Reaction table. `app/actions/websocket/reactions.test.ts` exists, but I did not read its assertions.