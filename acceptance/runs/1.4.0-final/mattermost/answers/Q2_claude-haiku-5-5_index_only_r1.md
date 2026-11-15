The add path ends in `handleReactions` with `skipSync: true`, which makes it create-only. The remove path is a separate, direct delete that doesn't use the operator at all. I traced this from the index alone. Two links are inferred from function bodies rather than recorded edges, and I say so below.

**Reaction added**

```
WS "reaction_added"
 └─ handleWebSocketEvent (app/actions/websocket/event.ts)      switch on msg.event
     └─ handleReactionAddedToPostEvent (app/actions/websocket/reactions.ts:21)
         ├─ DatabaseManager.getServerDatabaseAndOperator(serverUrl)
         ├─ JSON.parse(msg.data.reaction) → Reaction
         └─ operator.handleReactions({ prepareRecordsOnly: false,
                                       skipSync: true,
                                       postsReactions: [{post_id, reactions:[reaction]}] })
             └─ ServerDataOperatorBase.handleReactions (handlers/index.ts:124)
                 ├─ sanitizeReactions({database, post_id, rawReactions, skipSync})
                 │    (app/database/operator/utils/reaction.ts:22)
                 │    - loads all Reaction rows for post_id
                 │    - keys them by `${userId}-${emojiName}`
                 │    - raw not in map → createReactions.push({raw})
                 │    - skipSync → returns {createReactions, deleteReactions: []}  (returns early)
                 ├─ prepareRecords({createRaws, transformer: transformReactionRecord, tableName: REACTION})
                 │    └─ transformReactionRecord (transformers/reaction.ts:19)
                 │         sets id (from server raw.id), userId, postId, emojiName, createAt
                 │         → prepareBaseRecord (CREATE)
                 ├─ deleteReactions branch skipped (empty and also guarded by !skipSync)
                 ├─ prepareRecordsOnly is false → skip the early return
                 └─ batchRecords(batchRecords, 'handleReactions')   (base_data_operator/index.ts:191)
                      database.write(writer => writer.batch(...))  → row written
```

Flags on the add path:

| Flag | Value | Effect |
|---|---|---|
| `skipSync` | `true` | `sanitizeReactions` returns before computing `deleteReactions`. Rows that are missing from the payload are never deleted. This is correct for a single-reaction event, because the payload describes one reaction, not the full set on the post. |
| `prepareRecordsOnly` | `false` | `handleReactions` writes to the DB itself instead of returning prepared records to a caller that batches them. |
| `exists` check in `sanitizeReactions` | implicit | If the same user and emoji already have a row, nothing is created. The add path therefore never updates an existing reaction row. |

Errors: `batchRecords` is called without `propagateError`, so a failed write is logged with `logWarning` and not rethrown. If the write fails with a corruption error, it also emits `DATABASE_CORRUPTION_DETECTED`. The outer `try/catch` in `handleReactionAddedToPostEvent` is empty, so parse or lookup failures are dropped silently.

**Reaction removed**

```
WS "reaction_removed"
 └─ handleWebSocketEvent → handleReactionRemovedFromPostEvent (reactions.ts:39)
     ├─ DatabaseManager.getServerDatabaseAndOperator(serverUrl)  → uses only `database`
     ├─ JSON.parse(msg.data.reaction) → msgReaction
     ├─ queryReaction(database, emoji_name, post_id, user_id).fetch()   (queries/servers/reaction.ts:12)
     └─ if found: database.write(() => reaction[0].destroyPermanently())
```

The removal path does not take the same route. It never calls `handleReactions`, `sanitizeReactions`, `transformReactionRecord` or `batchRecords`, so `skipSync` and `prepareRecordsOnly` do not apply. It matches on the composite `(emoji_name, post_id, user_id)`, deletes at most one row, and does nothing if no row matches. Failures inside the `try` are swallowed silently by the empty `catch`, with no log.

**Other notes**

- `handleReactions` is typed to return `ReactionModel | CustomEmojiModel`. The reaction-added handler never produces custom emoji. Custom emoji arrive through the separate `handleAddCustomEmoji` handler (`reactions.ts:7`), which calls `handleCustomEmojis`.
- `handleReactions` is also called from `handlePosts` in `handlers/post.ts`, where `skipSync` is presumably false. That is the only context where the delete branch can run, because it removes rows absent from a full post-reaction list. I did not confirm the caller's flags.

**Index gaps**

- The index shows no callee edge from `handleReactionAddedToPostEvent` to `operator.handleReactions`. The call comes from the function body, which I read directly.
- The `REACTION_ADDED` case lines in `event.ts` (around lines 163–168) were truncated. I inferred the mapping from the search result for `REACTION_REMOVED` at line 166 and the `handleReactionAddedToPostEvent` caller, not from the case body.
- `prepareBaseRecord` (the generic create/update step in `transformers/index.ts`) was not inspected, so the exact `prepareCreate` behaviour is inferred from its name.