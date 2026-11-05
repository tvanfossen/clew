**Short answer:** `ServerDataOperator` is a mixin composition. Ten of its thirteen handler mixins live in `server_data_operator/handlers/`, and three live in product folders. Every handler write funnels through `BaseDataOperator.batchRecords`, which is the single `database.write(...)` call. `AppDataOperator` shares that same code.

**How the class is built**

- `app/database/operator/server_data_operator/index.ts:40` declares `class ServerDataOperator extends mix(ServerDataOperatorBase).with(...)`, mixing in 13 handler classes. The interface at `index.ts:23` merges in the matching `*HandlerMix` types so TypeScript knows the methods exist.
- `ServerDataOperatorBase` (`handlers/index.ts:31`) is the mix base. It extends `BaseDataOperator` (`base_data_operator/index.ts:33`) and holds the generic handlers: `handleRole`, `handleFiles`, `handleReactions`, `handleConfigs`, `handleCustomEmojis`, `handleSystem`, and `execute`.
- Each handler is a mixin function of the form `const XHandler = <TBase extends Constructor<ServerDataOperatorBase>>(superclass) => class extends superclass {...}`.

**Handlers defined elsewhere**

| Handler | Defined in |
|---|---|
| `AgentsHandler` | `app/products/agents/database/operators/handlers/index.ts` |
| `BoardsHandler` | `app/products/boards/database/operators/handlers/index.ts` |
| `PlaybookHandler` | `app/products/playbooks/database/operators/handlers/index.ts` |

The other ten (Category, Channel, CustomProfile, Group, Post, Properties, Team, TeamThreadsSync, Thread, User) sit in `server_data_operator/handlers/` as sibling files. The index's `dossier` output truncated the mix list, so I read `index.ts` directly to confirm this set.

**The write path**

Using `handleUsers` (`handlers/user.ts:116`) as the example:

```
handleUsers                       user.ts:116
  └─ handleRecords                base_data_operator:224
       ├─ processRecords          base:51   (reads existing rows, splits create/update/delete)
       ├─ prepareRecords          base:134  (runs transformer, builds models, NO write)
       └─ batchRecords            base:191  (only if prepareRecordsOnly is false)
            └─ database.write(writer => writer.batch(...models))   ← the actual write
```

- `batchRecords` catches errors, logs a warning, and emits `DATABASE_CORRUPTION_DETECTED` on corruption errors. It rethrows only when `propagateError` is set.
- `prepareRecordsOnly` defaults to `true` in `handleRecords`. `handleUsers` therefore returns prepared models without writing unless the caller passes `prepareRecordsOnly: false` or batches them later. This is easy to miss.

**What else shares the write code**

- **Other handlers.** Most handlers in the list above call `batchRecords` or `handleRecords` directly. `ServerDataOperatorBase.execute` (`handlers/index.ts`) is a shared wrapper for prepare-then-batch.
- **Callers outside the operator.** `batchRecords` has about 233 non-test call sites across 67 files, mostly in `app/actions/remote/`, `app/actions/local/`, `app/actions/websocket/`, and `app/products/playbooks/actions/`. The test helper at `test/test_helper.ts:145` also uses it.
- **`AppDataOperator`.** It extends the same `BaseDataOperator` (`app/database/operator/app_data_operator/index.ts:15`) and inherits `batchRecords`, `processRecords`, `prepareRecords`, and `handleRecords` for the global app database.
- **Construction.** `DatabaseManager` builds the operator at `app/database/manager/index.ts:184` as `new ServerDataOperator(database, serverUrl)`.

**Exceptions:** Not every write goes through `batchRecords`. `app/actions/websocket/reactions.ts:47` calls `database.write` directly.