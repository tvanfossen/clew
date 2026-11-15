**How the class is built.** `ServerDataOperator` (`app/database/operator/server_data_operator/index.ts:40`) is a class that extends `mix(ServerDataOperatorBase).with(...)`, applying 13 handler mixins. A matching `interface ServerDataOperator extends ...Mix` (line 23) gives TypeScript the method signatures. The constructor takes a WatermelonDB `Database` and an optional `serverUrl`. `ServerDataOperatorBase` is the root that the mixins build on. `mix` itself is a one-line wrapper around `MixinBuilder` (`app/utils/mix.ts:15`).

Each handler is a higher-order function `(superclass) => class extends superclass`, so every handler's methods can call `this.handleRecords`, `this.batchRecords`, and so on.

**Defined next to it** (`app/database/operator/server_data_operator/handlers/`):
- `category`, `channel`, `custom_profile`, `group`, `post`, `properties`, `team`, `team_threads_sync`, `thread`, `user`
- The base class `ServerDataOperatorBase` lives in `handlers/index.ts`. It extends `BaseDataOperator` and provides `handleRole`, `handleCustomEmojis`, `handleSystem`, `handleConfigs`, `handleReactions`, `handleFiles`, and `execute`.

**Defined elsewhere:**
| Mixin | File |
|---|---|
| `AgentsHandler` | `app/products/agents/database/operators/handlers/index.ts` |
| `BoardsHandler` | `app/products/boards/database/operators/handlers/index.ts` |
| `PlaybookHandler` | `app/products/playbooks/database/operators/handlers/index.ts` |

The product handlers follow the same pattern and are imported under `@agents`, `@boards`, and `@playbooks` aliases.

**Where a handler's write actually happens.** The chain is:

```
handler (e.g. handleBoardViews, handlePlaybookRun)
  → this.handleRecords(...)           base_data_operator/index.ts:224
      → processRecords → prepareRecords   (builds WatermelonDB prepareCreate/prepareUpdate models, no write)
      → if !prepareRecordsOnly: this.batchRecords(models, description)
  → or the handler collects models itself and calls this.batchRecords(batch, 'desc')
        → batchRecords                base_data_operator/index.ts:191
            → this.database.write(async (writer) => writer.batch(...models), description)
```

So the actual database write is `database.write` plus `writer.batch(...)` inside `BaseDataOperator.batchRecords`. It is the only place these handlers touch the write API. The handler code only prepares models. Errors are caught and logged. If the error is a corruption error, the method emits `Events.DATABASE_CORRUPTION_DETECTED`. It rethrows only when `propagateError` is true.

**What else shares it:**
- `batchRecords` is called from `ServerDataOperatorBase.execute`, `handleFiles`, and `handleReactions`, which are in the base class. It is also called from many server handlers: all the `post.ts` write paths, `channel.ts` `handleChannelBookmark`, `group.ts`, `user.ts` `handlePreferences`, `properties.ts`, `thread.ts`, `team_threads_sync.ts`, and `AgentsHandler` (`handleAIBots`, `handleAIThreads`). The product `PlaybookHandler` calls it too.
- `handleRecords` is shared more widely. It is called by every handler, by `AppDataOperator.handleGlobal` and `handleInfo`, which write to the app database, and by the Boards and Agents mixins.
- The `batchRecords` candidates in `app/actions/local/ephemeral_mode/cleanup.ts` are local variables with the same name, not calls to this method, so they are not sharing it.

Note that the `handleX` methods do not write the database directly. The write is centralized in `batchRecords`. Any change to transaction behavior, error handling, or corruption detection there affects every handler, and that includes the app-database operator.