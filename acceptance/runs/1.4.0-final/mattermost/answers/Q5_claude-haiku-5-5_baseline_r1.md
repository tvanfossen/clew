**How the class is built**

`ServerDataOperator` (`app/database/operator/server_data_operator/index.ts`) is a mixin composition, not a class with methods of its own. The base is `ServerDataOperatorBase` (`server_data_operator/handlers/index.ts`), which extends `BaseDataOperator`. The class then applies 13 handler mixins through `mix(...).with(...)` from `app/utils/mix.ts`. Each mixin is a function `(superclass) => class extends superclass {...}`, so the handlers are layered onto the base in order. A matching `interface ServerDataOperator extends ...Mix` gives TypeScript the method types. The constructor takes `(database, serverUrl)` and stores `serverUrl`. `DatabaseManager` creates it at `app/database/manager/index.ts:184`.

**Handlers defined next to it** (`server_data_operator/handlers/`): category, channel, custom_profile, group, post, properties, team, team_threads_sync, thread, user. That is 10.

**Handlers defined elsewhere** (3):

| Mixin | File |
|---|---|
| `AgentsHandler` | `app/products/agents/database/operators/handlers/index.ts` |
| `BoardsHandler` | `app/products/boards/database/operators/handlers/index.ts` |
| `PlaybookHandler` | `app/products/playbooks/database/operators/handlers/index.ts` |

They are imported through the `@agents`, `@boards` and `@playbooks` path aliases. They are typed against `ServerDataOperatorBase`, so they can call `this.handleRecords` and `this.batchRecords` like the local handlers.

**Where a handler's write actually happens**

For a typical handler such as `handleBoardViews`, the path is:

```
handler (e.g. handleBoardViews)
  └─ this.handleRecords({...}, description)        base_data_operator/index.ts
       ├─ processRecords()  query existing rows, split into create / update / delete
       ├─ prepareRecords()  transformer builds prepared models, or prepareDestroyPermanently()
       └─ if !prepareRecordsOnly → batchRecords(models, description)
            └─ database.write(writer => writer.batch(...models))   ← the actual DB write
```

`BaseDataOperator.batchRecords` in `app/database/operator/base_data_operator/index.ts` is the single place a standard handler writes to the database. On failure it logs a warning and emits `DATABASE_CORRUPTION_DETECTED` for corruption errors. It rethrows only if `propagateError` is set.

Some handlers skip this path:
- `post.ts:516` and `thread.ts:74` call `database.write(...)` directly to run `destroyPermanently()` on deleted posts and threads.
- `ServerDataOperatorBase.handleReactions` and the thread-participant handler build their own batch and then call `batchRecords` themselves.
- `handleAIBots` in the agents mixin reads the collection directly to diff against existing records.

**What else shares it**

- **`batchRecords`, `handleRecords`, `processRecords`, `prepareRecords`, `execute`**: these come from `BaseDataOperator`, which `AppDataOperator` also extends (`app_data_operator/index.ts`). So the app-level database shares the same write pipeline, but none of the server handlers.
- **`batchRecords` and `handleRecords` across mixins**: every local and product handler calls the same two methods. The only shared write path is `batchRecords`; the `database.write` calls above are the exceptions.
- **Mock manager**: `app/database/manager/__mocks__/index.ts:139` constructs the same class for tests.