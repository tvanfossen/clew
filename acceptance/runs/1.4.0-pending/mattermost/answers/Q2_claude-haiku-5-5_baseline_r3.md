## Reaction added: websocket event to database row

```
ws "reaction_added"
 └─ handleWebSocketEvent            app/actions/websocket/event.ts:163
     └─ handleReactionAddedToPostEvent   websocket/reactions.ts:21
         ├─ JSON.parse(msg.data.reaction)           (payload is a JSON string)
         └─ operator.handleReactions({ prepareRecordsOnly: false,
                                       skipSync: true,
                                       postsReactions: [{post_id, reactions:[reaction]}] })
             handlers/index.ts:124
             ├─ sanitizeReactions()              operator/utils/reaction.ts:22
             │   ├─ load all Reaction rows for post_id
             │   ├─ map keyed by `${userId}-${emojiName}`
             │   ├─ incoming reaction already present → no-op
             │   ├─ otherwise → createReactions.push({raw})
             │   └─ skipSync → return { createReactions, deleteReactions: [] }
             ├─ prepareRecords(transformReactionRecord)  transformers/reaction.ts:19
             │   └─ sets id, userId, postId, emojiName, createAt
             └─ batchRecords()                   (write; body not opened)
```

Notes on the add path:

- **`skipSync: true`** is the flag that matters most. Without it, `deleteReactions` would be every stored reaction on that post that is not in the payload. The payload only carries the one new reaction, so every other reaction on the post would be destroyed. The flag turns off the diff-and-delete step (`handlers/index.ts:156`) and makes this a create-only path.
- **`prepareRecordsOnly: false`** means the records are written inside the handler. Callers that batch with other work pass `true` instead, for example `handlers/post.ts:564`.
- **Duplicates are not rewritten.** If the same user and emoji already exist on the post, the existing row is kept as is, including its old `id`.
- **Errors are swallowed.** The whole body is in a `try/catch` with an empty catch (`reactions.ts:34`), and the dispatcher does not await the promise (`event.ts:164`). A failure leaves no log.

## Reaction removed: same path?

No. It shares the entry point and differs after that.

```
ws "reaction_removed"
 └─ handleWebSocketEvent            event.ts:166
     └─ handleReactionRemovedFromPostEvent   websocket/reactions.ts:39
         ├─ JSON.parse(msg.data.reaction)
         ├─ queryReaction(emoji_name, post_id, user_id).fetch()   queries/servers/reaction.ts:12
         └─ if found → database.write → reaction[0].destroyPermanently()
```

- It does not go through the operator. There is no `sanitizeReactions`, no `handleReactions`, no transformer and no `batchRecords`. It talks to `database` directly.
- It is a hard delete (`destroyPermanently`), not a soft delete.
- It matches on the natural key (emoji, post, user) rather than the server `id`. If that key matches nothing, nothing happens.
- It has no flags. `skipSync` is irrelevant here because the operator is not involved.
- It also swallows errors silently.

I did not trace the caller of `handleWebSocketEvent` in the socket layer, and I did not read the body of `batchRecords`. Both are outside what I checked.