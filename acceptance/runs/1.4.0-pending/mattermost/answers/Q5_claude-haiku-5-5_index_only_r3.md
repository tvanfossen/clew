The `ServerDataOperator` class is a mixin composition. Most of its handler pieces live beside it under `app/database/operator/server_data_operator/handlers/`, but three come from the products folders. All database writes funnel through one method in `BaseDataOperator`.

**How the class is built** (`app/database/operator/server_data_operator/index.ts:40`)

`ServerDataOperator` is declared as `class ServerDataOperator extends mix(ServerDataOperatorBase).with(AgentsHandler, BoardsHandler, CategoryHandler, ChannelHandler, CustomProfileHandler, GroupHandler, PlaybookHandler, …)`. The rest of the list is cut off in the index, but the class's bases show it also includes `PostHandler`, `PropertiesHandler`, `TeamHandler`, `TeamThreadsSyncHandler`, `ThreadHandler` and `UserHandler`. That is 13 handler mixins plus the base. `mix` is `new MixinBuilder(superclass)` from `app/utils/mix.ts`, and `.with(...)` applies each handler in turn. The interface merge at `index.ts:23` declares the matching `*HandlerMix` types, which is how TypeScript sees the handler methods on the class.

Each handler is a factory of the form `const XHandler = <TBase extends Constructor<ServerDataOperatorBase>>(superclass: TBase) => class extends superclass { … }`. The handlers all extend `ServerDataOperatorBase`, so they share its helpers.

**Handlers defined elsewhere**

| Handler | Defined in |
|---|---|
| `AgentsHandler` | `app/products/agents/database/operators/handlers/index.ts:35` |
| `BoardsHandler` | `app/products/boards/database/operators/handlers/index.ts:24` |
| `PlaybookHandler` | `app/products/playbooks/database/operators/handlers/index.ts:57` |

The other handlers (`Category`, `Channel`, `CustomProfile`, `Group`, `Post`, `Properties`, `Team`, `TeamThreadsSync`, `Thread`, `User`) sit in `server_data_operator/handlers/`. `ServerDataOperatorBase` is in `handlers/index.ts:31`, and the base itself extends `BaseDataOperator`.

**Where a handler's write actually happens**

For create/update, a handler calls `ServerDataOperatorBase.execute` (`handlers/index.ts:234`). That method does two things:

1. `this.prepareRecords({tableName, createRaws, updateRaws, transformer})`, which is `BaseDataOperator.prepareRecords` (`base_data_operator/index.ts:134`). It builds WatermelonDB model objects, but does not write them.
2. `this.batchRecords(models, description)` if there is anything to write.

The write itself is `BaseDataOperator.batchRecords` (`base_data_operator/index.ts:191`):

```ts
await this.database.write(async (writer) => {
    await writer.batch(...models);
}, description);
```

Its error handling is the rest of the path. It logs with `logWarning`. If `isDatabaseCorruptionError(e)` is true, it emits `Events.DATABASE_CORRUPTION_DETECTED` on `DeviceEventEmitter`. It rethrows only when `propagateError` is set, and that defaults to false.

Handlers reach this in two ways. Most go through `execute`. `handleReactions` and `handleFiles` in the base also call `batchRecords` directly, and so do `PostHandler` methods such as `handlePosts`, `_createPostsInChannelRecord` and `_deleteScheduledPostByIds`. Handlers that delete also call `prepareDestroyPermanently`, which the index does not show in detail.

**What else shares it**

- `AppDataOperator` (`app/database/operator/app_data_operator/index.ts:15`) extends the same `BaseDataOperator`, so the global app database uses the same `batchRecords` and `prepareRecords`.
- `prepareRecords` and `processRecords`, which de-duplicate against existing rows, are also in the base class.
- `handleRecords` in the base combines de-duplication with `prepareRecords`.

The index reports 32 callers of `batchRecords`. Only about 25 were returned, so the list above is not complete. The `batchRecords` entries under `app/actions/local/ephemeral_mode/cleanup.ts` appear as separate candidate symbols, and I did not confirm whether they call the base method.