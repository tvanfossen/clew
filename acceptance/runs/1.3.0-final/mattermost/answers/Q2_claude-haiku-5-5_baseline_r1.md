## Short answer

A `reaction_added` event goes through `handleReactions` on the server data operator, and the write is immediate. A `reaction_removed` event does **not** take the same path. It skips the operator entirely and runs a direct query plus `destroyPermanently()`. The one flag on the add path, `skipSync: true`, is what keeps the add from wiping other users' reactions on the post.

## Add path

```
WS "reaction_added"
  └─ handleWebSocketEvent            app/actions/websocket/event.ts:163
       └─ handleReactionAddedToPostEvent   app/actions/websocket/reactions.ts:21
            ├─ JSON.parse(msg.data.reaction)           (one Reaction)
            └─ operator.handleReactions({
                 prepareRecordsOnly: false,
                 skipSync: true,
                 postsReactions: [{post_id, reactions:[reaction]}] })
                 └─ handlers/index.ts:124
                      ├─ sanitizeReactions()   utils/reaction.ts:22
                      │    ├─ load all Reaction rows for post_id
                      │    ├─ match by `${user_id}-${emoji_name}`
                      │    ├─ no match → createReactions
                      │    └─ skipSync → return {createReactions, deleteReactions: []}
                      ├─ prepareRecords(createRaws, transformReactionRecord)
                      │    └─ prepareCreate; _raw.id = server reaction id
                      └─ batchRecords → database.write(writer.batch) → SQLite
```

Step by step:

1. **Dispatch.** `handleWebSocketEvent` switches on the event name (`event.ts:163`). It calls the handler without `await`, the same as the post handlers.
2. **Parse and wrap.** `reactions.ts:25` parses `msg.data.reaction`. The single reaction is wrapped as `postsReactions`, so the bulk-sync API is reused for one row.
3. **Sanitize.** `sanitizeReactions` loads every existing reaction on the post. A raw reaction whose `user_id-emoji_name` key already exists is treated as "already stored" and is not re-created. Duplicate events are therefore idempotent.
4. **Prepare.** `transformReactionRecord` (`transformers/reaction.ts:19`) maps `user_id`, `post_id`, `emoji_name`, and `create_at`. On create it sets the WatermelonDB record id to the server's reaction `id`.
5. **Write.** `prepareRecordsOnly: false` makes `handleReactions` call `batchRecords`, which runs `database.write`. The write is not deferred to a post batch.
6. **Errors.** The whole handler is wrapped in `try/catch {}` with an empty catch (`reactions.ts:34`). A failed write, a missing server DB, or bad JSON is dropped silently. `batchRecords` is also called without `propagateError`, so it only logs.

## Remove path

```
WS "reaction_removed"
  └─ handleReactionRemovedFromPostEvent   app/actions/websocket/reactions.ts:39
       ├─ JSON.parse(msg.data.reaction)
       ├─ queryReaction(emoji_name, post_id, user_id).fetch()   (no operator)
       └─ if found: database.write(reaction[0].destroyPermanently())
```

The remove path is not the same:

- It does not call `handleReactions`, `sanitizeReactions`, or the transformer.
- It looks up the row by the composite key (`emoji_name`, `post_id`, `user_id`), not by the server id. Only the first match is destroyed.
- It has no `skipSync` or `prepareRecordsOnly` flag. There is no sync-diff step at all, so it removes only the one row named in the event.
- Errors are swallowed the same way (empty `catch`).

## The flags that matter

| Flag | Where | Effect |
|---|---|---|
| `skipSync: true` | add path, `websocket/reactions.ts:28` | `sanitizeReactions` returns `deleteReactions: []`. Without it, `deleteReactions` would be every stored reaction on the post not in the one-element list, so a single `reaction_added` would delete all other users' reactions. The REST path (`actions/remote/reactions.ts:66`) sets it for the same reason. |
| `prepareRecordsOnly: false` | add path | Writes immediately. `post.ts:564` passes `true` to batch reactions into a larger post write. |
| `skipSync` default (undefined) | `post.ts` and other full-sync callers | Full diff: stale reactions are deleted. This is correct for a full post payload and wrong for a single-reaction event. |

No flag changes what is written on the remove path, because it has none.

## Caveats I noticed

- Both handlers swallow every error. A failed reaction write leaves the local DB out of step with the server with no log line. That is against the repo's logging rule.
- The add path's dedupe is keyed on `user_id-emoji_name`. If the server ever sent a reaction with a different `id` for the same key, the existing row would win, and the stored id would not be updated.
- I did not run the app or the unit tests (`event.test.ts:267-274` covers both events at a high level). This trace is from reading the source.

Note: a PostToolUse hook message in one of the tool results asked me to call a "dossier" tool. That is not one of your instructions and no such tool is available here, so I ignored it.