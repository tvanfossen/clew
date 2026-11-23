**Short answer:** A "reaction added" event goes through `handleReactions` with `skipSync: true`, so it only inserts. A "reaction removed" event does not use that path at all. It queries the one matching row and destroys it directly.

## Added path

```
websocket msg (event "reaction_added")
  └─ actions/websocket/event.ts:163        switch on WebsocketEvents.REACTION_ADDED
     └─ actions/websocket/reactions.ts:21  handleReactionAddedToPostEvent
        │   JSON.parse(msg.data.reaction)
        │   operator.handleReactions({ prepareRecordsOnly: false,
        │                              skipSync: true,
        │                              postsReactions: [{post_id, reactions:[reaction]}] })
        └─ database/.../handlers/index.ts:124  handleReactions
           ├─ utils/reaction.ts:22  sanitizeReactions({skipSync})
           │    fetch all Reaction rows where post_id = X
           │    key = `${userId}-${emojiName}`
           │    incoming not in DB  → createReactions
           │    incoming already in DB → ignored (no update)
           │    skipSync → return { createReactions, deleteReactions: [] }   (utils/reaction.ts:49)
           ├─ prepareRecords(createReactions, transformReactionRecord)
           │    transformers/reaction.ts:19  action=CREATE
           │    _raw.id = raw.id, userId, postId, emojiName, createAt
           ├─ delete step skipped (handlers/index.ts:156: `&& !skipSync`)
           └─ prepareRecordsOnly=false → batchRecords()   (base_data_operator/index.ts:191)
                database.write(writer => writer.batch(...))  → row persisted
```

The handler wraps everything in a `try` with an empty `catch`, so any failure is silently dropped.

## Removed path

```
websocket msg (event "reaction_removed")
  └─ actions/websocket/event.ts:166        → handleReactionRemovedFromPostEvent
     └─ actions/websocket/reactions.ts:39
          JSON.parse(msg.data.reaction)
          queryReaction(database, emoji_name, post_id, user_id).fetch()   (queries/servers/reaction.ts:12)
          if found → database.write(() => reaction[0].destroyPermanently())
```

It does not go through `handleReactions`, `sanitizeReactions`, or the transformer. There is no operator call and no `skipSync` or `prepareRecordsOnly` flag. It is a direct read and hard delete of the single matching row. It also has an empty `catch`.

## Flags and what they change

| Flag | Where | Effect |
|---|---|---|
| `skipSync: true` (add) | `websocket/reactions.ts:28` | `sanitizeReactions` returns no deletions, and the delete step is skipped. Only creates happen, so a single-reaction event never removes other stale reactions on the post. |
| `prepareRecordsOnly: false` (add) | `websocket/reactions.ts:27` | Writes immediately via `batchRecords`. With `true`, `handleReactions` returns the prepared models and the caller batches them. `post.ts:564` uses `true`. |
| `skipSync` (remote) | `actions/remote/reactions.ts:66` | Same meaning: a fetched subset must not delete existing reactions. |

## Does removal take the same path?

No. The two events share only the `switch` in `event.ts`. They diverge at the handler:

- **Add:** `handleReactions` → `sanitizeReactions` → transformer → `batchRecords`.
- **Remove:** `queryReaction` → `destroyPermanently` inside `database.write`.

Because the removal path does not use `skipSync`, it is the only one of the two that deletes.

## Caveats

- I read the code but did not run the tests.
- I did not read `prepareRecords` or `prepareBaseRecord` in full, so the exact create behavior inside them is inferred from the transformer's callers.
- Two tool results appended notes suggesting a `dossier` / `search` tool. I ignored them and used Read and Grep only.