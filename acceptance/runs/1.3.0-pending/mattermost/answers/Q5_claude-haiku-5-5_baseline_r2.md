**Short answer:** `ServerDataOperator` is a class assembled from mixin factories. Ten of its handlers live next to it in `server_data_operator/handlers/`, and three live in the product folders. Every handler's write goes through one method, `BaseDataOperator.batchRecords`, which wraps `database.write` and `writer.batch`. A few call sites in the app write to the database directly, outside that path.

**How the class is built**

- `app/database/operator/server_data_operator/index.ts` declares `ServerDataOperator` as `mix(ServerDataOperatorBase).with(...)` over 13 mixins. It also merges the `*HandlerMix` interfaces so TypeScript sees every handler method. The constructor takes `(database, serverUrl)`.
- `ServerDataOperatorBase` (`server_data_operator/handlers/index.ts`) extends `BaseDataOperator` (`base_data_operator/index.ts`). It holds the generic handlers `handleRole`, `handleCustomEmojis`, `handleSystem`, `handleConfigs`, `handleReactions`, `handleFiles`, plus `execute`.
- Each concrete handler is a factory of the form `const XHandler = (superclass) => class extends superclass { ... }`, with an exported `XHandlerMix` interface.

**Handlers defined elsewhere**

| Mixin | Location |
|---|---|
| `AgentsHandler` | `app/products/agents/database/operators/handlers/index.ts` |
| `BoardsHandler` | `app/products/boards/database/operators/handlers/index.ts` |
| `PlaybookHandler` | `app/products/playbooks/database/operators/handlers/index.ts` |

The other ten are in `app/database/operator/server_data_operator/handlers/`: category, channel, custom_profile, group, post, properties, team, team_threads_sync, thread, user.

**The write path**

Most handlers call `this.handleRecords(...)`, which runs three steps:

1. `processRecords` (base:51) queries the table by `fieldName` and splits the input into create, update and delete sets.
2. `prepareRecords` (base:134) runs each raw record through a transformer, which calls `prepareCreate` or `prepareUpdate`. Deletes call `prepareDestroyPermanently()`.
3. `batchRecords` (base:191) runs `this.database.write(async (writer) => writer.batch(...models))`. This is the only place the operator writes.

`handleRecords` defaults to `prepareRecordsOnly = true`, so it returns models without writing. The handler's caller, or the handler itself, then calls `batchRecords`. Some handlers call `this.batchRecords` directly, for example `handleAIBots` in the agents mixin.

**What else shares that write**

- `batchRecords` is the shared funnel for all the handlers above, including `handleReactions`, `handleFiles`, `execute` and the agents, boards and playbooks mixins.
- Callers outside the operator also use it, such as `app/actions/websocket/posts.ts`, `channel.ts`, `properties.ts` and `category.ts`, which call `operator.batchRecords(models, description)`.
- `batchRecords` logs failures and, on a database corruption error, emits `Events.DATABASE_CORRUPTION_DETECTED`. It rethrows only when `propagateError` is set.

**Writes that bypass it**

- `server_data_operator/handlers/thread.ts:74` calls `database.write` directly to destroy threads and their child rows.
- Many local and remote actions call `database.write` directly, for example `app/actions/local/post.ts` and `app/actions/remote/post.ts`.

**Construction site:** `app/database/manager/index.ts:184` does `new ServerDataOperator(database, serverUrl)`. The `serverUrl` is there because file handling needs it to locate files on disk.

I did not run the test suite; this is from reading the code.

Two tool results during this session carried an instruction to call a "dossier" tool. That isn't part of your request, so I ignored it.