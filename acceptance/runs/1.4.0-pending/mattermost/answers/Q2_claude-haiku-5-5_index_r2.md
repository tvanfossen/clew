## Short answer

Both events enter the same switch in `handleWebSocketEvent` but then take different paths. "Added" goes through the server data operator's `handleReactions` with `skipSync: true`, which diffs against existing rows and inserts only what is missing. "Removed" bypasses the operator entirely: it looks up the row and calls `destroyPermanently()`. The `skipSync` flag exists only on the add path, and it is the reason the add path cannot delete anything.

## Added path

```
WS frame (type "reaction_added", data.reaction = JSON string)
  │
  ▼
handleWebSocketEvent            app/actions/websocket/event.ts:163
  case REACTION_ADDED
  │
  ▼
handleReactionAddedToPostEvent  app/actions/websocket/reactions.ts:21
  getServerDatabaseAndOperator(serverUrl)
  reaction = JSON.parse(msg.data.reaction)
  operator.handleReactions({
     prepareRecordsOnly: false,
     skipSync: true,
     postsReactions: [{post_id, reactions:[reaction]}] })
  │
  ▼
ServerDataOperatorBase.handleReactions  handlers/index.ts:124
  for each post:
    sanitizeReactions({database, post_id, rawReactions, skipSync})
        │   utils/reaction.ts:22
        │   load all Reaction rows where post_id = X
        │   map key "userId-emojiName"
        │   raw already present → similarObjects   (skipped)
        │   raw absent         → createReactions   (queued)
        │   skipSync? → return {createReactions, deleteReactions: []}   ← early return
  if createReactions → prepareRecords(transformReactionRecord, CREATE)
        │   transformers/reaction.ts:19
        │   id = raw.id (server's reaction id)
        │   set userId, postId, emojiName, createAt
        │   prepareBaseRecord → collections.get(REACTION).prepareCreate
  if prepareRecordsOnly → return (not taken)
  batchRecords(batchRecords)   base_data_operator/index.ts:191
        database.write(writer => writer.batch(...))  ← the actual DB write
```

The write is one `database.write` batch. Errors are swallowed twice: `batchRecords` logs a warning by default and does not rethrow, and the outer `handleReactionAddedToPostEvent` has an empty `catch {}`.

## Removed path

```
WS frame (type "reaction_removed")
  │
  ▼
handleWebSocketEvent            event.ts:166
  │
  ▼
handleReactionRemovedFromPostEvent   reactions.ts:39
  database = getServerDatabaseAndOperator(serverUrl).database
  msgReaction = JSON.parse(msg.data.reaction)
  rows = queryReaction(database, emoji_name, post_id, user_id).fetch()
        │   queries/servers/reaction.ts:12  (three Q.where clauses)
  if rows.length:
     database.write(() => rows[0].destroyPermanently())
  (empty catch)
```

It does not use `handleReactions`, `sanitizeReactions`, the transformer, or `batchRecords`. There is no `skipSync` or `prepareRecordsOnly` on this path, and the `reaction` payload is used only for its identifying fields.

## Flags and what they change

| Flag | Where | Effect |
|---|---|---|
| `skipSync: true` | Add path only | `sanitizeReactions` returns `deleteReactions: []` before computing deletions. The handler also skips the stale-delete branch (`if (deleteReactions?.length && !skipSync)`). Result: the event can only create. It cannot remove reactions by other users that the local DB still has. |
| `prepareRecordsOnly: false` | Add path only | The batch is written to the DB inside `handleReactions`. With `true` it would return the prepared models for the caller to batch. |
| `skipSync` (implicit, i.e. false) | Full sync from `handlePosts` | Not on the WS path. A full post sync would also prepare deletes for reactions missing from the payload. |

Because `sanitizeReactions` only ever produces `createReactions` here, the reaction table never sees `UPDATE` operations from this path. A duplicate add is a no-op because the existing row is found in the map.

## Things I noticed

- The removal path matches on `(emoji_name, post_id, user_id)`, not on the server id. A stored row whose emoji or user differs in case or form would not match. I did not verify that the server always sends consistent values.
- Both handlers swallow errors with an empty `catch`. That conflicts with the repo's CLAUDE.md rule against silently ignoring errors. A failed add or remove leaves no log.
- In `handleReactions`, the `!skipSync` guard on the delete branch is redundant, because `sanitizeReactions` already returns an empty `deleteReactions` when `skipSync` is set. It is harmless.

I did not run the existing tests (`app/actions/websocket/reactions.test.ts`, `event.test.ts`), so the behavior above is from reading the source.