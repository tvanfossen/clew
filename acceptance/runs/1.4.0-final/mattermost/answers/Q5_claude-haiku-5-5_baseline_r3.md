`ServerDataOperator` is a thin class built by a mixin chain. The record-writing machinery lives in one shared base class, and every handler's write goes through a single `batchRecords` method that calls `database.write`.

**Composition**

`app/database/operator/server_data_operator/index.ts` declares:

```ts
class ServerDataOperator extends mix(ServerDataOperatorBase).with(
    AgentsHandler, BoardsHandler, CategoryHandler, ChannelHandler, CustomProfileHandler,
    GroupHandler, PlaybookHandler, PostHandler, PropertiesHandler, TeamHandler,
    ThreadHandler, TeamThreadsSyncHandler, UserHandler,
) { constructor(database, serverUrl?) { super(database); this.serverUrl = serverUrl; } }
```

- `mix` (`app/utils/mix.ts`) is a tiny reducer: it starts from the base class and applies each mixin in order, so each mixin wraps the previous class.
- Each mixin is `<TBase>(superclass) => class extends superclass { handleX = async (...) => ... }`. Each one also exports a `XHandlerMix` interface. The `interface ServerDataOperator extends ...Mix` block merges those types in so TypeScript sees the methods on the final class.
- The root is `ServerDataOperatorBase` (`server_data_operator/handlers/index.ts`), which extends `BaseDataOperator` (`base_data_operator/index.ts`). It holds the `serverUrl` field and the generic handlers: `handleRole`, `handleSystem`, `handleConfigs`, `handleCustomEmojis`, `handleReactions`, `handleFiles`, and `execute`.
- `DatabaseManager.createServerDatabase` (`app/database/manager/index.ts:184`) is the only production site that does `new ServerDataOperator(database, serverUrl)`.

**Handlers defined elsewhere**

| Mixin | Location |
|---|---|
| `AgentsHandler` | `app/products/agents/database/operators/handlers/index.ts` |
| `BoardsHandler` | `app/products/boards/database/operators/handlers/index.ts` |
| `PlaybookHandler` | `app/products/playbooks/database/operators/handlers/index.ts` |

The rest sit in `server_data_operator/handlers/`: category, channel, custom_profile, group, post, properties, team, team_threads_sync, thread, user. The base class's own generic handlers are in `handlers/index.ts`.

**The actual write**

Handlers don't write directly. The path is:

1. A handler (for example `handleThreads` in `thread.ts`) calls `this.handleRecords({...transformer, createOrUpdateRawValues, tableName, prepareRecordsOnly})`.
2. `handleRecords` calls `processRecords`, which queries existing rows and splits the input into create, update and delete sets.
3. `prepareRecords` runs the transformer for each set. Transformers build unsaved WatermelonDB models with `prepareCreate` or `prepareUpdate`. Deletes use `prepareDestroyPermanently`.
4. If `prepareRecordsOnly` is false, `batchRecords` runs. It calls `this.database.write(async (writer) => writer.batch(...models), description)` at `base_data_operator/index.ts` around line 194.

`batchRecords` logs failures with `logWarning` and swallows them unless `propagateError` is set. On a database corruption error it emits `Events.DATABASE_CORRUPTION_DETECTED`.

Because `prepareRecordsOnly` defaults to true in `handleRecords`, a caller often gets unsaved models back and must batch them later. Many handlers do exactly that, combining models from several calls into one `batchRecords` call.

**What else shares this machinery**

- `AppDataOperator` (`app/database/operator/app_data_operator/index.ts`) extends the same `BaseDataOperator`, so it gets the same `processRecords`, `prepareRecords`, `batchRecords` and `handleRecords`. It runs against the global app database, not a server database.
- Every product mixin calls `this.batchRecords`, not its own write. The agents and playbooks handlers do this, and so does the core `execute` helper in the base class.
- The shared helpers live in `database/operator/utils/general.ts`: `getUniqueRawsBy`, `retrieveRecords`, `getValidRecordsForUpdate`, and `prepareDestroyPermanentlyChildrenAssociatedRecords`. The transformers and comparators in the `transformers/` and `comparators/` folders sit alongside them.
- Some code bypasses `batchRecords` and calls `database.write` itself. These sites include the post delete path (`handlers/post.ts:516`), the thread delete path (`handlers/thread.ts:74`), the playbooks local actions, and the database manager's app-database setup. The `app/database/operator/utils/test.ts` helper also writes with `writer.batch` directly.

I read the mixin files and call sites directly rather than exhaustively reading every handler body, so the per-handler details are from sampling, not a full audit.

Note: a Bash hook output in this session suggested a `dossier` tool for inspecting code. No such tool is available to me, so I ignored it and used file reads and grep.