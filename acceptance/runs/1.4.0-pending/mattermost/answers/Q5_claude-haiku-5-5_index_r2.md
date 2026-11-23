`ServerDataOperator` is a thin class that mixes 14 handler mixins onto `ServerDataOperatorBase`. Ten of the handlers are defined next to it; three are defined in product folders. Every handler write goes through one method, `BaseDataOperator.batchRecords`.

**How the class is built** (`app/database/operator/server_data_operator/index.ts`)

- `ServerDataOperatorBase` (`handlers/index.ts:31`) is the base. It extends `BaseDataOperator` and holds `serverUrl`, `handleRole`, `handleSystem`, `handleConfigs`, `handleCustomEmojis`, `handleReactions`, `handleFiles`, and `execute`.
- `mix(ServerDataOperatorBase).with(...)` (`app/utils/mix.ts`) applies each handler class as a subclass layer, so the handler methods become instance methods.
- The `interface ServerDataOperator extends ...Mix` block adds the TypeScript types for those methods through declaration merging. Each handler exports an `XHandlerMix` interface alongside its class.

**Handlers defined elsewhere**

| Handler | Defined in |
|---|---|
| `AgentsHandler` | `app/products/agents/database/operators/handlers/index.ts` |
| `BoardsHandler` | `app/products/boards/database/operators/handlers/index.ts` |
| `PlaybookHandler` | `app/products/playbooks/database/operators/handlers/index.ts` |

The other ten are in `app/database/operator/server_data_operator/handlers/`: category, channel, custom_profile, group, post, properties, team, team_threads_sync, thread, and user.

**The write path**

```
handler (e.g. AgentsHandler.handleAIBots)
  → this.handleRecords / this.prepareRecords / this.processRecords
  → this.batchRecords(models, description)        base_data_operator/index.ts:191
      → this.database.write(async (writer) => writer.batch(...models))
```

- `batchRecords` is the actual write. It calls WatermelonDB's `database.write` and `writer.batch`. On error it logs and, unless `propagateError` is set, swallows the error. If the error is a corruption error it emits `DATABASE_CORRUPTION_DETECTED`.
- `handleRecords` (`base_data_operator/index.ts:224`) runs `processRecords` to diff against existing rows, then `prepareRecords` to build models, and calls `batchRecords` only when `prepareRecordsOnly` is false.
- Handlers that use the `prepareRecordsOnly` flag let callers combine several prepared models into one batch.

**What else shares that write code**

- Every `ServerDataOperator` handler, including the three product handlers, writes through `batchRecords`. The product handlers call it directly or through `handleRecords`.
- `AppDataOperator` (`app/database/operator/app_data_operator/index.ts`, `handleGlobal`/`handleInfo`) also inherits `handleRecords` and `batchRecords` from `BaseDataOperator`, so it shares this path with the server database.
- Ephemeral-mode cleanup in `app/actions/local/ephemeral_mode/cleanup.ts` also calls `batchRecords`.
- `prepareRecords` and `processRecords` are used only by the server handlers and `handleRecords`.

Operator writes are not the only writes. Many action files call `database.write(...)` or `database.batch(...)` directly, bypassing the operator. Examples are `app/actions/local/post.ts`, `app/actions/local/file.ts`, and the playbooks actions. `DatabaseManager` (`app/database/manager/index.ts`) also writes to the app database directly. Those writes don't get the operator's error handling or corruption event.

I did not check whether `DatabaseManager` or the action files route any writes through `ServerDataOperator`.