## How `ServerDataOperator` is built

`ServerDataOperator` is a mixin composition, not a subclass hierarchy. `app/database/operator/server_data_operator/index.ts:40-59` does:

```ts
class ServerDataOperator extends mix(ServerDataOperatorBase).with(
    AgentsHandler, BoardsHandler, CategoryHandler, ..., UserHandler,
) {
    constructor(database, serverUrl?) { super(database); this.serverUrl = serverUrl; }
}
```

- **Base:** `ServerDataOperatorBase` (`handlers/index.ts:31`) extends `BaseDataOperator` (`base_data_operator/index.ts:33`). It holds `handleRole`, `handleCustomEmojis`, `handleSystem`, `handleConfigs`, `handleReactions`, `handleFiles` and `execute`.
- **Mixins:** each handler is `const XHandler = (superclass) => class extends superclass {...}`, paired with an `export interface XHandlerMix`.
- **`mix()`** (`app/utils/mix.ts`) folds the list left to right, so each mixin wraps the previous result.
- **Typing:** the `interface ServerDataOperator extends ...Mix` declaration at lines 23-38 merges every mixin's methods into the type.

## Which handlers are defined elsewhere

| Handler | Location |
|---|---|
| `AgentsHandler` | `app/products/agents/database/operators/handlers/index.ts` |
| `BoardsHandler` | `app/products/boards/database/operators/handlers/index.ts` |
| `PlaybookHandler` | `app/products/playbooks/database/operators/handlers/index.ts` |

The other ten are in `app/database/operator/server_data_operator/handlers/`: category, channel, custom_profile, group, post, properties, team, team_threads_sync, thread and user.

## Where a handler's write actually happens

```
handleX()  (handler mixin)
  └─ handleRecords()                      base_data_operator/index.ts:224
       ├─ processRecords()                dedupe against DB
       ├─ prepareRecords()                transformer → prepareCreate/prepareUpdate;
       │                                  deletes → prepareDestroyPermanently
       └─ batchRecords()  (if prepareRecordsOnly === false)
            └─ database.write(writer => writer.batch(...models))   :191-211
```

The one real write is `BaseDataOperator.batchRecords` (`base_data_operator/index.ts:191-211`). It wraps `writer.batch(...)` in `this.database.write`. On error it logs with `logWarning`. If the error is a database corruption, it emits `DATABASE_CORRUPTION_DETECTED`. It rethrows only when `propagateError` is true.

Two details matter when reading handler code:

- `handleRecords` defaults to `prepareRecordsOnly = true`, so it returns prepared models without writing. Callers that want a write must pass `false`, or batch the returned models themselves in a larger transaction.
- `execute`, `handleFiles` and `handleReactions` in the base class call `batchRecords` directly after preparing.

## What else shares the write path

- **Other operators:** `AppDataOperator` extends `BaseDataOperator`, so the app database writes through the same function.
- **Base-class methods:** `handleFiles`, `handleReactions` and `execute` in `ServerDataOperatorBase`, plus the `PostHandler` and `ThreadHandler` methods that use `prepareRecords`.
- **Cleanup code:** `app/actions/local/ephemeral_mode/cleanup.ts` (lines 201, 219, 272) calls `operator.batchRecords` through a structurally typed parameter, not through the class.

Not every write goes through `batchRecords`. Some code calls `database.write` directly:

- `handlers/post.ts:516`, which destroys deleted posts
- `handlers/thread.ts:74`
- `app/products/playbooks/actions/local/*.ts`
- `app/database/manager/index.ts`

The caller list came from the index, which left 232 callers unresolved, so the list may be incomplete. The direct-write sites above are from grep, not from the index.