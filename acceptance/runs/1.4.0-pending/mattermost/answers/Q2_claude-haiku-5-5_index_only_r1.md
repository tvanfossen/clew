**Short answer:** The add and remove events both start in `handleWebSocketEvent`, but they take different paths after that. Add goes through the sync-handler machinery (`sanitizeReactions` → `handleReactions` → transformer → `batchRecords`). Remove bypasses that machinery entirely and destroys the row directly. The only flag on the path is `skipSync: true` on the add side, and it does not change what gets written on add.

```
websocket msg (event: "reaction_added")
  └─ websocket_manager.createClient → handleWebSocketEvent(serverUrl, msg)   [event.ts:44]
       switch(msg.event) case REACTION_ADDED                                  [event.ts:163]
         └─ handleReactionAddedToPostEvent(serverUrl, msg)                    [websocket/reactions.ts:21]
              ├─ DatabaseManager.getServerDatabaseAndOperator(serverUrl)
              ├─ reaction = JSON.parse(msg.data.reaction)
              └─ operator.handleReactions({prepareRecordsOnly:false, skipSync:true,
                                           postsReactions:[{post_id, reactions:[reaction]}]})
                   └─ handleReactions                                         [handlers/index.ts:124]
                        ├─ sanitizeReactions({database, post_id, rawReactions, skipSync})  [utils/reaction.ts:22]
                        │    ├─ load all Reaction rows for post_id
                        │    ├─ map existing by `${userId}-${emojiName}`
                        │    ├─ raw not in map → createReactions.push({raw})
                        │    └─ skipSync → return {createReactions, deleteReactions: []}
                        ├─ prepareRecords({createRaws, transformer: transformReactionRecord, tableName: REACTION})
                        │    └─ transformReactionRecord [transformers/reaction.ts:19]
                        │         └─ prepareBaseRecord → database.collections.get(REACTION).prepareCreate(fieldsMapper)
                        │              fieldsMapper: _raw.id = raw.id, userId, postId, emojiName, createAt
                        └─ batchRecords(batchRecords, 'handleReactions')      [base_data_operator:191]
                             └─ database.write(writer => writer.batch(...))   ← row lands in SQLite here
```

**Add path, step by step**

1. `handleWebSocketEvent` maps `WebsocketEvents.REACTION_ADDED` (`'reaction_added'`, `constants/websocket.ts:47`) to `handleReactionAddedToPostEvent`. The call is not awaited in the switch.
2. The handler parses `msg.data.reaction`, which is a JSON string, and passes it as a one-element `postsReactions` array to the server operator's `handleReactions`.
3. `sanitizeReactions` decides what to create. It skips any raw reaction whose `user_id + emoji_name` already exists on the post, so a duplicate add writes nothing.
4. `handleReactions` builds `ReactionModel` records with `transformReactionRecord`. On create, the record's `_raw.id` comes from the server's reaction id.
5. `batchRecords` runs the writes inside `database.write`.

**Flags that matter on the add path**

- **`skipSync: true`** (set by the websocket handler). In `sanitizeReactions`, this returns early with `deleteReactions: []`, so a single add event never deletes other reactions on the post. Without it, the function would diff the full DB set against the incoming list and mark anything missing for deletion. In `handleReactions`, the same flag gates the `deleteReactions` branch.
- **`prepareRecordsOnly: false`** means the handler actually writes. With `true`, it would return the prepared records without persisting them.
- Errors are swallowed twice. `batchRecords` is called without `propagateError`, so a write failure only logs a warning. The websocket handler also has an empty `catch`.

**Remove path: no, it does not take the same path**

`handleReactionRemovedFromPostEvent` (`websocket/reactions.ts:39`) does not call `handleReactions`, `sanitizeReactions`, or any transformer:

1. Parse `msg.data.reaction`.
2. `queryReaction(database, emoji_name, post_id, user_id).fetch()` finds the row (`queries/servers/reaction.ts:12`).
3. If a row is found, `database.write` calls `reaction[0].destroyPermanently()`.

So the remove path has no flags. `skipSync` and `prepareRecordsOnly` do not apply. It also cannot leave a stale row behind, because it deletes whatever row matches the three-field key. It does not use `handleReactions` in any way, so the `deleteReactions` branch is never reached on this path. The write is a direct, permanent destroy rather than a soft delete, and it only ever removes `reaction[0]`.

**Caveats**

- I did not open the body of `destroyPermanently`, so I am assuming it is the standard WatermelonDB model method.
- Both websocket handlers swallow all errors with empty `catch` blocks, so a failed add or remove is silent in the logs.