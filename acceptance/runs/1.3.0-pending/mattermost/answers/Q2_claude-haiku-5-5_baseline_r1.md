## Short answer

A `reaction_added` event is written to the local DB through the shared `handleReactions` operator handler, called with `skipSync: true`. A `reaction_removed` event does not use that handler. It queries the matching row and calls `destroyPermanently()` directly. The two paths share no write code.

## Added path

```
WebSocket "reaction_added"
  └─ app/actions/websocket/event.ts:163-165   switch on WebsocketEvents.REACTION_ADDED
       └─ reactions.ts:21  handleReactionAddedToPostEvent(serverUrl, msg)
            ├─ JSON.parse(msg.data.reaction)            → Reaction
            └─ operator.handleReactions({
                 prepareRecordsOnly: false,
                 skipSync: true,
                 postsReactions: [{post_id, reactions: [reaction]}] })
                 └─ handlers/index.ts:124  handleReactions
                      └─ utils/reaction.ts:22  sanitizeReactions({skipSync: true})
                           • load all Reaction rows where post_id = X
                           • for the incoming reaction: if (user_id, emoji_name) exists → skip
                                                       else → createReactions.push({raw})
                           • skipSync → return {createReactions, deleteReactions: []}
                      └─ transformers/reaction.ts:19  transformReactionRecord (CREATE)
                           • id = raw.id, userId, postId, emojiName, createAt
                           • prepareBaseRecord → prepareCreate model
                      └─ handlers/index.ts:162  prepareRecordsOnly is false → skip early return
                      └─ handlers/index.ts:167  this.batchRecords → database.write(writer.batch(...))
                                                 → row inserted in the server DB
```

Errors are swallowed by the empty `catch` in `reactions.ts`. `event.ts` also calls the handler without `await` (line 164), so the switch returns before the write finishes.

## Removed path

```
WebSocket "reaction_removed"
  └─ event.ts:166-168   → handleReactionRemovedFromPostEvent
       └─ reactions.ts:39
            ├─ JSON.parse(msg.data.reaction)
            ├─ queryReaction(database, emoji_name, post_id, user_id).fetch()   [queries/servers/reaction.ts]
            └─ if found: database.write(() => reaction[0].destroyPermanently())
```

This path never calls `handleReactions`, `sanitizeReactions`, or `batchRecords`. It does not use `prepareRecordsOnly` or `skipSync`, so no flag changes what gets written. It always deletes the single matching row, or does nothing if no row matches.

## Flags and what they change

| Flag | Where | Effect |
|---|---|---|
| `skipSync: true` (add event) | `reactions.ts:28` | `sanitizeReactions` returns `deleteReactions: []`. Without it, every other stored reaction on that post that is missing from the one-item payload would be treated as stale and destroyed. |
| `prepareRecordsOnly: false` (add event) | `reactions.ts:27` | The handler writes immediately through `batchRecords`. With `true`, it would return prepared models for the caller to batch. |
| Existing-row check | `utils/reaction.ts:40` | Duplicate add events for the same user and emoji are ignored. The stored row is not updated. |
| `skipSync: true` (remote add) | `actions/remote/reactions.ts:60-63` | The user's own add call uses both `prepareRecordsOnly: true` and `skipSync: true`, then batches the models with the recent-emoji records. The websocket echo of the same reaction then finds the row already present and does nothing. |

The `skipSync` flag is only meaningful inside `handleReactions`. The removal path avoids the handler entirely, so it has no flags.

## Does removal take the same path?

No. It shares only the query helper, `queryReaction`, with the add path's remote caller. The differences:

- Add goes through `handleReactions`, `sanitizeReactions`, `transformReactionRecord`, and `batchRecords`.
- Remove does a direct `fetch` and `destroyPermanently` inside `database.write`, with no operator involvement.
- Remove matches on `(emoji_name, post_id, user_id)` from the message, not on the `id` field.

One caveat: `handleReactions` does have a delete branch (`handlers/index.ts:156`), but it only runs when `skipSync` is false. The websocket add path never reaches it, and the removal event never calls the handler. So the only place a removal runs through the operator is the full-sync path, which the websocket code does not use.

I did not run the tests. `app/actions/websocket/reactions.test.ts` covers both handlers and is the quickest way to confirm this behaviour.