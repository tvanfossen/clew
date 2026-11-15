**Short answer:** A "reaction added" event goes through the generic `handleReactions` operator, with `skipSync: true` so it never deletes other reactions. A "reaction removed" event does not use that operator at all. It queries the database directly and destroys the matching row. The two paths share only the websocket switch and the swallowed-error `try/catch` pattern.

## Added path

```
websocket_manager.ts:112  client.setEventCallback → handleWebSocketEvent(serverUrl, evt)
  │  (gated by isCurrentClient())
event.ts:163              case REACTION_ADDED → handleReactionAddedToPostEvent(serverUrl, msg)   [not awaited]
reactions.ts:21           JSON.parse(msg.data.reaction) → Reaction
                          operator.handleReactions({prepareRecordsOnly:false, skipSync:true,
                                                    postsReactions:[{post_id, reactions:[reaction]}]})
handlers/index.ts:124     handleReactions → sanitizeReactions(...)  per post
utils/reaction.ts:22      load all REACTION rows where post_id = X
                          map key "userId-emojiName"; if the incoming one exists → no-op
                          else createReactions.push({raw})
                          skipSync → return {createReactions, deleteReactions: []}   (line 49)
handlers/index.ts:146     prepareRecords(createRaws, transformReactionRecord)
transformers/reaction.ts:19  id = raw.id; userId, postId, emojiName, createAt set
handlers/index.ts:166     prepareRecordsOnly false → batchRecords()
base_data_operator:191    database.write(writer.batch(...))  → row stored in the server DB
```

An existing row with the same user and emoji is skipped, not updated. Adding the same reaction twice is therefore idempotent, and the stored row keeps its original `create_at`.

## Removed path

```
event.ts:166        case REACTION_REMOVED → handleReactionRemovedFromPostEvent(serverUrl, msg)
reactions.ts:39    JSON.parse(msg.data.reaction)
                   queryReaction(db, emoji_name, post_id, user_id).fetch()   (queries/servers/reaction.ts:12)
                   if length → database.write(() => reaction[0].destroyPermanently())
```

It does not call `handleReactions`, `sanitizeReactions`, `batchRecords`, or any transformer. It uses the same natural key as the add path (emoji, post, user). It also does not check the reaction `id`. If no row matches, it does nothing.

## Flags that change what gets written

| Flag | Where | Effect |
|---|---|---|
| `skipSync: true` | add path, `reactions.ts:28` | `sanitizeReactions` returns `deleteReactions: []` before the diff (`utils/reaction.ts:49`). The one-reaction payload is not treated as the full reaction set, so the handler does not delete every other reaction on the post. |
| `skipSync` (undefined) | `handlePosts` → `handleReactions`, `post.ts:564` | Full-sync mode. The reactions in a post's metadata are treated as the complete set, and stale rows are destroyed (`index.ts:156`). |
| `prepareRecordsOnly: false` | add path | The batch is committed inside `handleReactions`. |
| `prepareRecordsOnly: true` | `handlePosts`, `post.ts:564` | Returns models so the caller can batch them with posts and files. |

Reaction-added events are not the only way reactions reach the table. Post payloads that carry `metadata.reactions` go through `handlePosts` and into the full-sync path above.

## Does removal take the same path?

No. It shares the switch dispatch and the empty `catch`. It does not use the `handleReactions` operator, the sync diff, or the `skipSync` flag. It also bypasses `batchRecords`, so the corruption-event handling in `base_data_operator/index.ts:198-206` does not run for removals.

## Observations

- Both handlers swallow every error in an empty `catch` (`reactions.ts:16`, `:34`, `:51`). A failed add or remove leaves no log. CLAUDE.md requires `logError` in handlers, so these are the places to add it.
- Both handlers are fire-and-forget in the switch (`event.ts:164`, `:167`), so ordering between an add and a remove for the same reaction is not guaranteed.
- I did not read `prepareRecords` or `processRecords` internals. The create path is inferred from `handleReactions`, and I did not run tests.