**How `ServerDataOperator` is built**

`ServerDataOperator` is declared at `app/database/operator/server_data_operator/index.ts:40` as `class ServerDataOperator extends mix(ServerDataOperatorBase).with(...)`, mixing in 13 handler classes. Its constructor takes `(database: Database, serverUrl?: string)` (line 55). A matching `interface ServerDataOperator extends ...Mix` declaration (line 23) merges the handler types in for typing. The mixin chain sits on `ServerDataOperatorBase`, which extends `BaseDataOperator`.

Handler mixins:

| Handler | Defined in |
|---|---|
| CategoryHandler, ChannelHandler, CustomProfileHandler, GroupHandler, PostHandler, PropertiesHandler, TeamHandler, TeamThreadsSyncHandler, ThreadHandler, UserHandler | `app/database/operator/server_data_operator/handlers/*.ts` (same folder as the class) |
| `ServerDataOperatorBase` (base, plus `handleRole`, `handleCustomEmojis`, `handleSystem`, `handleConfigs`, `handleReactions`, `handleFiles`, `execute`) | `app/database/operator/server_data_operator/handlers/index.ts:31` |
| AgentsHandler | `app/products/agents/database/operators/handlers/index.ts` |
| BoardsHandler | `app/products/boards/database/operators/handlers/index.ts` |
| PlaybookHandler | `app/products/playbooks/database/operators/handlers/index.ts` |

So three product handlers (agents, boards, playbooks) live outside the operator folder. The `*Mix` interface types I saw in the merged declaration are presumably in each handler file, but I did not confirm their locations.

**Who performs the actual database write**

The write is done in one place: `BaseDataOperator.batchRecords` (`app/database/operator/base_data_operator/index.ts:191`). It calls `this.database.write(async (writer) => writer.batch(...models))`. On failure it logs a warning, emits `DATABASE_CORRUPTION_DETECTED` if the error is a corruption error, and rethrows only when `propagateError` is set.

A handler write flows through this chain:

```
handleX (e.g. PostHandler.handlePosts)
  → handleRecords / prepareRecords / _createOrUpdate…   (build WatermelonDB models)
  → batchRecords(models)  only if prepareRecordsOnly is false
      → database.write(writer => writer.batch(...))
```

Handler methods default to `prepareRecordsOnly`, so they often return prepared models without writing. `handleRecords` defaults `prepareRecordsOnly = true` (`base_data_operator/index.ts:224`), and the write happens only when a caller passes `false`.

**What else shares that write path**

- **`BaseDataOperator`'s other methods.** `handleRecords` and `prepareRecords` both feed `batchRecords`.
- **`AppDataOperator`** extends `BaseDataOperator`, so it inherits the same `batchRecords` for the global app database. This is the only other confirmed consumer of the base class.
- **Callers of `batchRecords` (per the index, 32 total, 25 shown):** the `PostHandler` internals (`_createOrUpdateScheduledPost`, `_deleteScheduledPostByIds`, `_createPostsInChannelRecord`, `_mergePostInChannelChunks`), `ServerDataOperatorBase.execute`, and handlers across Channel, Group, Thread, User, Properties, TeamThreadsSync, and the three product handlers (AgentsHandler, PlaybookHandler). Those with `handleRecords` as a caller (39 total, 25 shown) include the Category, Channel, Team, CustomProfile, Boards, and Agents handlers, plus `AppDataOperator.handleGlobal` and `handleInfo`.
- **Not verified:** `app/actions/local/ephemeral_mode/cleanup.ts` has three entries named `batchRecords` (`cleanupAiThreads`, `cleanupPlaybookRuns`, `autoCacheCleanup`). The index marks them as candidates without bodies, so I could not confirm whether they call this method or are separate local names.

The index answered from the `dossier` output above. I did not read source files, so the exact `Mix` locations and the cleanup-file question are the gaps.