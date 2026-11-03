**Short answer:** `ServerDataOperator` is an interface that intersects 11 handler mixins from `handlers/` with 3 product mixins from `app/products/`, all built on `ServerDataOperatorBase`. Every handler write funnels through `BaseDataOperator.batchRecords`, which is the only place that calls `database.write`. `AppDataOperator` and the `PostHandler` private helpers share that path.

**Composition** (`app/database/operator/server_data_operator/index.ts:23`)

`ServerDataOperator` extends 14 bases:

| Source | Bases |
|---|---|
| Next to it, in `server_data_operator/handlers/` | `CategoryHandlerMix`, `ChannelHandlerMix`, `CustomProfileHandlerMix`, `GroupHandlerMix`, `PostHandlerMix`, `PropertiesHandlerMix`, `TeamHandlerMix`, `TeamThreadsSyncHandlerMix`, `ThreadHandlerMix`, `UserHandlerMix` |
| Same folder, but a class, not a mixin | `ServerDataOperatorBase` (`handlers/index.ts:31`) |
| Defined elsewhere | `AgentsHandlerMix` (`app/products/agents/database/operators/handlers/index.ts:30`), `BoardsHandlerMix` (`app/products/boards/database/operators/handlers/index.ts:20`), `PlaybookHandlerMix` (`app/products/playbooks/database/operators/handlers/index.ts:49`) |

So the three product mixins are the only handler classes defined outside the server operator's folder. Each contributes its own methods: `handleAIBots`/`handleAIThreads`, `handleBoardViews`, and the five `handlePlaybook*` methods.

`ServerDataOperatorBase` itself extends `BaseDataOperator` (`app/database/operator/base_data_operator/index.ts:33`), which holds the `database` handle and the generic machinery: `processRecords`, `prepareRecords`, `handleRecords`, `batchRecords`.

**Write path for a handler**

1. A handler method (e.g. `handleUsers`, `handleAIBots`) calls `handleRecords` or `execute`.
2. `handleRecords` (`base_data_operator/index.ts:224`) dedupes against existing rows via `processRecords`, builds models via `prepareRecords`, and calls `batchRecords` only when `prepareRecordsOnly` is false.
3. `execute` (`server_data_operator/handlers/index.ts:234`) is the simpler create/update path: `prepareRecords` then `batchRecords`.
4. `batchRecords` (`base_data_operator/index.ts:191`) is the actual write: `this.database.write(async (writer) => writer.batch(...models), description)`. On error it logs a warning, emits `DATABASE_CORRUPTION_DETECTED` if the error is a corruption error, and rethrows only when `propagateError` is set.

**What else shares that write**

- **Every handler that goes through `handleRecords` or `execute`.** The index lists about 40 callers, including `handleUsers`, `handleChannel`, `handleTeam`, `handleThreads`, `handleDraft`, the `handlePlaybook*` methods, and `handleAIBots`.
- **`PostHandler` private helpers** call `batchRecords` directly: `_createOrUpdateScheduledPost`, `_createPostsInChannelRecord`, `_deleteScheduledPostByIds`, `_mergePostInChannelChunks`.
- **`AppDataOperator`** (`app/database/operator/app_data_operator/index.ts`) also extends `BaseDataOperator`, so `handleGlobal` and `handleInfo` share the same `batchRecords` path, but against the app database instead of a server database.

**Caveats**

- The `batchRecords` caller list reports 159 unresolved call sites. The ephemeral cleanup functions in `app/actions/local/ephemeral_mode/cleanup.ts` show up only as name matches, not as confirmed callers, so I did not count them as sharing the path.
- `handleReactions` and `handleFiles` are in `ServerDataOperatorBase` and appear in the callers list, but I did not open their bodies to confirm each one writes via `handleRecords` rather than another route.