**Short answer:** A reaction-added event is written through the server data operator's batch pipeline, with `skipSync: true` so it can only add. A reaction-removed event bypasses the operator entirely: it looks up the row and hard-deletes it in its own write transaction. The two paths share only the switch dispatch and the per-server database handle.

**Added path**

```
WebSocket msg (event = REACTION_ADDED)
  └─ handleWebSocketEvent            app/actions/websocket/event.ts:44
       └─ handleReactionAddedToPostEvent   websocket/reactions.ts:21
            ├─ DatabaseManager.getServerDatabaseAndOperator(serverUrl)
            ├─ JSON.parse(msg.data.reaction)      → Reaction
            └─ operator.handleReactions({ prepareRecordsOnly: false,
                                          skipSync: true,
                                          postsReactions: [{post_id, reactions:[reaction]}] })
                 └─ handleReactions          server_data_operator/handlers/index.ts:124
                      ├─ sanitizeReactions   operator/utils/reaction.ts:22
                      │    ├─ load all Reaction rows for post_id
                      │    ├─ for each raw: exists by `${user_id}-${emoji_name}`? skip : push to createReactions
                      │    └─ skipSync → return { createReactions, deleteReactions: [] }
                      ├─ prepareRecords({createRaws, transformer: transformReactionRecord})
                      │    └─ transformReactionRecord  transformers/reaction.ts:19
                      │         (CREATE: _raw.id = raw.id; sets userId, postId, emojiName, createAt)
                      └─ prepareRecordsOnly is false → batchRecords(…)
                           └─ database.write(writer => writer.batch(...))   base_data_operator/index.ts:191
                                → row inserted in the server DB
```

**Removed path**

```
WebSocket msg (event = REACTION_REMOVED)
  └─ handleWebSocketEvent
       └─ handleReactionRemovedFromPostEvent   websocket/reactions.ts:39
            ├─ DatabaseManager.getServerDatabaseAndOperator(serverUrl)  (uses .database only)
            ├─ JSON.parse(msg.data.reaction)
            ├─ queryReaction(db, emoji_name, post_id, user_id).fetch()   queries/servers/reaction.ts:12
            └─ if found: database.write(() => reaction[0].destroyPermanently())
```

No operator, no `sanitizeReactions`, no transformer. It is a hard delete, not a soft one, and the row is matched on `(emoji_name, post_id, user_id)` rather than the server reaction id.

**Flags and what they change**

- **`skipSync: true` (added path only).** In `sanitizeReactions` it returns early with `deleteReactions: []`, so the code never computes "rows in the DB that are missing from the payload". That diff is only correct for a full post payload, where it is the way stale reactions get removed. A single-reaction event contains one reaction, so without this flag every other reaction on the post would be deleted. `handleReactions` also guards `deleteReactions` with `!skipSync`, a second safety net.
- **`prepareRecordsOnly: false`.** The batch is written immediately instead of being returned for the caller to combine into a larger transaction. Setting it to `true` would return the prepared models without writing.
- **Existence check.** An already-present reaction (same user and emoji on that post) is skipped, not updated. Re-delivery of an add is therefore a no-op.
- **`propagateError` (default `false`).** `batchRecords` logs and swallows write errors, and `handleReactionAddedToPostEvent` has an empty `catch`. A failed write is silent apart from the warning log.

**Caveats**

- The removed handler also has an empty `catch`, so a failed delete is silent.
- The removed path does not check `skipSync` or any similar flag because it never reaches the operator. Its only guard is `reaction.length`, which means a removal for a reaction that is not stored does nothing.
- `handleReactions` is typed to return `CustomEmojiModel` as well, but the function body only handles `Reaction` rows.