## How `ServerDataOperator` is built

`ServerDataOperator` is a class produced by mixin composition, not inheritance from one large class. It is defined at `app/database/operator/server_data_operator/index.ts:40`:

```ts
class ServerDataOperator extends mix(ServerDataOperatorBase).with(
    AgentsHandler, BoardsHandler, CategoryHandler, ChannelHandler, CustomProfileHandler,
    GroupHandler, PlaybookHandler, PostHandler, PropertiesHandler, TeamHandler,
    ThreadHandler, TeamThreadsSyncHandler, UserHandler,
) { constructor(database, serverUrl?) { super(database); this.serverUrl = serverUrl; } }
```

- **Root:** `ServerDataOperatorBase` (`handlers/index.ts:31`) extends `BaseDataOperator` (`app/database/operator/base_data_operator/index.ts:33`). It holds the generic handlers: roles, custom emojis, system, configs, reactions, files, and `execute`.
- **Mixins:** `mix()` (`app/utils/mix.ts`) reduces the list of mixin factories over the base class. Each handler is a factory of the form `const XHandler = <TBase extends Constructor<ServerDataOperatorBase>>(superclass) => class extends superclass {...}`.
- **Typing:** `mix()` is untyped (`any[]`), so `index.ts:23` declares `interface ServerDataOperator extends ...HandlerMix {}`. Each `XHandlerMix` interface supplies the method signatures for TypeScript.

## Where the handlers live

**Defined in `app/database/operator/server_data_operator/handlers/`** (next to the class): category, channel, custom_profile, group, post, properties, team, team_threads_sync, thread, user, plus the base in `index.ts`.

**Defined elsewhere (product modules):**

| Handler | File |
|---|---|
| `AgentsHandler` | `app/products/agents/database/operators/handlers/index.ts` |
| `BoardsHandler` | `app/products/boards/database/operators/handlers/index.ts` |
| `PlaybookHandler` | `app/products/playbooks/database/operators/handlers/index.ts` |

They are imported through the `@agents`, `@boards`, and `@playbooks` path aliases and follow the same mixin shape, extending `ServerDataOperatorBase`.

## Who performs the database write

Handlers don't write directly. The path is:

1. **Diff and prepare.** Handlers call `handleRecords` (`base_data_operator/index.ts:224`), which calls `processRecords` (line 51) to decide creates, updates, and deletes against existing rows. It then calls `prepareRecords` (line 134), which runs the transformer for each raw value to build WatermelonDB models. Deletes become `prepareDestroyPermanently()`.
2. **Commit.** If `prepareRecordsOnly` is false, the models go to `batchRecords` (`base_data_operator/index.ts:191`). That method calls `this.database.write(async (writer) => writer.batch(...models), description)`. This is the actual database write.
3. **Error handling.** `batchRecords` catches errors and logs them. If the error is a corruption error, it emits `DATABASE_CORRUPTION_DETECTED`. It rethrows only when `propagateError` is set.

Note that `prepareRecordsOnly` defaults to `true` in `handleRecords` and in most handlers. Nothing is written unless the caller passes `false`, or collects prepared models and commits them in one batch.

**What else shares the write path:**
- `batchRecords` is the common write point for every `BaseDataOperator` subclass. That includes `ServerDataOperatorBase.execute`, `handleReactions`, and `handleFiles`, the generic `handleRecords`, the agents, playbooks, and boards handlers, and many methods in `post.ts` and `thread.ts`.
- `AppDataOperator` (`app/database/operator/app_data_operator/index.ts:15`) extends `BaseDataOperator` directly. It shares `batchRecords`, `prepareRecords`, and `processRecords`, but has none of the handler mixins. It operates on the global app database.

**Two exceptions bypass `batchRecords`:**
- `post.ts:516` calls `database.write` directly to destroy deleted posts.
- `thread.ts:74` calls `database.write` directly to destroy deleted threads and their `threadsInTeam` and `participants` children.

Those writes skip the logging and corruption-event handling in `batchRecords`.

The operator is constructed in `app/database/manager/index.ts:184`, which also sets `serverUrl`.