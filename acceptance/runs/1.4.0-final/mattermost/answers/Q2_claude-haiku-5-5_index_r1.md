**Short answer:** A "reaction added" event goes through the operator's `handleReactions` and is written as a create. A "reaction removed" event skips the operator entirely: it looks up the single matching row and destroys it. The two paths do not share the write logic.

## Added path

```
WebSocket frame (event = REACTION_ADDED)
  └─ handleWebSocketEvent            app/actions/websocket/event.ts:44
       case REACTION_ADDED (l.163) → handleReactionAddedToPostEvent(serverUrl, msg)
  └─ handleReactionAddedToPostEvent  app/actions/websocket/reactions.ts:21
       1. DatabaseManager.getServerDatabaseAndOperator(serverUrl)
       2. reaction = JSON.parse(msg.data.reaction)   // payload is a JSON string
       3. operator.handleReactions({ prepareRecordsOnly: false,
                                     skipSync: true,
                                     postsReactions: [{post_id, reactions:[reaction]}] })
  └─ handleReactions  app/database/operator/server_data_operator/handlers/index.ts:124
       a. sanitizeReactions({database, post_id, rawReactions, skipSync})
            app/database/operator/utils/reaction.ts:22
            - loads all Reaction rows for post_id
            - keys them by `${userId}-${emojiName}`
            - raw reaction not in the map → createReactions
            - skipSync true → returns { createReactions, deleteReactions: [] } immediately
       b. createReactions → prepareRecords({createRaws, transformer: transformReactionRecord, tableName: REACTION})
            base_data_operator/index.ts:134
            → transformReactionRecord (server_data_operator/transformers/reaction.ts:19)
                 action = CREATE, so record._raw.id = raw.id (server id)
                 sets userId, postId, emojiName, createAt
                 → prepareBaseRecord → database.collections.get(REACTION).prepareCreate(...)
       c. prepareRecordsOnly false → batchRecords(batchRecords, 'handleReactions')
            base_data_operator/index.ts:191
            → database.write(writer => writer.batch(...))   ← the DB write happens here
```

The handler's `catch {}` swallows every error, so a failed add leaves no trace in the logs.

## Removed path

```
WebSocket frame (event = REACTION_REMOVED)
  └─ handleWebSocketEvent  event.ts:166 → handleReactionRemovedFromPostEvent(serverUrl, msg)
  └─ handleReactionRemovedFromPostEvent  app/actions/websocket/reactions.ts:39
       1. database = getServerDatabaseAndOperator(serverUrl).database   (no operator)
       2. msgReaction = JSON.parse(msg.data.reaction)
       3. queryReaction(database, emoji_name, post_id, user_id).fetch()
            app/queries/servers/reaction.ts:12   (three Q.where clauses)
       4. if found: database.write(() => reaction[0].destroyPermanently())
```

It does not call `handleReactions` or `sanitizeReactions`, and it never goes through `transformReactionRecord`. It is a targeted lookup and a single hard delete.

## Flags that change what gets written

| Flag | Where | Effect |
|---|---|---|
| `prepareRecordsOnly: false` (add) | `handleReactions` l.165 | Writes immediately. With `true`, it would return the batch for the caller to commit. |
| `skipSync: true` (add) | `sanitizeReactions` l.46 | Returns before computing `deleteReactions`. The operator's `!skipSync` guard on deletes (l.155) is then redundant for this call. |

`skipSync` matters because the payload holds only one reaction. Without it, `sanitizeReactions` would treat every other existing reaction on the post as stale and destroy it. (This is my reading of the code. The payload contains only the new reaction, which is why the guard is needed.)

Other notes on the add path:
- **Duplicates are no-ops.** If a row with the same `(user, emoji, post)` already exists, `sanitizeReactions` puts it in `similarObjects` instead of `createReactions`. Nothing is updated, and the original `create_at` is kept.
- **Custom emoji are not handled here.** `handleReactions` returns `ReactionModel | CustomEmojiModel` in its signature, but the body only creates `ReactionModel` rows for this event.

## Summary of the differences

| | Added | Removed |
|---|---|---|
| Entry | `handleReactionAddedToPostEvent` | `handleReactionRemovedFromPostEvent` |
| Goes through operator | Yes (`handleReactions`) | No (direct `database`) |
| Lookup | Full post reaction set, keyed by user+emoji | Single `queryReaction` by emoji, post, user |
| Write | `prepareCreate` + `batchRecords` (one `write`) | `destroyPermanently()` inside `database.write` |
| Flags | `prepareRecordsOnly:false`, `skipSync:true` | None |
| Errors | Silently swallowed | Silently swallowed |

Neither path does a "sync" against the server. The add path avoids the delete logic only because of `skipSync: true`.