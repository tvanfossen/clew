## Short answer

A `reaction_added` event is parsed, checked against the local Reaction table, and inserted through the server operator's `handleReactions` with `skipSync: true` and `prepareRecordsOnly: false`. A `reaction_removed` event does **not** use that path. It skips the operator entirely, looks up the row, and calls `destroyPermanently()` directly. Neither path is the same as the full-sync path.

## Added path

```
WS "reaction_added"
 └─ handleWebSocketEvent            app/actions/websocket/event.ts:163
     └─ handleReactionAddedToPostEvent   app/actions/websocket/reactions.ts:21
         ├─ JSON.parse(msg.data.reaction)  → Reaction
         └─ operator.handleReactions({
              prepareRecordsOnly: false,
              skipSync: true,
              postsReactions: [{post_id, reactions:[reaction]}] })
             └─ handleReactions         handlers/index.ts:124
                 ├─ sanitizeReactions   utils/reaction.ts:22
                 │    ├─ query all Reaction rows where post_id = X
                 │    ├─ key each by `${userId}-${emojiName}`
                 │    ├─ incoming not in DB  → createReactions
                 │    └─ skipSync → return {createReactions, deleteReactions: []}
                 ├─ prepareRecords(transformReactionRecord)   transformers/reaction.ts:19
                 │    └─ CREATE: _raw.id = server id, set userId/postId/emojiName/createAt
                 └─ prepareRecordsOnly is false → batchRecords()
                      └─ database.write → writer.batch(...)   base_data_operator:191
```

Notes on this path:

- **`skipSync: true` is the important flag.** Without it, `sanitizeReactions` computes `deleteReactions` as every local reaction on the post that is absent from the payload. The payload holds only one reaction, so a single event would delete all the other reactions on that post. With the flag, the function returns early and never computes deletions.
- **Duplicates are no-ops.** If the reaction already exists locally (for example, because this client sent it through `addReaction`), it lands in `similarObjects` and is not re-created or updated.
- **`prepareRecordsOnly: false`** means the write happens inside `handleReactions`. The local `addReaction` (`app/actions/remote/reactions.ts:48`) also passes `skipSync: true` but uses `prepareRecordsOnly: true`, so it can batch the reaction together with the recent-emoji record.
- **Error handling:** the `switch` in `event.ts` calls `handleReactionAddedToPostEvent` without `await`, and the function's `catch {}` swallows every error. A failed insert produces no log and no signal.

## Removed path

```
WS "reaction_removed"
 └─ handleWebSocketEvent            event.ts:166
     └─ handleReactionRemovedFromPostEvent   reactions.ts:39
         ├─ JSON.parse(msg.data.reaction)
         ├─ queryReaction(database, emoji_name, post_id, user_id).fetch()   queries/servers/reaction.ts:12
         └─ if found: database.write(() => reaction[0].destroyPermanently())
```

- It does **not** call `handleReactions`, `sanitizeReactions`, or any transformer. The `skipSync` and `prepareRecordsOnly` flags do not apply at all, so nothing is written as a batch.
- It matches on the same three fields that identify a reaction: `emoji_name`, `post_id`, and `user_id`. If no row matches, nothing happens.
- It has the same empty `catch {}` as the add path.

## Comparison

| | reaction_added | reaction_removed |
|---|---|---|
| Entry point | `handleReactionAddedToPostEvent` | `handleReactionRemovedFromPostEvent` |
| Goes through operator | yes, `handleReactions` | no, uses `database` directly |
| `skipSync` | `true` (no deletions) | not applicable |
| `prepareRecordsOnly` | `false` (writes immediately) | not applicable |
| Write | `batchRecords` → `writer.batch` | `database.write` → `destroyPermanently()` |
| Idempotent | yes (existing row skipped) | yes (no row, no-op) |

For contrast, the full-sync path (`post.ts:564`) calls `handleReactions` without `skipSync`. There, rows missing from the server's list are deleted through `prepareDestroyPermanently`. That is the behavior the websocket handlers avoid by setting the flag or by bypassing the operator.

I did not run the tests. The existing unit tests for both handlers are in `app/actions/websocket/reactions.test.ts`.