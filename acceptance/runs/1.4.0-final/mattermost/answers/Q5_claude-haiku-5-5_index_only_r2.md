**How `ServerDataOperator` is built**

`ServerDataOperator` (`app/database/operator/server_data_operator/index.ts:40`) is a class made by mixing handler mixins onto a base class:

```ts
class ServerDataOperator extends mix(ServerDataOperatorBase).with(
    AgentsHandler, BoardsHandler, CategoryHandler, ChannelHandler,
    CustomProfileHandler, GroupHandler, PlaybookHandler, ...
)
```

- The base is `ServerDataOperatorBase` (`handlers/index.ts:31`), which extends `BaseDataOperator`. It holds `serverUrl`, the shared `execute`, and generic handlers such as `handleRole`, `handleCustomEmojis`, `handleReactions`, and `handleFiles`.
- Each handler is a mixin: `const X = <TBase extends Constructor<ServerDataOperatorBase>>(superclass) => class extends superclass {...}`. `index.ts:23` also declares an `interface ServerDataOperator extends ...Mix` so TypeScript sees the methods.

**Handlers defined elsewhere**

| Handler | Defined in |
|---|---|
| `AgentsHandler` | `app/products/agents/database/operators/handlers/index.ts:35` |
| `BoardsHandler` | `app/products/boards/database/operators/handlers/index.ts:24` |
| `PlaybookHandler` | `app/products/playbooks/database/operators/handlers/index.ts:57` |

The other handlers live in `app/database/operator/server_data_operator/handlers/`. I confirmed `PostHandler` (`post.ts:253`) and `UserHandler` (`user.ts:30`) directly. The index lists `CategoryHandler`, `ChannelHandler`, `CustomProfileHandler`, `GroupHandler`, `PropertiesHandler`, `TeamHandler`, `TeamThreadsSyncHandler`, and `ThreadHandler` under that same folder, but I did not dossier each one.

**Which code performs the database write**

Handlers never call the database directly. The path is:

1. A handler (e.g. `PostHandler.handlePosts`, `UserHandler.handleUsers`) builds records. Its private helpers, or `ServerDataOperatorBase.execute` (`handlers/index.ts:234`), call `prepareRecords`, which returns prepared Model objects.
2. `execute` then calls `this.batchRecords(models, description)`.
3. `BaseDataOperator.batchRecords` (`app/database/operator/base_data_operator/index.ts:191-211`) is the actual write. It runs `this.database.write(async (writer) => writer.batch(...models), description)`. Failures are logged with `logWarning`. If the error is a database corruption error, it emits `Events.DATABASE_CORRUPTION_DETECTED`. It rethrows only when `propagateError` is true.

**What else shares `batchRecords`**

- **Every `ServerDataOperator` handler** that writes. The index lists callers in `PostHandler` (about 10 methods, including `handlePosts`, `handleScheduledPosts`, and the `handleReceivedPostsIn*` family), `ServerDataOperatorBase.execute`, `handleFiles`, `handleReactions`, `AgentsHandler` (`handleAIBots`, `handleAIThreads`), `ChannelHandler.handleChannelBookmark`, `GroupHandler`, `PlaybookHandler`, `UserHandler.handlePreferences`, and `PropertiesHandler`. The index reports 32 callers in total but only lists 25, so the list is incomplete.
- **`AppDataOperator`**, which also extends `BaseDataOperator` (the app database, not the server database).
- **The ephemeral-mode cleanup code** in `app/actions/local/ephemeral_mode/cleanup.ts` (`cleanupAiThreads`, `cleanupPlaybookRuns`, `autoCacheCleanup`). These show up as `batchRecords` nodes with no body, so I could not confirm they call the base method directly. Treat that as likely, not verified.
- The `BaseDataOperatorType` interface (`base_data_operator/index.ts:29`) also declares `batchRecords`.

**Caveats:** Everything above comes from the clew index. I did not read the source files, and the handler list for the non-product mixins is based on the index's derived-class list rather than a check of each file.