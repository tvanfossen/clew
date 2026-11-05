**Short answer:** `ServerDataOperator` is a mixin composition on top of `ServerDataOperatorBase`. Three of its handlers live outside the `server_data_operator/` folder, in the agents, boards and playbooks product folders. Every handler's write goes through `BaseDataOperator.batchRecords`, which is the one place that calls `database.write(writer => writer.batch(...))`, and that method is shared by the other handlers and by the base class's own `execute`/`handleFiles`/`handleReactions`.

**How the class is built** (`app/database/operator/server_data_operator/index.ts`)

- `ServerDataOperatorBase` (`handlers/index.ts:31`) extends `BaseDataOperator`. It holds the generic helpers: `handleReactions`, `handleFiles`, `handleConfigs`, `handleCustomEmojis`, `handleRoles`, `handleSystem`, and `execute`.
- `class ServerDataOperator extends mix(ServerDataOperatorBase).with(...)` applies each handler as a mixin, in order (`index.ts:40-54`). `mix` (`app/utils/mix.ts`) just reduces the list, so each handler is a class factory wrapping the previous class.
- A TypeScript `interface ServerDataOperator extends ...Mix` declaration (`index.ts:23-38`) merges in the method types, so callers see every handler method on the one object.

**Handlers defined elsewhere**

| Mixin | Defined in |
|---|---|
| `AgentsHandler` | `app/products/agents/database/operators/handlers/index.ts` |
| `BoardsHandler` | `app/products/boards/database/operators/handlers/index.ts` |
| `PlaybookHandler` | `app/products/playbooks/database/operators/handlers/index.ts` |

The other handlers are in `app/database/operator/server_data_operator/handlers/`: category, channel, custom_profile, group, post, properties, team, team_threads_sync, thread, user.

**What a handler's write actually runs**

For a typical handler such as `handleChannel` (`handlers/channel.ts:58`):

1. The handler pre-filters incoming raws against existing rows, then calls `this.handleRecords({...}, 'handleChannel')`.
2. `BaseDataOperator.handleRecords` (`app/database/operator/base_data_operator/index.ts:224`) runs `processRecords` to split the input into create, update and delete sets.
3. `prepareRecords` (`:134`) turns those into WatermelonDB models: the transformer builds prepared create/update records, and deletes call `prepareDestroyPermanently()`. Nothing is written yet.
4. Only when `prepareRecordsOnly` is false does `handleRecords` call `batchRecords` (`:251`).
5. `batchRecords` (`:191-211`) runs `this.database.write(async (writer) => writer.batch(...models))`. This is the actual database write. Errors are logged and swallowed unless `propagateError` is set. Corruption errors also emit `DATABASE_CORRUPTION_DETECTED`.

`handleChannel` defaults `prepareRecordsOnly` to `true`, so a caller has to opt in to the write. Handlers that combine several tables (the agents, playbooks and boards handlers) collect models into a `batchRecords` array and write once at the end, through `this.batchRecords(...)`.

**What else shares `batchRecords`**

- `handleRecords` itself, which is the path every table handler uses.
- `ServerDataOperatorBase.execute` (`handlers/index.ts:243`), `handleReactions` (`:167`) and `handleFiles` (`:219`).
- The product handlers' own batch steps: `handleAIBots`, `handleAIThreads`, `handlePlaybookRun` and the rest in the products' `handlers/index.ts`.

**Writes that bypass it**

Two post and thread delete paths call `database.write` directly instead of `batchRecords`: `handlers/post.ts:516` and `handlers/thread.ts:74`. They run `destroyPermanently()` on rows already fetched from the database. Those deletes don't get `batchRecords`' error handling or its corruption event. Also, the list of 232 unresolved callers from the index means I could not enumerate every caller of `batchRecords`; the list above is the resolved set.