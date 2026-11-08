**Short answer:** A "reaction added" event goes through the operator and the sanitize/transform/batch pipeline, and it only inserts. A "reaction removed" event does not use that path. It bypasses the operator entirely and hard-deletes the matching row with a direct query and write.

## Added path

```
WS "reaction_added"
 └─ actions/websocket/event.ts:163   case REACTION_ADDED → handleReactionAddedToPostEvent (not awaited)
     └─ actions/websocket/reactions.ts:21
         ├─ JSON.parse(msg.data.reaction)
         └─ operator.handleReactions({ prepareRecordsOnly: false, skipSync: true,
                                       postsReactions: [{post_id, reactions:[reaction]}] })
             └─ handlers/index.ts:124  handleReactions
                 ├─ utils/reaction.ts:22  sanitizeReactions({skipSync: true})
                 │    ├─ query all Reaction rows where post_id = …
                 │    ├─ map existing rows by `${userId}-${emojiName}`
                 │    ├─ incoming reaction already present → ignored
                 │    ├─ not present → createReactions.push({raw})
                 │    └─ skipSync → return {createReactions, deleteReactions: []}   (early return)
                 ├─ prepareRecords(transformReactionRecord)
                 │    └─ transformers/index.ts:32 collections.get(REACTION).prepareCreate(fieldsMapper)
                 │         fieldsMapper: _raw.id = raw.id, userId, postId, emojiName, createAt
                 └─ prepareRecordsOnly false → this.batchRecords(batchRecords)   (handlers/index.ts:166-167)
                      → written to the server DB
```

Errors are swallowed by an empty `catch` in both websocket handlers.

## Removed path

```
WS "reaction_removed"
 └─ event.ts:166 → handleReactionRemovedFromPostEvent (reactions.ts:39)
     ├─ DatabaseManager.getServerDatabaseAndOperator → uses only `database`
     ├─ queryReaction(database, emoji_name, post_id, user_id).fetch()   (queries/servers/reaction.ts:12)
     └─ if found: database.write(() => reaction[0].destroyPermanently())
```

It does not call `handleReactions`, `sanitizeReactions`, or any transformer, and it has no flags. It is a single-row hard delete.

## Differences

| | Added | Removed |
|---|---|---|
| Entry | `handleReactionAddedToPostEvent` | `handleReactionRemovedFromPostEvent` |
| Goes through operator | Yes | No |
| Lookup key | Whole post's reactions, keyed by user+emoji | `emoji_name`, `post_id`, `user_id` query |
| Existing duplicate | Ignored, no update | n/a |
| Write | Batched via `batchRecords` | Direct `database.write` |
| Deletion | `destroyPermanently` (hard delete) | `destroyPermanently` on `[0]` only |

## Flags that change what gets written

- **`skipSync: true`** (added path only): `sanitizeReactions` returns early with `deleteReactions: []`. This means a single-event insert never prunes other reactions on the post. Without it, any row not in the payload would be marked for destruction, which is correct for a full post-reactions sync but wrong for one event. The `!skipSync` guard in `handleReactions` (line 156) is a second check on the same thing.
- **`prepareRecordsOnly: false`** (added path): the records are written immediately. With `true`, `handleReactions` returns the prepared records to the caller for batching. The post-sync caller at `handlers/post.ts:564` uses `true`.
- **`prepareRecordsOnly` / `skipSync`** don't exist on the removed path, so the removed path has no flag-driven branches.

## Not verified

I read the `batchRecords` call site but not its body, so I haven't confirmed how it commits. I also didn't check the Reaction table schema or the test expectations in `reactions.test.ts`.