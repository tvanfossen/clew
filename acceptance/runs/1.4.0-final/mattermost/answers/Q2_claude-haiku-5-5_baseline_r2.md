## Short answer

A "reaction added" event is written through the server operator's `handleReactions` handler, with `skipSync: true` so that it never deletes other reactions. A "reaction removed" event does **not** take that path. It goes straight to the database, finds the matching row, and calls `destroyPermanently()` in its own write transaction. The two only share the entry switch in `handleWebSocketEvent`.

## Added path

```
WebSocket (client.setEventCallback)          websocket_manager.ts:112
  -> handleWebSocketEvent(serverUrl, msg)    actions/websocket/event.ts:44
     case REACTION_ADDED                     event.ts:163-165  (not awaited)
  -> handleReactionAddedToPostEvent          actions/websocket/reactions.ts:21
       JSON.parse(msg.data.reaction)
       operator.handleReactions({
         prepareRecordsOnly: false,
         skipSync: true,
         postsReactions: [{post_id, reactions:[reaction]}] })
  -> handleReactions                         server_data_operator/handlers/index.ts:124
       sanitizeReactions({skipSync})         operator/utils/reaction.ts:22
         - loads all Reaction rows for post_id
         - map key `${userId}-${emojiName}`
         - incoming reaction already present -> skipped (no-op)
         - otherwise -> createReactions.push({raw})
         - if skipSync -> return {createReactions, deleteReactions: []}
       prepareRecords(CREATE)                base_data_operator/index.ts:134
         -> transformReactionRecord            transformers/reaction.ts:19
            -> prepareBaseRecord (CREATE)      transformers/index.ts:20-33
               -> collection.prepareCreate(fieldsMapper)
                  sets _raw.id, userId, postId, emojiName, createAt
       prepareRecordsOnly is false -> batchRecords   base_data_operator/index.ts:191
         -> database.write(writer => writer.batch(...))   <- persisted here
```

The whole chain sits in `try/catch` blocks that swallow every error (`reactions.ts:34-36`). A malformed payload or a DB failure is silent. The repo's CLAUDE.md asks for errors to be logged, so this is worth noting.

## Flags that change what gets written

**`skipSync: true`** (`reactions.ts:28`) is the important one. In `sanitizeReactions`, the early return at `utils/reaction.ts:49-51` happens before the deletion set is computed. Without the flag, the handler would treat the one-reaction payload as the complete reaction list for the post and destroy every other reaction on it. The flag is there because the event carries only one reaction.

**`prepareRecordsOnly: false`** makes `handleReactions` batch the writes itself. The remote `addReaction` in `actions/remote/reactions.ts:60-75` passes `true` so it can combine the reaction with a recent-emoji write into one batch.

**Dedupe on `userId-emojiName`** means a reaction that already exists for that user and emoji is not recreated. Redelivered or duplicate add events are therefore idempotent. The stored `id` comes from `raw.id` on create.

## Removed path

```
reaction_removed -> event.ts:166-167
  -> handleReactionRemovedFromPostEvent     actions/websocket/reactions.ts:39
       database.get(REACTION)
         .query(emoji_name, post_id, user_id)   queries/servers/reaction.ts:12
       if found:
         database.write(() => reaction[0].destroyPermanently())
```

It does not use the operator, `handleReactions`, `sanitizeReactions`, the transformer, `skipSync` or `prepareRecordsOnly`. The removal is a direct delete of the first matching row. It bypasses `batchRecords`, so the corruption-detection hook there does not run. Failures are swallowed by the empty catch at `reactions.ts:51-53`.

## Things to check

- If duplicate rows for the same user, post and emoji ever existed, removal would delete only `reaction[0]`.
- The add path relies on `skipSync` to avoid mass deletion. Any future caller that passes a partial reaction list without that flag would delete reactions it never saw.

I had no tool for the relevant code lookups, and two hook messages in the tool results suggested a `dossier`/`search` tool I don't have. I ignored them and worked from Read and Grep. I did not run the test suite.