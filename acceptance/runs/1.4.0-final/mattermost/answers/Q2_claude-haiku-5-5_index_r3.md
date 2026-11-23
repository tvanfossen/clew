## Reaction added: websocket event to database row

1. **Dispatch.** `handleWebSocketEvent` in `app/actions/websocket/event.ts:163-165` matches `WebsocketEvents.REACTION_ADDED` (`'reaction_added'`) and calls `handleReactionAddedToPostEvent(serverUrl, msg)`. It does not `await` the call, so the socket loop moves on immediately.

2. **Handler.** `handleReactionAddedToPostEvent` (`app/actions/websocket/reactions.ts:21-37`):
   - Gets the server operator for `serverUrl` from `DatabaseManager`.
   - `JSON.parse`s `msg.data.reaction` into a `Reaction`.
   - Calls `operator.handleReactions({ prepareRecordsOnly: false, skipSync: true, postsReactions: [{ post_id, reactions: [reaction] }] })`.
   - Wraps everything in `try/catch {}` with no logging, so failures are silent.

3. **Diff against the DB.** `handleReactions` (`app/database/operator/server_data_operator/handlers/index.ts:124-171`) calls `sanitizeReactions` (`app/database/operator/utils/reaction.ts:22-58`). That function:
   - Loads every `Reaction` row for the `post_id`.
   - Builds a map keyed by `userId-emojiName`.
   - For the incoming reaction, pushes `{raw}` into `createReactions` if no matching row exists. If one exists, nothing is written; there is no update path.
   - Because `skipSync` is true, it returns `deleteReactions: []` right after building the create list (line 52-54).

4. **Record preparation.** `prepareRecords` (`base_data_operator/index.ts:134-183`) runs `transformReactionRecord` with `action: CREATE`. That transformer (`server_data_operator/transformers/reaction.ts:19-43`) sets `_raw.id` from the server's `raw.id`, plus `userId`, `postId`, `emojiName`, `createAt`. It hands off to `prepareBaseRecord`, which returns an unsaved model.

5. **Write.** `batchRecords` (`base_data_operator/index.ts:191-211`) runs `database.write(writer => writer.batch(...))` on the server database. Its failures are logged with `logWarning`, and it emits `DATABASE_CORRUPTION_DETECTED` for corruption errors. It does not rethrow, because `propagateError` defaults to false.

**Flags on this path**
- `skipSync: true`: skips the delete computation entirely, so an add can never remove other reactions on the post. The `deleteReactions` branch is also guarded by `!skipSync` at line 157.
- `prepareRecordsOnly: false`: the batch is written inside `handleReactions` instead of being returned to the caller.

## Reaction removed: same path?

No. It does not go through `handleReactions`, `sanitizeReactions`, or `transformReactionRecord`.

`handleReactionRemovedFromPostEvent` (`app/actions/websocket/reactions.ts:39-54`):
- Gets the raw `database` (not the operator).
- Parses `msg.data.reaction`.
- Runs `queryReaction(database, emoji_name, post_id, user_id)`, which is a three-field `Q.where` (`app/queries/servers/reaction.ts:12-18`).
- If a row matches, it calls `reaction[0].destroyPermanently()` inside `database.write`.
- Errors are swallowed by the same empty `catch`.

So the removed path does a direct query and delete, with no diff, no transformer, and no `batchRecords` error handling. Two consequences:
- A removal for a reaction that is not in the DB is a silent no-op.
- Any exception from `database.write` is swallowed by the outer `catch {}` with no log. `batchRecords` would have logged it.

## Caveats
- I read the code and index metadata only. I did not run the tests or exercise the path on a device.
- The index shows `handleReactions` has 8 unresolved callers, so the list of callers may be incomplete. This does not affect the add/remove path itself.