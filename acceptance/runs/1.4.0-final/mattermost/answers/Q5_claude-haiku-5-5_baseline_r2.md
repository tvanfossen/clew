## How `ServerDataOperator` is built

`ServerDataOperator` (`app/database/operator/server_data_operator/index.ts:40`) is a runtime mixin chain:

```
ServerDataOperatorBase                     (handlers/index.ts:31)
  └─ AgentsHandler                         (products/agents/database/operators/handlers/index.ts)
     └─ BoardsHandler                      (products/boards/database/operators/handlers/index.ts)
        └─ CategoryHandler                 (handlers/category.ts)
           └─ ChannelHandler               (handlers/channel.ts)
              └─ CustomProfileHandler      (handlers/custom_profile.ts)
                 └─ GroupHandler           (handlers/group.ts)
                    └─ PlaybookHandler     (products/playbooks/database/operators/handlers/index.ts)
                       └─ PostHandler      (handlers/post.ts)
                          └─ PropertiesHandler (handlers/properties.ts)
                             └─ TeamHandler    (handlers/team.ts)
                                └─ ThreadHandler (handlers/thread.ts)
                                   └─ TeamThreadsSyncHandler (handlers/team_threads_sync.ts)
                                      └─ UserHandler (handlers/user.ts)
                                         = ServerDataOperator
```

- **Mechanism:** `mix(...)` in `app/utils/mix.ts` is a `reduce` that applies each mixin function to the previous class, so each handler is a subclass of the one before it. Each handler is `const X = (superclass) => class extends superclass { ...arrow methods }`.
- **Types:** the `interface ServerDataOperator extends ...HandlerMix` block (lines 23–38) merges each mixin's method signatures into the class type. The mixin itself does not carry type information.
- **Base class:** `ServerDataOperatorBase` (`handlers/index.ts`) holds the shared logic. It defines `handleRole`, `handleCustomEmojis`, `handleSystem`, `handleConfigs`, `handleReactions`, `handleFiles`, and `execute`, and it extends `BaseDataOperator` (`base_data_operator/index.ts`). It also has a `serverUrl` field set by the constructor.

### Defined elsewhere (not next to it)

Three of the 13 mixins live in product folders, not in `server_data_operator/handlers/`:

| Mixin | Location |
|---|---|
| `AgentsHandler` | `app/products/agents/database/operators/handlers/index.ts` |
| `BoardsHandler` | `app/products/boards/database/operators/handlers/index.ts` |
| `PlaybookHandler` | `app/products/playbooks/database/operators/handlers/index.ts` |

The other 10 are in `app/database/operator/server_data_operator/handlers/`. The product handlers import the base type from there, so the dependency runs one way.

### Construction

`DatabaseManager` creates it per server at `app/database/manager/index.ts:184` with `new ServerDataOperator(database, serverUrl)`. The App database uses `AppDataOperator`, which extends `BaseDataOperator` directly and does not get these handlers.

## The write path

Most handlers do not write directly. They call `handleRecords` or `prepareRecords`, then `batchRecords`:

```
handler (e.g. handleAIBots)
  └─ this.handleRecords(...)                    base_data_operator:224
       ├─ processRecords()    query existing rows by fieldName, split into create/update/delete
       ├─ prepareRecords()    transformer per row; deletes via prepareDestroyPermanently()
       └─ if !prepareRecordsOnly → batchRecords()
                                                base_data_operator:191
            └─ this.database.write(writer => writer.batch(...models))   ← the actual write
```

- **The actual write** is `BaseDataOperator.batchRecords` (`app/database/operator/base_data_operator/index.ts:191–211`). It calls WatermelonDB's `database.write` and `writer.batch`.
- **Error handling:** it catches errors and logs a warning. If the error is a database corruption error, it emits `Events.DATABASE_CORRUPTION_DETECTED`. It rethrows only when `propagateError` is true, which is not the default. Callers therefore do not see write failures unless they opt in.
- **Shared by:** every `this.batchRecords(...)` call in the handlers (for example `post.ts`, `thread.ts`, `group.ts`, `properties.ts`, `user.ts`, and the three product mixins). `ServerDataOperatorBase.execute` and `handleRecords` also go through it. The `prepareRecordsOnly` flag lets a caller collect models from several handlers and write them in one batch.
- **Also shared:** the transformers, comparators, and `prepareDestroyPermanently` helpers used upstream in the same flow.

## Writes that bypass `batchRecords`

Not every write goes through this path. Some handlers and most actions call `database.write` directly, for example:

- `thread.ts:74` (destroying threads and their children)
- `post.ts:516` (destroying posts)
- `app/actions/*` and `app/queries/servers/*`

These skip the `batchRecords` error handling, so they can throw. The `propagateError=false` default applies only to `batchRecords`.