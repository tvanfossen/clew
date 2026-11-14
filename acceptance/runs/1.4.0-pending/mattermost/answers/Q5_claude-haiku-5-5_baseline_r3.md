## How `ServerDataOperator` is built

`ServerDataOperator` (`app/database/operator/server_data_operator/index.ts:40`) is a mixin composition, not a hand-written class. `ServerDataOperatorBase` is the root, and each handler is a mixin that wraps it:

```
BaseDataOperator               base_data_operator/index.ts      (database ref, processRecords, prepareRecords, batchRecords, handleRecords)
  └─ ServerDataOperatorBase    server_data_operator/handlers/index.ts  (handleRole, handleConfigs, handleReactions, handleFiles, execute, serverUrl)
       └─ mix(...).with(…13 mixins…)   utils/mix.ts  (reduce: each mixin(c) wraps the previous class)
            └─ ServerDataOperator
```

- `utils/mix.ts` is a small `MixinBuilder` that folds the mixins over the base class in order.
- Each handler is `const XHandler = <TBase extends Constructor<ServerDataOperatorBase>>(superclass) => class extends superclass {...}`, plus an exported `XHandlerMix` interface.
- The `interface ServerDataOperator extends …Mix` declaration merges those interfaces so TypeScript sees every handler method on the class.
- `DatabaseManager` builds it at `app/database/manager/index.ts:184` as `new ServerDataOperator(database, serverUrl)`.

## Which handlers live elsewhere

Ten handlers are in `server_data_operator/handlers/` next to the class: Category, Channel, CustomProfile, Group, Post, Properties, Team, TeamThreadsSync, Thread, User.

Three are defined in product folders and imported through path aliases:

| Mixin | Defined in |
|---|---|
| `AgentsHandler` | `app/products/agents/database/operators/handlers/index.ts` |
| `BoardsHandler` | `app/products/boards/database/operators/handlers/index.ts` |
| `PlaybookHandler` | `app/products/playbooks/database/operators/handlers/index.ts` |

## Where a handler's write actually happens

Most handlers follow this path:

```
handleX(args)
  → this.handleRecords(...)                    base_data_operator:224
      → processRecords()                       query existing rows; split into create / update / delete
      → prepareRecords()                       transformer per raw; prepareDestroyPermanently() for deletes
      → batchRecords(models) if !prepareRecordsOnly
          → this.database.write(writer => writer.batch(...models))   base_data_operator:191-196
```

The real database write is `BaseDataOperator.batchRecords` at `app/database/operator/base_data_operator/index.ts:191`. It is the only place in the operator layer that calls `database.write` and `writer.batch`. On failure it logs a warning, emits `DATABASE_CORRUPTION_DETECTED` if the error is a corruption error, and swallows the error unless `propagateError` is true.

Handlers called with `prepareRecordsOnly: true` return the models without writing. The caller can then batch several handlers' output into one transaction.

## What else shares that write

- Base-class methods: `handleFiles` and `handleReactions` in `ServerDataOperatorBase`, plus `execute()`. All call `batchRecords`.
- Product handlers: `AgentsHandler` and `PlaybookHandler` call `this.batchRecords` at the end of their handlers.
- Outside the handler classes: websocket and action code calls `operator.batchRecords` directly, for example `app/actions/websocket/category.ts:93` and `app/products/playbooks/actions/websocket/runs.ts:111`.

Some code writes around the operator. The playbooks local actions (`actions/local/checklist.ts`, `run.ts`, `version.ts`, `channel.ts`) call `database.write(...)` themselves, so they don't go through `batchRecords`, and they won't get its corruption-event handling.

Because `batchRecords` swallows errors by default, a caller that needs to know whether the write failed has to pass `propagateError = true`.

Note: tool output twice suggested a `dossier` tool that isn't in my toolset, so I used Read and Grep for this.