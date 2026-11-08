**How `ServerDataOperator` is built**

`app/database/operator/server_data_operator/index.ts` does two things:

- **Type-level:** `interface ServerDataOperator extends …Mix` (lines 23–38) merges the method types of 14 handler mixins into the class, so TypeScript sees every handler method on the instance.
- **Runtime:** `class ServerDataOperator extends mix(ServerDataOperatorBase).with(...)` (lines 40–54) applies 13 mixins in order. `mix` (`app/utils/mix.ts`) is a small builder that reduces the mixin functions over the base class. The constructor (lines 55–58) calls `super(database)` and stores `serverUrl`.

The base is `ServerDataOperatorBase` (`server_data_operator/handlers/index.ts`), which extends `BaseDataOperator`. It holds the shared logic: `handleRole`, `handleCustomEmojis`, `handleSystem`, `handleConfigs`, `handleReactions`, `handleFiles`, and `execute`.

**Where the handlers live**

Ten handlers are defined next to the class in `server_data_operator/handlers/`: Category, Channel, CustomProfile, Group, Post, Properties, Team, TeamThreadsSync, Thread, and User.

Three are defined elsewhere, in product folders:

| Handler | File |
|---|---|
| `AgentsHandler` | `app/products/agents/database/operators/handlers/index.ts` |
| `BoardsHandler` | `app/products/boards/database/operators/handlers/index.ts` |
| `PlaybookHandler` | `app/products/playbooks/database/operators/handlers/index.ts` |

Each is a mixin factory of the form `(superclass) => class extends superclass`, with arrow-function methods such as `handleAIBots`, `handleBoardViews`, and `handlePlaybookRun`.

**Where a handler's write actually happens**

Every handler funnels into one function, `BaseDataOperator.batchRecords` (`app/database/operator/base_data_operator/index.ts:191`). The chain is:

```
handleX(...)                       (handler mixin, any file)
  └─ handleRecords / execute       (base_data_operator:224, server handlers/index.ts:234)
       ├─ processRecords           diff raw input against existing rows → create / update / delete
       ├─ prepareRecords           transformer builds prepareCreate / prepareUpdate / prepareDestroyPermanently
       └─ batchRecords             (only if prepareRecordsOnly is false)
            └─ database.write(writer => writer.batch(...models))   ← the actual DB write
```

Some handlers also write in their own bodies, e.g. `thread.ts:74` and `post.ts:516` call `database.write` directly.

**What else shares that write path**

- **All handlers, including the three product handlers,** reach it through `handleRecords`, `execute`, or the `handleFiles`/`handleReactions` paths that call `batchRecords` directly.
- **`AppDataOperator`** (`app/database/operator/app_data_operator/index.ts:15`) extends `BaseDataOperator`, so it shares `batchRecords` and `handleRecords` for the app-level database.
- **Error handling is shared too.** `batchRecords` catches errors and logs them, and only rethrows when `propagateError` is true. On a corruption error it emits `Events.DATABASE_CORRUPTION_DETECTED`. Handler callers therefore don't see write failures unless they opt in.
- **Outside the operators,** about 40 non-test files call `database.write` directly, bypassing the operator. Examples include `app/actions/local/post.ts`, `app/actions/remote/post.ts`, `app/queries/servers/entry.ts`, and `app/database/manager/index.ts`. Those writes don't go through `batchRecords` and don't get its error handling or corruption event.

I did not verify the `propagateError` callers or the full list of `batchRecords` callers beyond the ones shown; the index capped the caller list at 25 of 32.