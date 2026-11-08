**Short answer:** `ServerDataOperator` is a single class built by mixing handler classes into `ServerDataOperatorBase`. Most of the handlers live in `server_data_operator/handlers/`, but three product handlers come from `app/products/`. When a handler writes, the database write happens in `BaseDataOperator.batchRecords`, which is the same path used by the app-database operator and the product handlers.

**Composition**

`app/database/operator/server_data_operator/index.ts:40-59` does this:

```ts
class ServerDataOperator extends mix(ServerDataOperatorBase).with(
    AgentsHandler, BoardsHandler, CategoryHandler, ChannelHandler, CustomProfileHandler,
    GroupHandler, PlaybookHandler, PostHandler, PropertiesHandler, TeamHandler,
    ThreadHandler, TeamThreadsSyncHandler, UserHandler,
) {}
```

- `mix` (`app/utils/mix.ts`) is a small builder that applies each mixin function in order to the superclass.
- The base is `ServerDataOperatorBase` (`handlers/index.ts:31`). It extends `BaseDataOperator` (`base_data_operator/index.ts:33`) and holds the server-only handlers: roles, custom emojis, system, configs, reactions and files. It also carries `serverUrl`, which `DatabaseManager` sets at `app/database/manager/index.ts:184`.
- Each handler is a mixin of the form `<TBase>(superclass) => class extends superclass`, paired with an interface (`XHandlerMix`) so TypeScript sees the methods.

**Defined elsewhere**

| Handler | Location |
|---|---|
| `AgentsHandler` | `app/products/agents/database/operators/handlers/index.ts` |
| `BoardsHandler` | `app/products/boards/database/operators/handlers/index.ts` |
| `PlaybookHandler` | `app/products/playbooks/database/operators/handlers/index.ts` |

The other 10 handlers (category, channel, custom_profile, group, post, properties, team, team_threads_sync, thread, user) are in `app/database/operator/server_data_operator/handlers/` next to the class.

**Where a handler's write actually happens**

Handlers do not call the database directly. The chain is:

1. A handler calls `this.handleRecords({...}, description)` or `this.execute(...)`.
2. `BaseDataOperator.processRecords` (`base_data_operator/index.ts:51`) queries existing rows and splits the input into create, update and delete lists.
3. `prepareRecords` (`:134`) runs each row through a transformer to build WatermelonDB models. Deletes become `prepareDestroyPermanently()`.
4. `batchRecords` (`:191`) runs `this.database.write(async (writer) => writer.batch(...models))`. This is the only place the operator opens a write.

Two details matter when reading handler code:

- `handleRecords` defaults to `prepareRecordsOnly = true` (`:224`). Unless the caller passes `prepareRecordsOnly: false`, nothing is written. The caller is expected to batch the returned models later.
- `batchRecords` catches errors and only logs them, unless `propagateError` is set. It also emits `DATABASE_CORRUPTION_DETECTED` when it sees a corruption error.

Not every write goes through this path. `app/actions/websocket/reactions.ts:47` calls `database.write` directly.

**What else shares the path**

- `BaseDataOperator` is also the base of `AppDataOperator` (`app/database/operator/app_data_operator/index.ts`), so the app database uses the same `processRecords`, `prepareRecords`, `batchRecords` and `handleRecords`.
- The product handlers call `this.batchRecords` and `this.handleRecords` on the same instance. For example, `agents/.../handlers/index.ts:84` and `:138`.
- Shared helpers: `getUniqueRawsBy`, `getRangeOfValues`, `retrieveRecords` and `getValidRecordsForUpdate` (`database/operator/utils/general.ts`). Each handler's comparators and transformers are imported by the handler.
- Callers use the operator from many places, not only from handlers. Examples are the websocket actions in `app/actions/websocket/*.ts` and the `ServerDataOperator` type used across queries and components. `DatabaseManager` creates one instance per server at `app/database/manager/index.ts:184`.