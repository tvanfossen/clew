**Short answer:** Reaction-added and reaction-removed share only the entry point. The added event goes through the `DataOperator` handler pipeline, which diffs against the existing rows. The removed event bypasses that pipeline and deletes one row directly.

## Reaction added

```
WebSocket frame (event = "reaction_added")
 └─ websocket_manager.ts:112  client.setEventCallback → handleWebSocketEvent(serverUrl, evt)
     └─ actions/websocket/event.ts:163  case WebsocketEvents.REACTION_ADDED
         └─ actions/websocket/reactions.ts:21  handleReactionAddedToPostEvent
             │  DatabaseManager.getServerDatabaseAndOperator(serverUrl)
             │  reaction = JSON.parse(msg.data.reaction)
             └─ operator.handleReactions({prepareRecordsOnly: false, skipSync: true,
                                           postsReactions: [{post_id, reactions:[reaction]}]})
                 └─ server_data_operator/handlers/index.ts:124  handleReactions
                     ├─ utils/reaction.ts:22  sanitizeReactions({database, post_id, rawReactions, skipSync})
                     │    loads all Reaction rows for post_id
                     │    for each raw: if (user_id, emoji_name) exists → skip; else → createReactions.push
                     │    if skipSync → return {createReactions, deleteReactions: []}   ← returns here
                     ├─ prepareRecords({createRaws, transformer: transformReactionRecord, tableName: REACTION})
                     │    └─ transformers/reaction.ts:19  → prepareBaseRecord → collections.get(REACTION).prepareCreate
                     │         sets _raw.id = server id, userId, postId, emojiName, createAt
                     └─ prepareRecordsOnly is false → batchRecords(batchRecords)
                          └─ base_data_operator/index.ts:191  database.write(writer => writer.batch(...))  ← SQLite write
```

Errors are swallowed twice. `handleReactionAddedToPostEvent` has an empty `catch {}`. `batchRecords` catches write errors, logs a warning and emits `DATABASE_CORRUPTION_DETECTED` for corruption errors, but it does not rethrow because `propagateError` defaults to false.

**Flags that change what gets written, on the added path:**

- **`skipSync: true`** is the important one. In `sanitizeReactions`, it returns before the stale-row diff, so `deleteReactions` is always empty. Without it, the diff would treat every existing reaction on the post that is not in the one-item payload as stale and delete it. A single `reaction_added` event would wipe the other reactions on that post.
- **`prepareRecordsOnly: false`** means the prepared models are actually written. With `true`, the batch would be returned without touching the database.
- **Existing row = no-op.** If a row with the same user and emoji already exists, `sanitizeReactions` only marks it as "similar" and never updates it. A duplicate `reaction_added` therefore writes nothing, and the server id is only set on creation.

## Reaction removed

```
handleWebSocketEvent  case REACTION_REMOVED (event.ts:166)
 └─ handleReactionRemovedFromPostEvent (reactions.ts:39)
     ├─ database = DatabaseManager...  (no operator)
     ├─ msgReaction = JSON.parse(msg.data.reaction)
     ├─ queryReaction(database, emoji_name, post_id, user_id).fetch()   queries/servers/reaction.ts:12
     └─ if found: database.write(() => reaction[0].destroyPermanently())
```

**Does it take the same path?** No, not after the switch. It skips the operator, `sanitizeReactions`, the transformer, and `batchRecords`. It does not go through `handleReactions` with `skipSync: false`. Some differences follow from that:

- If no row matches, nothing happens and nothing is logged.
- Only the first matching row is destroyed.
- A write failure is caught by the empty `catch`. The `DATABASE_CORRUPTION_DETECTED` emit that `batchRecords` performs does not happen on this path.

Hard deletion is done by `destroyPermanently()` inside `database.write`. The added path instead builds `prepareCreate` records and submits them in one batch.

**Observability gap:** Both handlers swallow every error with an empty catch and no log, which conflicts with the repo's rule to log errors with context. A failed reaction write leaves no trace.

I confirmed the call chain with the index and read the handler sources directly. I did not run the tests in `app/actions/websocket/reactions.test.ts` or the event dispatch test.