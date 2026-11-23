## How `ServerDataOperator` is built

`ServerDataOperator` (`app/database/operator/server_data_operator/index.ts`) is a class assembled from mixins:

```
BaseDataOperator                          app/database/operator/base_data_operator/index.ts
  └─ ServerDataOperatorBase               server_data_operator/handlers/index.ts
       └─ + AgentsHandler, BoardsHandler, CategoryHandler, ChannelHandler, CustomProfileHandler,
            GroupHandler, PlaybookHandler, PostHandler, PropertiesHandler, TeamHandler,
            ThreadHandler, TeamThreadsSyncHandler, UserHandler
          applied with mix(...).with(...)  (app/utils/mix.ts, a reduce over mixin functions)
```

Each mixin is a function `superclass => class extends superclass { handleX = ... }`. Each file also exports a `XHandlerMix` interface, and `index.ts` merges those interfaces into `ServerDataOperator` so TypeScript sees every `handleX` method. The constructor takes `(database, serverUrl?)` and sets `serverUrl`, which the base class declares.

## Which handlers live elsewhere

Most handlers are in `server_data_operator/handlers/` next to the index. Three are imported from product folders:

| Mixin | Defined in |
|---|---|
| `AgentsHandler` | `app/products/agents/database/operators/handlers/index.ts` |
| `BoardsHandler` | `app/products/boards/database/operators/handlers/index.ts` |
| `PlaybookHandler` | `app/products/playbooks/database/operators/handlers/index.ts` |

The base `ServerDataOperatorBase` (`handlers/index.ts`) also holds some shared handlers, such as `handleRole`, `handleCustomEmojis`, `handleSystem`, `handleConfigs`, `handleReactions`, and `handleFiles`.

## Who performs the database write

The write is not done in the handlers. They build models and hand them to a shared function:

1. **Handler** (e.g. `handleAIBots`, `handleBoardViews`, `handleReactions`) turns raw API data into records.
2. **`handleRecords` / `processRecords` / `prepareRecords`** (`base_data_operator/index.ts`) diff incoming raws against existing rows. They produce create and update pairs, call the table's transformer (`prepareCreate`/`prepareUpdate`, which do not write), and call `prepareDestroyPermanently()` for deletes. Nothing is persisted yet.
3. **`batchRecords(models, description)`** (`base_data_operator/index.ts`, around line 191) is the actual write. It calls `this.database.write(async writer => writer.batch(...models), description)`. Failures are logged with `logWarning`. Database-corruption errors also emit `Events.DATABASE_CORRUPTION_DETECTED`. It only rethrows if `propagateError` is true, and by default it does not.

Handlers take a `prepareRecordsOnly` flag. When it is true, they return the models without calling `batchRecords`, so the caller can combine them into one batch.

## What else shares that write path

- **All server handlers.** Every in-tree and product handler calls `this.batchRecords` or `this.handleRecords`. Examples are the reaction, file, property, group, post-scheduling, and channel-bookmark paths.
- **`AppDataOperator`** (`app/database/operator/app_data_operator/index.ts`) extends `BaseDataOperator` directly, so it shares `batchRecords` and the diff/prepare helpers but not the server-only handlers.
- **Direct callers outside the operator.** `app/products/playbooks/actions/websocket/runs.ts` and `actions/local/property_fields.ts` call `operator.batchRecords` themselves.
- **Bypasses.** Playbook local actions in `app/products/playbooks/actions/local/*.ts` call `database.write(...)` directly and do not go through `batchRecords`. That means they skip the corruption-event handling and the error swallowing. This is the one inconsistency I noticed.

I did not trace the callers of `ServerDataOperatorBase.execute`, so I can't say how widely it is used.