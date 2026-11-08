**Composition.** `ServerDataOperator` (`app/database/operator/server_data_operator/index.ts:23`) is an interface that extends 14 handler mixins. Eleven are defined in the same `handlers/` folder as the class:

- `ServerDataOperatorBase` (`handlers/index.ts:31`), the shared base class
- `CategoryHandlerMix`, `ChannelHandlerMix`, `CustomProfileHandlerMix`, `GroupHandlerMix`, `PostHandlerMix`, `PropertiesHandlerMix`, `TeamHandlerMix`, `TeamThreadsSyncHandlerMix`, `ThreadHandlerMix`, `UserHandlerMix`

Three are defined elsewhere, in the product modules:

| Mixin | Defined in | Methods |
|---|---|---|
| `AgentsHandlerMix` | `app/products/agents/database/operators/handlers/index.ts:30` | `handleAIBots`, `handleAIThreads` |
| `BoardsHandlerMix` | `app/products/boards/database/operators/handlers/index.ts:20` | `handleBoardViews` |
| `PlaybookHandlerMix` | `app/products/playbooks/database/operators/handlers/index.ts:49` | `handlePlaybookRun`, `handlePlaybookChecklist`, `handlePlaybookChecklistItem`, `handlePlaybookRunPropertyField`, `handlePlaybookRunPropertyValue` |

Each concrete handler is a factory that takes a superclass constrained to `Constructor<ServerDataOperatorBase>` and returns a subclass. `BoardsHandler` (`boards/.../handlers/index.ts:24-44`) is an example. Its `handleBoardViews` method calls `this.handleRecords(...)`.

**The write path.** Handlers never touch WatermelonDB directly. The chain is:

1. A handler method (for example `handleBoardViews`) builds its raw values and calls `this.handleRecords`.
2. `BaseDataOperator.handleRecords` (`app/database/operator/base_data_operator/index.ts:224`) calls `processRecords` to deduplicate against existing rows and split the input into create, update and delete lists. It then calls `prepareRecords` to turn them into prepared models. If `prepareRecordsOnly` is false, it calls `batchRecords`.
3. **`BaseDataOperator.batchRecords` (`base_data_operator/index.ts:191-211`) is the function that performs the database write.** It calls `this.database.write(writer => writer.batch(...models))`. On error it logs a warning. If the error is a corruption error, it emits `DATABASE_CORRUPTION_DETECTED`. It rethrows only when `propagateError` is set.

A second path skips the dedupe step. `ServerDataOperatorBase.execute` (`server_data_operator/handlers/index.ts:234`) calls `prepareRecords` and then `batchRecords`, bypassing `processRecords`.

**What else shares the write.** `batchRecords` is the single write sink for the whole layer. Its indexed callers include:

- `handleRecords` and `execute`, which almost every handler reaches
- Methods on `PostHandler` that write directly, such as `_createOrUpdateScheduledPost`, `_createPostsInChannelRecord`, `_deleteScheduledPostByIds` and `_mergePostInChannelChunks`
- `ChannelHandler.handleChannelBookmark`, the group handlers, the playbook handlers and the agents handlers

`AppDataOperator` also derives from `BaseDataOperator`, so it shares `batchRecords` and `handleRecords`. The only difference is which `database` instance it writes to: the global app database for `AppDataOperator`, and the per-server database for `ServerDataOperator`.

**Caveats.** The caller list for `batchRecords` reports 159 unresolved callers, so it is not exhaustive. Several functions named `batchRecords` in `app/actions/local/ephemeral_mode/cleanup.ts` are separate local helpers, not the base method. I did not check the `AppDataOperator` class's own dossier, which the index did not resolve by that name, so its inheritance is taken from the base class's `derived` list.