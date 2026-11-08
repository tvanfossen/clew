**The class composition**

`ServerDataOperator` is declared in `app/database/operator/server_data_operator/index.ts`. It is a class built with the repo's `mix(...).with(...)` helper (`app/utils/mix.ts`). Each mixin is a function that takes a superclass and returns a subclass, and `with` applies them in order. The base is `ServerDataOperatorBase`, and the constructor sets `serverUrl` after calling `super(database)`. The same file declares a merged `interface ServerDataOperator extends ...Mix` so TypeScript sees the methods that the mixins add at runtime.

The base and 11 handlers live in the same folder, `server_data_operator/handlers/`:

- `index.ts` (`ServerDataOperatorBase`): roles, custom emojis, system, configs, reactions, files, and the generic `execute`.
- `category`, `channel`, `custom_profile`, `group`, `post`, `properties`, `team`, `team_threads_sync`, `thread`, `user`.

Three handler sets are defined elsewhere, in product folders:

| Handler | Defined in |
|---|---|
| `AgentsHandler` / `AgentsHandlerMix` | `app/products/agents/database/operators/handlers/index.ts` |
| `BoardsHandler` / `BoardsHandlerMix` | `app/products/boards/database/operators/handlers/index.ts` |
| `PlaybookHandler` / `PlaybookHandlerMix` | `app/products/playbooks/database/operators/handlers/index.ts` |

**Where the database write happens**

Handlers never call WatermelonDB's `write` themselves for ordinary upserts. The chain is:

1. A handler calls `handleRecords`, `processRecords`, `prepareRecords`, or `execute`. These are defined in `BaseDataOperator` (`app/database/operator/base_data_operator/index.ts`), and `ServerDataOperatorBase` extends it.
2. `processRecords` queries existing rows and splits the input into create, update, and delete lists.
3. `prepareRecords` runs each transformer to build unsaved WatermelonDB models. Deletes become `prepareDestroyPermanently()`. Nothing is written yet.
4. `batchRecords` (`base_data_operator/index.ts:191`) performs the write: `this.database.write(async (writer) => writer.batch(...models))`. It also logs failures and emits `DATABASE_CORRUPTION_DETECTED` on corruption errors. It only rethrows when `propagateError` is true.

`handleRecords` only calls `batchRecords` when `prepareRecordsOnly` is false. It defaults to `true`, so callers have to opt in to a write. `handleFiles`, `handleReactions`, and `execute` follow the same pattern.

**What else shares that write path**

- `AppDataOperator` (`app/database/operator/app_data_operator/index.ts`) extends `BaseDataOperator`, so the app-level database uses the same `batchRecords` and `handleRecords` code.
- Every mixin handler above, including the agents, boards, and playbooks handlers, reaches the write through the inherited `batchRecords`.
- Outside the operator tree, ephemeral-mode cleanup (`app/actions/local/ephemeral_mode/cleanup.ts`) calls `batchRecords` directly.
- Some code bypasses `batchRecords` and opens its own `database.write`. Examples are the delete branches in `handlers/post.ts:516` and `handlers/thread.ts:74`, and many actions and queries under `app/actions/` and `app/queries/`. These skip the error handling and corruption detection in `batchRecords`.