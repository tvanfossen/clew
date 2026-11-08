**Composition.** `ServerDataOperator` is declared in `app/database/operator/server_data_operator/index.ts:40` as `class ServerDataOperator extends mix(ServerDataOperatorBase).with(...)`, and an interface of the same name at line 23 merges in the matching `*HandlerMix` typings. The index reports 14 base classes:

| Where it lives | Classes |
|---|---|
| Same folder, `server_data_operator/handlers/` | `CategoryHandler`, `ChannelHandler`, `CustomProfileHandler`, `GroupHandler`, `PostHandler`, `PropertiesHandler`, `TeamHandler`, `TeamThreadsSyncHandler`, `ThreadHandler`, `UserHandler` |
| Same folder, `handlers/index.ts` | `ServerDataOperatorBase` (the root that the handlers extend) |
| Elsewhere, product folders | `AgentsHandler` (`app/products/agents/database/operators/handlers/index.ts`), `BoardsHandler` (`app/products/boards/database/operators/handlers/index.ts`), `PlaybookHandler` (`app/products/playbooks/database/operators/handlers/index.ts`) |

`ServerDataOperatorBase` extends `BaseDataOperator` (`app/database/operator/base_data_operator/index.ts:33`), which holds the `database` handle and the shared plumbing.

**Where the write happens.** The handlers never call WatermelonDB directly. The path is:

1. A handler method (for example `PostHandler.handlePosts`, `post.ts:411`) builds raw values and calls `execute` or `prepareRecords`.
2. `ServerDataOperatorBase.execute` (`handlers/index.ts:234`) calls `prepareRecords` to produce prepared models, then `batchRecords`.
3. `BaseDataOperator.batchRecords` (`base_data_operator/index.ts:191`) is the actual write. It calls `this.database.write(async (writer) => writer.batch(...models))`. On error it logs a warning and, if the error is a corruption error, emits `Events.DATABASE_CORRUPTION_DETECTED`. It only rethrows when `propagateError` is true.

Handlers that take `prepareRecordsOnly` return models without calling `batchRecords`, so the caller decides when the write happens.

**What else shares it.**
- All server handlers reach the write through `batchRecords`, directly or via `execute`. The index lists callers including `handlePosts`, `handleThreads`, `handleAIBots`, `handlePlaybookRun`, `handlePreferences` and `handleTeamThreadsSync`, plus the private `PostHandler` helpers.
- `AppDataOperator` also extends `BaseDataOperator`, so it shares the same `batchRecords` and `processRecords`/`prepareRecords` code, but for the global app database.
- The ephemeral-mode cleanup code in `app/actions/local/ephemeral_mode/cleanup.ts` (`cleanupAiThreads`, `cleanupPlaybookRuns`, `autoCacheCleanup`) also calls `batchRecords`. The index resolves these as unbound references rather than as edges to a specific function.

The caller list is not exhaustive. The index reports 232 unresolved call sites for `batchRecords`, so a grep for `batchRecords(` would be needed to get the full set. I did not read the `handleRecords` body, so I have not confirmed whether it writes on its own path.