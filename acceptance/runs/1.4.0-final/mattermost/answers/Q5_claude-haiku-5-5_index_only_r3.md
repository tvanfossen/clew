**Class composition.** `ServerDataOperator` (`app/database/operator/server_data_operator/index.ts:40`) is `class ServerDataOperator extends mix(ServerDataOperatorBase).with(...)`. The base is `ServerDataOperatorBase`, which extends `BaseDataOperator`. It mixes in 13 handler mixins, and the interface at `index.ts:23` declares matching `*HandlerMix` types so the methods type-check.

**Where the handlers live:**

| Handler | Location |
|---|---|
| `CategoryHandler`, `ChannelHandler`, `CustomProfileHandler`, `GroupHandler`, `PostHandler`, `PropertiesHandler`, `TeamHandler`, `TeamThreadsSyncHandler`, `ThreadHandler`, `UserHandler` | `app/database/operator/server_data_operator/handlers/*.ts` (same folder as `index.ts`) |
| `ServerDataOperatorBase` | `app/database/operator/server_data_operator/handlers/index.ts:31` (same folder, shared base with `handleRole`, `handleCustomEmojis`, `handleReactions`, `handleFiles`, `execute`, etc.) |
| `AgentsHandler` | `app/products/agents/database/operators/handlers/index.ts` |
| `BoardsHandler` | `app/products/boards/database/operators/handlers/index.ts` |
| `PlaybookHandler` | `app/products/playbooks/database/operators/handlers/index.ts` |

So three product handlers (agents, boards, playbooks) are defined outside the server operator folder, under their own `products/*/database/operators/handlers` directories.

**The actual database write.** Handlers don't write directly. The path is:

1. A handler method, e.g. `PostHandler.handlePosts`, builds raw input.
2. It calls `ServerDataOperatorBase.execute` (`handlers/index.ts:234`) or `BaseDataOperator.handleRecords`. These call `prepareRecords`, which produces WatermelonDB `prepareCreate`/`prepareUpdate` models.
3. `BaseDataOperator.batchRecords` (`app/database/operator/base_data_operator/index.ts:191`) performs the write: `this.database.write(async (writer) => writer.batch(...models), description)`.

That `batchRecords` body is the only place the write happens. It also:
- Catches errors and logs them with `logWarning`. It rethrows only when `propagateError` is true.
- Emits `Events.DATABASE_CORRUPTION_DETECTED` if the error is a corruption error.

Handlers called with `prepareRecordsOnly` return the prepared models without calling `batchRecords`, so the caller batches them later.

**What else shares it.**
- `AppDataOperator` also extends `BaseDataOperator`, so the app-level database uses the same write path.
- All server handlers reach it through `execute`, `handleRecords` or `handleFiles`/`handleReactions`. Those cover `PostHandler`, `ChannelHandler`, `GroupHandler`, `ThreadHandler`, `UserHandler`, `PropertiesHandler`, and `TeamThreadsSyncHandler`.
- The product handlers `AgentsHandler` (`handleAIBots`, `handleAIThreads`) and `PlaybookHandler` (`handlePlaybookRun`, `handlePlaybookChecklist`, `handlePlaybookChecklistItem`) call it directly.

The index also lists `cleanupAiThreads`, `cleanupPlaybookRuns` and `autoCacheCleanup` in `app/actions/local/ephemeral_mode/cleanup.ts` as `batchRecords` candidates. I did not verify whether they call it, because the index marks them as name matches without bodies. The caller list for `batchRecords` is also incomplete: the index reports 232 unresolved callers, so there may be more than the ones above.