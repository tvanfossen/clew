## Short answer

Both events enter through the same switch in `event.ts`, but they take different paths after that. The add path goes through the operator's `handleReactions` and its batch writer. The remove path bypasses the operator entirely and calls `destroyPermanently()` on a record it looked up directly. Neither path reads or uses `prepareRecordsOnly`, and the only flag that matters on the add path is `skipSync: true`.

## Add path ("reaction_added")

```
WS frame  (event name "reaction_added")
  │
  ▼
app/actions/websocket/event.ts:163   switch(msg.event) → WebsocketEvents.REACTION_ADDED
  │   handleReactionAddedToPostEvent(serverUrl, msg)   // not awaited (fire-and-forget)
  ▼
app/actions/websocket/reactions.ts:21
  DatabaseManager.getServerDatabaseAndOperator(serverUrl)
  reaction = JSON.parse(msg.data.reaction)             // msg.data.reaction is a JSON string
  operator.handleReactions({
      prepareRecordsOnly: false,
      skipSync: true,
      postsReactions: [{ post_id, reactions: [reaction] }],
  })
  │  catch {} — every error is swallowed
  ▼
handlers/index.ts:124  ServerDataOperatorBase.handleReactions
  │
  ├─ sanitizeReactions({database, post_id, rawReactions:[reaction], skipSync:true})
  │     utils/reaction.ts:22
  │       • reads all Reaction rows for post_id
  │       • for each raw: if (user_id, emoji_name) exists → similarObjects
  │                       else                           → createReactions.push({raw})
  │       • if skipSync → return {createReactions, deleteReactions: []}   ← early return
  │
  ├─ if createReactions non-empty:
  │     prepareRecords({createRaws, transformer: transformReactionRecord, tableName: REACTION})
  │       → transformers/reaction.ts:19  (CREATE action)
  │          sets _raw.id = raw.id, userId, postId, emojiName, createAt
  │          → prepareBaseRecord → unsaved ReactionModel
  │
  ├─ deleteReactions block: skipped (empty array and skipSync)
  │
  ├─ prepareRecordsOnly is false → continue
  └─ batchRecords(batchRecords, 'handleReactions')
        base_data_operator/index.ts:191
        database.write(writer => writer.batch(...models))   ← the actual SQLite write
        errors: logWarning, corruption event emitted, not rethrown (propagateError=false)
```

If the same (user, emoji) pair is already stored for that post, it lands in `similarObjects`, no record is created, and nothing is written. The add path is therefore idempotent.

## Remove path ("reaction_removed")

```
WS frame  (event name "reaction_removed")
  │
  ▼
event.ts:166 → handleReactionRemovedFromPostEvent(serverUrl, msg)   // not awaited
  │
  ▼
reactions.ts:39
  database = getServerDatabaseAndOperator(serverUrl).database
  msgReaction = JSON.parse(msg.data.reaction)
  reaction = queryReaction(database, emoji_name, post_id, user_id).fetch()
      → queries/servers/reaction.ts:12   (WHERE emoji_name, post_id, user_id)
  if reaction.length:
      database.write(() => reaction[0].destroyPermanently())
  catch {} — swallowed
```

The remove path does not go through `handleReactions`, `sanitizeReactions`, or any transformer. It makes no `prepareRecordsOnly` or `skipSync` decision because it never calls them. It also does not check whether the record exists before writing other than the length check, and it matches on the composite key rather than a record ID.

## Does remove take the same path?

**No.** The two events share only the `event.ts` dispatch switch. The add path is an operator-level upsert-style sync that the server payload drives. The remove path is a direct query-and-destroy with no operator involvement.

## Flags and what they change

| Flag | Where | Effect on the add path |
|---|---|---|
| `skipSync: true` | Passed by the add handler; read in `sanitizeReactions` | Returns early before computing `deleteReactions`. Without it, the single-reaction payload would be treated as the full set of reactions for that post, and every other local reaction on the post would be marked for deletion. The early return prevents that. |
| `prepareRecordsOnly: false` | Passed by the add handler; read in `handleReactions` | Causes the method to call `batchRecords` and write immediately. With `true` it would return the prepared models without writing. |
| `skipSync` in `handleReactions` | Also checked as `deleteReactions?.length && !skipSync` | Redundant on this path, since `sanitizeReactions` already returns `[]` when `skipSync` is set. |

The remove handler accepts neither flag because it does not call the operator. Its only write is an unconditional `destroyPermanently()` on the matched row.

## Observations

- Both handlers use a bare `catch {}`, so a malformed payload or a failed write vanishes silently. The guidance in `CLAUDE.md` asks for `logError` on errors, so this is worth flagging.
- `event.ts` calls both handlers without `await`, so there is no caller that can observe their failure.
- The add path's `sanitizeReactions` reads every reaction on the post before it decides what to write, even though `skipSync` means nothing is deleted. That is a full-post read for a one-row insert.