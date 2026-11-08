**Short answer:** A "reaction added" event does not take the same path as "reaction removed" after the switch. Added goes through the server data operator and a diff-and-batch write. Removed queries the row directly and destroys it. Both are dispatched from one `switch`, and both swallow errors silently.

## Added path

```
WS "reaction_added"
 └─ handleWebSocketEvent (app/actions/websocket/event.ts:163)
     case WebsocketEvents.REACTION_ADDED → handleReactionAddedToPostEvent(serverUrl, msg)
         └─ app/actions/websocket/reactions.ts:21
            1. DatabaseManager.getServerDatabaseAndOperator(serverUrl)
            2. reaction = JSON.parse(msg.data.reaction)
            3. operator.handleReactions({
                 prepareRecordsOnly: false,
                 skipSync: true,
                 postsReactions: [{post_id, reactions: [reaction]}] })
               └─ ServerDataOperatorBase.handleReactions  (handlers/index.ts:124)
                  a. sanitizeReactions({database, post_id, rawReactions, skipSync})
                       utils/reaction.ts:22
                       - loads existing Reaction rows for post_id
                       - keys them by `${userId}-${emojiName}`
                       - raw already present → skip; absent → createReactions.push
                       - skipSync === true → return {createReactions, deleteReactions: []} early
                  b. createReactions → prepareRecords({createRaws, transformer: transformReactionRecord, tableName: REACTION})
                       transformers/reaction.ts:19
                       - CREATE: _raw.id = raw.id (server-assigned), userId, postId, emojiName, createAt
                  c. deleteReactions block is skipped (`&& !skipSync`)
                  d. prepareRecordsOnly is false → batchRecords(batchRecords, 'handleReactions')
                       base_data_operator/index.ts:191
                       - database.write(writer => writer.batch(...))
                       - on error: logWarning + corruption event, not rethrown (propagateError defaults false)
 └─ catch {} — any exception is swallowed silently
```

**Result:** one `Reaction` row is inserted in the server DB, unless an identical user+emoji row for that post already exists. A duplicate event is therefore a no-op.

## Removed path

```
WS "reaction_removed"
 └─ handleWebSocketEvent → handleReactionRemovedFromPostEvent (reactions.ts:39)
     1. database = DatabaseManager...(serverUrl)   (no operator)
     2. msgReaction = JSON.parse(msg.data.reaction)
     3. queryReaction(database, emoji_name, post_id, user_id).fetch()   queries/servers/reaction.ts:12
     4. if found: database.write(() => reaction[0].destroyPermanently())
     └─ catch {} — silent
```

It does not use `handleReactions`, `sanitizeReactions`, or any flag. If no row matches, it does nothing.

## Flags and what they change

| Flag | Where | Effect |
|---|---|---|
| `skipSync: true` | added handler | `sanitizeReactions` returns before computing deletions. Without it, the diff would treat every other stored reaction on the post as stale, because the payload carries only the one new reaction. The handler would destroy them. This is the most important flag. |
| `skipSync` (in the `!skipSync` guard) | `handleReactions` | Also gates the `deleteReactions` branch. It is off by default in the bulk post-sync caller, which is where full-state reconciliation happens. |
| `prepareRecordsOnly: false` | added handler | Writes immediately via `batchRecords`. With `true`, the handler would return the prepared models for the caller to batch into a larger transaction. |

I could not confirm all of `handleReactions`' callers. The index shows one resolved caller, `PostHandler.handlePosts`, with 8 unresolved. The bulk path with `skipSync` unset is the one that deletes stale reactions.

## Caveats

- Both websocket handlers wrap their work in `try { … } catch { // Do nothing }`. A failed add or remove is invisible in logs, which conflicts with the repo's logging rules. This is worth flagging.
- `batchRecords` logs failures but does not rethrow them, so a failed write also never reaches the handler's catch.