**Short answer:** The add path writes one `Reaction` row through the server operator, with `skipSync: true`, which suppresses deletions. The remove path does not use the operator at all. It queries the matching row and calls `destroyPermanently()` directly inside a `database.write`. Neither path uses `prepareRecordsOnly`.

## Reaction added: call chain

```
WebSocket frame (event = 'reaction_added')
 └─ client.setEventCallback            app/managers/websocket_manager.ts:112
     └─ handleWebSocketEvent(serverUrl, msg)   app/actions/websocket/event.ts:44
         │  switch(msg.event) → case REACTION_ADDED        (~line 163)
         └─ handleReactionAddedToPostEvent(serverUrl, msg)  app/actions/websocket/reactions.ts:21
             ├─ DatabaseManager.getServerDatabaseAndOperator(serverUrl)
             ├─ reaction = JSON.parse(msg.data.reaction)    // data.reaction is a JSON string
             └─ operator.handleReactions({
                  prepareRecordsOnly: false,
                  skipSync: true,
                  postsReactions: [{post_id, reactions:[reaction]}] })
                  │  app/database/operator/server_data_operator/handlers/index.ts:124
                  ├─ sanitizeReactions({database, post_id, rawReactions, skipSync})
                  │     app/database/operator/utils/reaction.ts:22
                  │     • loads every Reaction row for post_id
                  │     • builds map key `${userId}-${emojiName}`
                  │     • raw not in map → createReactions.push({raw})
                  │     • skipSync === true → return {createReactions, deleteReactions: []}
                  ├─ if createReactions: prepareRecords({createRaws, transformer: transformReactionRecord, tableName: REACTION})
                  │     base_data_operator/index.ts:134 → transformer(action=CREATE)
                  │     transformers/reaction.ts:19 → prepareBaseRecord → collections.get(REACTION).prepareCreate
                  │     (_raw.id = server reaction id, userId, postId, emojiName, createAt)
                  └─ batchRecords(...)  → database.write(writer.batch(...))   base_data_operator/index.ts:191
```

Errors are swallowed in the outer `try/catch` (`// Do nothing`), and `batchRecords` logs a warning and does not rethrow by default. A failed write is therefore silent to the caller.

## Reaction removed: call chain

```
WebSocket frame (event = 'reaction_removed')
 └─ handleWebSocketEvent  case REACTION_REMOVED         event.ts:166
     └─ handleReactionRemovedFromPostEvent              reactions.ts:39
         ├─ database = DatabaseManager...(serverUrl).database   (no operator)
         ├─ msgReaction = JSON.parse(msg.data.reaction)
         ├─ queryReaction(database, emoji_name, post_id, user_id).fetch()
         └─ if found: database.write(() => reaction[0].destroyPermanently())
```

This path does not call `handleReactions`, `sanitizeReactions`, or any transformer. It has no `skipSync` or `prepareRecordsOnly` flags. It matches on the composite key `(emoji_name, post_id, user_id)` rather than on the server ID. If no row matches, it does nothing.

## Flags that change what gets written

| Flag | Where | Effect |
|---|---|---|
| `skipSync: true` | add path, set in `reactions.ts:21` | `sanitizeReactions` returns early at `reaction.ts:42-44`, before computing `deleteReactions`. The add path never deletes other reactions on the post. Without this flag, any local reaction absent from the payload would be marked for destruction. |
| `prepareRecordsOnly` | `handleReactions`, `handlers/index.ts:124-171` | `false` in the add path, so the batch is written. When `true`, the records are returned without being written. Nothing in this path sets it to `true`. |
| `deleteReactions?.length && !skipSync` | `handlers/index.ts:~152` | Double-guards deletion. The add path never reaches it. |
| Existence check in `sanitizeReactions` | `reaction.ts:33-36` | If a row for the same user and emoji already exists locally, nothing is created. A duplicate `reaction_added` is idempotent. |

Within the add path, the only write is `create` with the server-supplied ID. The update branch is not used.

## Does "removed" take the same path?

No, in three ways:

1. **Different entry point.** It uses `handleReactionRemovedFromPostEvent` (`reactions.ts:39`), not the operator.
2. **Different lookup key.** It matches on `(user_id, emoji_name, post_id)` rather than on the server ID.
3. **Different write.** It calls `destroyPermanently()` directly in a `database.write`, not `batchRecords` via `prepareDestroyPermanently`.

The sync-handler rule in CLAUDE.md (diff existing rows against the incoming set, then destroy stale ones) applies to full-sync handlers. The `skipSync` flag is what keeps the add path out of that diff logic. The remove path is a targeted delete, so it does not need the diff.

## Caveats

- I did not read the body of `handleWebSocketEvent`'s `REACTION_ADDED` and `REACTION_REMOVED` cases in full. The index shows both cases call the handlers above, and the dossier's callee list confirms it.
- The `reaction_added` payload shape (`msg.data.reaction` as a JSON string) is inferred from the two handlers' `JSON.parse` calls. I did not check it against the server's payload.