**Short answer:** `ServerDataOperator` is a mixin stack. Ten of its handler mixins live in `server_data_operator/handlers/`, and three live in product folders (agents, boards, playbooks). Every handler write funnels through one method, `BaseDataOperator.batchRecords`, which wraps `database.write(writer => writer.batch(...))`. `AppDataOperator` shares that base class, so it uses the same write path for the app database.

**How the class is built**

`server_data_operator/index.ts` does `mix(ServerDataOperatorBase).with(...13 mixins...)`. Each mixin is a factory `(superclass) => class extends superclass`, and `mix` applies them left to right (`app/utils/mix.ts`). The `interface ServerDataOperator extends ...HandlerMix` block merges the matching type declarations so the methods type-check. The constructor takes `(database, serverUrl?)`. `DatabaseManager` (`app/database/manager/index.ts:184`) creates one per server.

The inheritance chain is:

```
BaseDataOperator                    base_data_operator/index.ts
  └─ ServerDataOperatorBase         server_data_operator/handlers/index.ts
       └─ ServerDataOperator (mix)  server_data_operator/index.ts
```

**Where each handler is defined**

| Mixin | Location |
|---|---|
| Category, Channel, CustomProfile, Group, Post, Properties, Team, TeamThreadsSync, Thread, User | `app/database/operator/server_data_operator/handlers/` |
| Agents (`handleAIBots`, `handleAIThreads`) | `app/products/agents/database/operators/handlers/index.ts` |
| Boards | `app/products/boards/database/operators/handlers/index.ts` |
| Playbook | `app/products/playbooks/database/operators/handlers/index.ts` |

`ServerDataOperatorBase` itself holds the generic handlers: `handleRole`, `handleCustomEmojis`, `handleSystem`, `handleConfigs`, `handleReactions`, `handleFiles`, and `execute`.

**Who performs the database write**

A typical handler does not write directly. The path is:

1. `processRecords` (`base_data_operator/index.ts:51`) queries existing rows and splits the input into create, update and delete sets.
2. `prepareRecords` (`:134`) runs each set through a transformer to build WatermelonDB model objects. Deletes become `prepareDestroyPermanently()`.
3. `batchRecords` (`:191`) performs the write: `this.database.write(async (writer) => writer.batch(...models), description)`.

`handleRecords` (`:224`) chains steps 1–3. It only calls `batchRecords` when `prepareRecordsOnly` is false, and the default is `true`. Handlers that take that flag return unsaved models, and the caller decides when to commit.

`batchRecords` swallows errors by default and logs them. If the error is a corruption error, it emits `Events.DATABASE_CORRUPTION_DETECTED`. It rethrows only when `propagateError` is set.

**What else shares that write path**

- **`AppDataOperator`** extends the same `BaseDataOperator`, so `batchRecords`, `processRecords`, `prepareRecords` and `handleRecords` are shared with the app-level database.
- **Product handlers** call `this.batchRecords` (agents, playbooks, and the channel bookmark, property, group, post and thread handlers).
- **Outside the operator**, `playbooks/actions/websocket/runs.ts:111` and `playbooks/actions/local/property_fields.ts:47` call `operator.batchRecords` directly.
- **Bypassing the operator:** some code calls `database.write` or `database.batch` directly, for example `post.ts:516`, `thread.ts:74`, `queries/servers/custom_profile.ts:137`, `actions/local/systems.ts:102` and many `actions/local/*` and `actions/remote/*` files. I only saw these call sites in grep output and did not read them, so I cannot say whether each one is deliberate. Any new write that skips `batchRecords` loses its error logging and corruption detection.

I did not open the boards handler body or the `post.ts`/`thread.ts` direct-write sites. The statements about them come from file locations and grep results only.