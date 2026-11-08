**Short answer:** `ServerDataOperator` is a mixin chain on top of `ServerDataOperatorBase`. Only the base's `batchRecords` (in `BaseDataOperator`) calls `database.write`, and the app-database operator shares it.

**How the class is built**

`app/database/operator/server_data_operator/index.ts` does `mix(ServerDataOperatorBase).with(...)`. `app/utils/mix.ts` reduces over the mixins, so each one wraps the previous class as a subclass. The file also declares an interface that merges every `*HandlerMix` type, which is what gives callers typed access to `handleX` methods.

```
BaseDataOperator          base_data_operator/index.ts      (DB plumbing)
  └─ ServerDataOperatorBase   server_data_operator/handlers/index.ts
       └─ + AgentsHandler, BoardsHandler, CategoryHandler, ChannelHandler,
            CustomProfileHandler, GroupHandler, PlaybookHandler, PostHandler,
            PropertiesHandler, TeamHandler, ThreadHandler,
            TeamThreadsSyncHandler, UserHandler
            = ServerDataOperator  (constructor takes database + serverUrl)
```

`DatabaseManager.createServerDatabase` (`app/database/manager/index.ts:184`) is the only place it is constructed.

**Handlers defined elsewhere**

Ten handlers live in `app/database/operator/server_data_operator/handlers/` (category, channel, custom_profile, group, post, properties, team, team_threads_sync, thread, user). Three live in product folders:

| Mixin | File |
|---|---|
| `AgentsHandler` | `app/products/agents/database/operators/handlers/index.ts` |
| `BoardsHandler` | `app/products/boards/database/operators/handlers/index.ts` |
| `PlaybookHandler` | `app/products/playbooks/database/operators/handlers/index.ts` |

The `ServerDataOperatorBase` base class is in the same folder as the core handlers, but it is not a mixin. It supplies `handleRole`, `handleCustomEmojis`, `handleSystem`, `handleConfigs`, `handleReactions`, `handleFiles`, and `execute`.

**Where a handler's write actually happens**

Handlers never call `database.write` themselves. Most go through `handleRecords` or `processRecords`/`prepareRecords`, and some call `this.batchRecords` directly (post.ts does this about 19 times). The chain:

1. `handleRecords` (`base_data_operator/index.ts:224`) calls `processRecords`, which queries existing rows and splits the input into create, update, and delete lists.
2. `prepareRecords` (`:134`) runs each item through a transformer to build WatermelonDB models. Deletes become `prepareDestroyPermanently()`.
3. `batchRecords` (`:191`) is the only function that writes. It does `this.database.write(async writer => writer.batch(...models))`. On error it logs, emits `DATABASE_CORRUPTION_DETECTED` if the error is a corruption error, and rethrows only when `propagateError` is set.

Note that `prepareRecordsOnly` defaults to `true` in `handleRecords`, so many handlers return prepared models without writing. The caller has to pass `false` or call `batchRecords` itself.

**What else shares that write path**

- `AppDataOperator` (`app/database/operator/app_data_operator/index.ts`) extends `BaseDataOperator` directly. Its `handleInfo` and `handleGlobal` use the same `handleRecords` → `batchRecords` path against the global app database.
- Inside `ServerDataOperatorBase`, `handleReactions`, `handleFiles`, and `execute` all reuse `prepareRecords` and `batchRecords`.
- The product mixins (agents, playbooks) call `this.batchRecords` directly, as do many post.ts methods.
- `DatabaseManager` has its own `database.write` calls (`app/database/manager/index.ts`, around lines 232–473). Those are manager-level operations and do not go through the operator.

I did not check whether the mixin application order has any override behavior when two mixins define the same method name.