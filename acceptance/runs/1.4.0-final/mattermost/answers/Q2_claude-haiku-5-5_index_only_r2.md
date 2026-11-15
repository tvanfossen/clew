**Short answer:** Both events are handled in `app/actions/websocket/`, but they take different paths into the database. "Added" goes through the shared sync handler with `skipSync: true`. "Removed" bypasses that handler and deletes one row directly. Neither path uses `prepareRecordsOnly`.

## Reaction added

```
WS frame (event = REACTION_ADDED)
  └─ handleWebSocketEvent            app/actions/websocket/event.ts:44
       case REACTION_ADDED
  └─ handleReactionAddedToPostEvent  app/actions/websocket/reactions.ts:21
       1. DatabaseManager.getServerDatabaseAndOperator(serverUrl)
       2. JSON.parse(msg.data.reaction)   → Reaction
       3. operator.handleReactions({ prepareRecordsOnly: false,
                                     skipSync: true,
                                     postsReactions: [{post_id, reactions:[reaction]}] })
  └─ ServerDataOperatorBase.handleReactions   handlers/index.ts:124
       4. sanitizeReactions({database, post_id, rawReactions, skipSync})
            utils/reaction.ts:22
            - loads all Reaction rows for post_id
            - keys them by `${userId}-${emojiName}`
            - raw reaction already present  → skipped (no-op)
            - raw reaction absent           → createReactions.push({raw})
            - skipSync → returns deleteReactions: []
       5. prepareRecords({createRaws, transformer: transformReactionRecord, tableName: REACTION})
            server_data_operator/transformers/reaction.ts:19
            - sets _raw.id from server id (create)
            - sets userId, postId, emojiName, createAt
            - prepareBaseRecord builds the model
       6. batchRecords(batchRecords)  → one write to the server DB
```

Errors in the add handler are swallowed by an empty `catch {}`. A malformed payload or a DB failure therefore leaves no trace in the logs at this layer.

## Reaction removed

```
WS frame (event = REACTION_REMOVED)
  └─ handleWebSocketEvent → handleReactionRemovedFromPostEvent   reactions.ts:39
       1. getServerDatabaseAndOperator → uses only `database`
       2. JSON.parse(msg.data.reaction)
       3. queryReaction(database, emoji_name, post_id, user_id).fetch()
            queries/servers/reaction.ts:12
       4. if found: database.write(() => reaction[0].destroyPermanently())
          if not found: nothing happens
       (catch {} again swallows errors)
```

It does not use `handleReactions`, `sanitizeReactions`, or any transformer. The row is matched by the composite key (emoji, post, user) and hard-deleted.

## Does removal take the same path?

No. The only shared pieces are the top-level dispatcher and the JSON parse.

| | Added | Removed |
|---|---|---|
| Entry | `handleReactionAddedToPostEvent` | `handleReactionRemovedFromPostEvent` |
| Goes through `handleReactions` | yes | no |
| Lookup | full post scan in `sanitizeReactions` | `queryReaction` by emoji+post+user |
| Write | `batchRecords` (create) | `destroyPermanently()` in `database.write` |
| `prepareRecordsOnly` | `false` | n/a |
| `skipSync` | `true` | n/a |

## Flags that change what gets written

- **`skipSync: true` (add path).** Inside `sanitizeReactions`, `skipSync` returns early with `deleteReactions: []`. Inside `handleReactions`, the delete branch is also guarded by `!skipSync`. The event therefore only creates. It never prunes reactions that the server no longer reports for that post. A full sync would prune, but a single-event update must not, because the event carries only one reaction.
- **Duplicate suppression (add path).** The map keyed on `userId-emojiName` means a reaction that already exists locally is not created again. The event is effectively idempotent.
- **`prepareRecordsOnly: false` (add path).** Records are written immediately. With `true`, `handleReactions` would return the prepared models without writing them, which callers that batch several operations use.

## Caveats

- The index does not resolve the call from `handleReactionAddedToPostEvent` into `operator.handleReactions`, so its callee list is empty. I confirmed the target from the handler body and the `handleReactions` signature.
- I did not trace the remote `addReaction`/`removeReaction` actions. Those are the optimistic local path the user triggers, not the websocket path.