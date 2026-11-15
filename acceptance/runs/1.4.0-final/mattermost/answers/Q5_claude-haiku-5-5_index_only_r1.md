**How the class is built**

`ServerDataOperator` (`app/database/operator/server_data_operator/index.ts:40`) is `mix(ServerDataOperatorBase).with(...)`, a mixin composition. Its base is `ServerDataOperatorBase`, which extends `BaseDataOperator`. The index's `interface ServerDataOperator extends ...Mix` declaration (line 23) merges in the matching `*Mix` interface types so the mixed-in methods are typed. The constructor is `constructor(database: Database, serverUrl?: string)` (line 55). The index reports 14 bases in total.

**Handlers defined next to it** (`app/database/operator/server_data_operator/handlers/`):

- `category`, `channel`, `custom_profile`, `group`, `post`, `properties`, `team`, `team_threads_sync`, `thread`, `user`
- The base itself, `ServerDataOperatorBase`, is in `handlers/index.ts:31`. It provides the shared helpers: `handleRole`, `handleCustomEmojis`, `handleSystem`, `handleConfigs`, `handleReactions`, `handleFiles`, and `execute`.

**Handlers defined elsewhere:**

- `AgentsHandler`: `app/products/agents/database/operators/handlers/index.ts`
- `BoardsHandler`: `app/products/boards/database/operators/handlers/index.ts`
- `PlaybookHandler`: `app/products/playbooks/database/operators/handlers/index.ts`

The paths for the last two are inferred from their qualified names; I did not confirm the file contents of those two.

**Who performs the database write**

The write has three layers:

1. **Handler (product or core):** builds the raw input. `handleAIBots` (`app/products/agents/database/operators/handlers/index.ts:43`) is typical. It fetches existing rows, diffs them against incoming raws, and calls `handleRecords` to prepare create/update models. It also marks stale rows with `prepareDestroyPermanently()`. It calls `batchRecords` only when `prepareRecordsOnly` is false.
2. **`ServerDataOperatorBase.execute`** (`handlers/index.ts:234`) is a thin wrapper. It calls `prepareRecords`, then `batchRecords` if there are models.
3. **`BaseDataOperator`** (`app/database/operator/base_data_operator/index.ts`) does the actual work:
   - `prepareRecords` (line 134) runs the transformer for each create/update raw and appends `prepareDestroyPermanently()` results for deletes.
   - `batchRecords` (line 191) is the real write. It calls `this.database.write(async (writer) => writer.batch(...models))`. On error it logs with `logWarning`, emits `Events.DATABASE_CORRUPTION_DETECTED` if the error is a corruption error, and rethrows only when `propagateError` is set.

So every handler's write ends in `BaseDataOperator.batchRecords`.

**What else shares it**

- **Inside the server operator:** the base `execute`, `handleFiles`, and `handleReactions`. Also `PostHandler` (many methods, including `handlePosts`, `handleReceivedPostsInChannel*`, and scheduled-post handlers), `ChannelHandler.handleChannelBookmark`, `GroupHandler` (three methods), `UserHandler.handlePreferences`, `PropertiesHandler` (fields and values), `ThreadHandler`, `TeamThreadsSyncHandler.handleTeamThreadsSync`, and `AgentsHandler` (`handleAIBots`, `handleAIThreads`) and `PlaybookHandler` (run, checklist, checklist item).
- **Across the app:** `AppDataOperator` also extends `BaseDataOperator`, so the app database shares the same write path. The index also lists callers in `app/actions/local/ephemeral_mode/cleanup.ts` (`cleanupAiThreads`, `cleanupPlaybookRuns`, `autoCacheCleanup`). Those entries have no resolved body, so I could not confirm whether they reach this same method.

**Caveats**

- The `ServerDataOperator` declaration is truncated in the index at 8 lines. The list of 14 bases comes from the index's base list, not from reading the full `with(...)` argument list.
- `batchRecords` has about 232 unresolved callers, so the caller list above may be incomplete.