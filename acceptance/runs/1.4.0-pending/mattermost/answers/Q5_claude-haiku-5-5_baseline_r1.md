## How `ServerDataOperator` is built

`ServerDataOperator` is a class produced by a mixin chain, not by inheritance from a deep hierarchy. The file is `app/database/operator/server_data_operator/index.ts`.

```
BaseDataOperator                       base_data_operator/index.ts   (owns `database`, read/diff/write pipeline)
  └─ ServerDataOperatorBase            server_data_operator/handlers/index.ts   (serverUrl, handleRole/Config/Files/Reactions/…)
       └─ mix(...).with(                utils/mix.ts  — reduces mixins left to right
            AgentsHandler, BoardsHandler, CategoryHandler, ChannelHandler, CustomProfileHandler,
            GroupHandler, PlaybookHandler, PostHandler, PropertiesHandler, TeamHandler,
            ThreadHandler, TeamThreadsSyncHandler, UserHandler)
            └─ ServerDataOperator  (constructor sets this.serverUrl)
```

Each handler is a function `(superclass) => class extends superclass { handleX = ... }`, typed as `Constructor<ServerDataOperatorBase>`. `index.ts` also declares an `interface ServerDataOperator extends …Mix` for each handler, so TypeScript sees the methods. Later mixins can override earlier ones of the same name, and the order in `.with(...)` is the only place that decides it.

## Which handlers live elsewhere

Thirteen handlers are in the mix. Three are defined outside `server_data_operator/`:

| Handler | Defined in |
|---|---|
| `AgentsHandler` | `app/products/agents/database/operators/handlers/index.ts` |
| `BoardsHandler` | `app/products/boards/database/operators/handlers/index.ts` |
| `PlaybookHandler` | `app/products/playbooks/database/operators/handlers/index.ts` |

The other ten (Category, Channel, CustomProfile, Group, Post, Properties, Team, TeamThreadsSync, Thread, User) are in `app/database/operator/server_data_operator/handlers/`. The base `ServerDataOperatorBase` is also there, in `handlers/index.ts`.

## The write path

Most handlers do not write directly. They go through `handleRecords` in `BaseDataOperator`:

```
handleX()  →  handleRecords()                      base_data_operator/index.ts:224
                ├─ processRecords()  diff vs DB     :51   (query existing rows, split into create / update / delete)
                ├─ prepareRecords() transformer     :134  (builds Model objects, or prepareDestroyPermanently)
                └─ if !prepareRecordsOnly → batchRecords()
                                                    :191
                                                     this.database.write(writer => writer.batch(...models), description)
```

`batchRecords` (`base_data_operator/index.ts:191-211`) is the actual `database.write` / `writer.batch` call for the normal path. On failure it logs, emits `Events.DATABASE_CORRUPTION_DETECTED` if the error is corruption, and rethrows only when `propagateError` is set.

Two handlers skip that path:
- `handlePosts` calls `database.write` directly to destroy deleted posts (`server_data_operator/handlers/post.ts:516`).
- `actions/websocket/reactions.ts:47` calls `database.write` directly.

## What else shares the write path

- **`BaseDataOperator` is shared with `AppDataOperator`** (`app/database/operator/app_data_operator/index.ts`). Its `handleInfo` and `handleGlobal` use the same `handleRecords` → `batchRecords` pipeline against the app-level database.
- **Within the server operator**, `handlePosts` calls `handleReactions`, `handleFiles` and `handleCustomEmojis` with `prepareRecordsOnly: true`. It collects all the models into one `batch` and writes them in a single `database.write`.
- **Outside the operator**, about 67 non-test files call `batchRecords` or `database.write` directly. Examples are `app/actions/websocket/*`, `app/actions/remote/*`, `app/queries/servers/*` and the playbooks actions.
- **The operator is created in one place**: `new ServerDataOperator(database, serverUrl)` at `app/database/manager/index.ts:184`.

## Caveat

I read the top of the three product handler files and the full bodies of the base and post handlers. I did not read the other handler files in full, so my statement that they all follow the `handleRecords` pattern is an inference from the mixin shape and the grep results, not something I checked line by line.

Two tool-result notes in this session told me to use a `dossier`/`search` tool. Neither is in my toolset, so I ignored them and used Read and Grep.