**Short answer:** Both events enter through the same switch but take different paths. "Added" goes through the operator's batch-write machinery with `skipSync: true`. "Removed" bypasses the operator entirely and calls `destroyPermanently()` directly. Neither path touches the database if its input is a no-op. Both handlers swallow every error silently.

## Reaction added

```
WebSocket frame (event = 'reaction_added')
  └─ handleWebSocketEvent(serverUrl, msg)              app/actions/websocket/event.ts:44
       case REACTION_ADDED → handleReactionAddedToPostEvent(serverUrl, msg)   :163-165
          (not awaited)
  └─ handleReactionAddedToPostEvent                    app/actions/websocket/reactions.ts:21
       1. DatabaseManager.getServerDatabaseAndOperator(serverUrl)
       2. reaction = JSON.parse(msg.data.reaction)     // data.reaction is a JSON string
       3. operator.handleReactions({
            prepareRecordsOnly: false,
            skipSync: true,
            postsReactions: [{post_id, reactions: [reaction]}] })
  └─ handleReactions                                   .../server_data_operator/handlers/index.ts:124
       for each postReactions:
         a. sanitizeReactions({database, post_id, rawReactions, skipSync})
              app/database/operator/utils/reaction.ts:22
              - query all Reaction rows where post_id = X
              - build map key "userId-emojiName"
              - raw not in map  → createReactions.push({raw})
              - raw already in map → ignored (not created, not updated)
              - if skipSync → return {createReactions, deleteReactions: []}   ← early return
         b. createReactions → prepareRecords({createRaws, transformer: transformReactionRecord})
              → transformReactionRecord (transformers/reaction.ts:19)
                  sets _raw.id = raw.id (server id), userId, postId, emojiName, createAt
                  via prepareBaseRecord with action CREATE
         c. deleteReactions skipped (empty + skipSync guard)
       prepareRecordsOnly is false → this.batchRecords(batchRecords, 'handleReactions')
  └─ batchRecords  (base_data_operator/index.ts:191)
       database.write(writer => writer.batch(...models))   ← the actual DB write
```

**Stored result:** one new `Reaction` row, with the server's id, `userId`, `postId`, `emojiName` and `createAt`. If the same user already has the same emoji on that post locally, nothing is written.

## Reaction removed

```
handleWebSocketEvent → case REACTION_REMOVED            event.ts:166-168
  └─ handleReactionRemovedFromPostEvent                 reactions.ts:39
       1. database = getServerDatabaseAndOperator(serverUrl).database   (operator not used)
       2. msgReaction = JSON.parse(msg.data.reaction)
       3. reaction = queryReaction(database, emoji_name, post_id, user_id).fetch()
       4. if found: database.write(() => reaction[0].destroyPermanently())
```

It does not go through `handleReactions`, `sanitizeReactions`, a transformer, or `batchRecords`. It matches on `(emoji, post, user)` rather than on the server id. Nothing is written if no matching row exists.

## Flags that change what gets written

| Flag | Where | Effect |
|---|---|---|
| `skipSync: true` | Added handler | `sanitizeReactions` returns right after computing `createReactions`, so `deleteReactions` is always empty. Without it, the single reaction in the payload would be treated as the complete reaction set for the post, and every other user's reaction on that post would be marked for deletion. |
| `prepareRecordsOnly: false` | Added handler | `handleReactions` calls `batchRecords` itself. With `true`, it would return the prepared models for the caller to batch. |
| `skipSync` (guard at `handlers/index.ts`, `deleteReactions?.length && !skipSync`) | `handleReactions` | Redundant with the early return in `sanitizeReactions`, but it is a second guard against deletes on that path. |

The sync path that calls `handleReactions` with `skipSync` unset, from `PostHandler.handlePosts` according to the caller index, is the only place that can delete reactions. It treats the array as the full set for each post.

## Things worth knowing

- **Errors are silent.** Both handlers wrap everything in `try { … } catch { // Do nothing }`. A malformed payload or a DB error leaves no log. The add path's `batchRecords` does log a warning and emit `DATABASE_CORRUPTION_DETECTED`, but a failure in `JSON.parse` or in the sanitize query never gets that far. This conflicts with the repo's logging rules.
- **The add path is not idempotent on update.** Duplicates are skipped, so a changed `create_at` for an existing reaction is never written.
- **The remove path skips the operator layer.** It writes directly to the database, so any operator-level behavior (corruption detection, the batch description) doesn't apply to it.
- **The two paths are not symmetric.** Add reads all reactions on the post and uses the server id. Remove reads one row by compound key and destroys it.

I did not check the tests in `reactions.test.ts` or `event.test.ts`, and I did not run the app.