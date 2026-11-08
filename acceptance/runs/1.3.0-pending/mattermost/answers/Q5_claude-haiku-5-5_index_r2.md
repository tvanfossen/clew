`ServerDataOperator` is a class built by mixin composition. Ten of its handler mixins sit next to it under `server_data_operator/handlers/`. Three come from product folders, and every handler's database write funnels through one method, `BaseDataOperator.batchRecords`.

**How the class is built**

- `app/database/operator/server_data_operator/index.ts:40` declares `class ServerDataOperator extends mix(ServerDataOperatorBase).with(...)`. The `with(...)` call applies each handler class as a mixin in order, on top of the base.
- `mix` (`app/utils/mix.ts`) is a tiny builder that reduces the mixins over the superclass.
- The `interface ServerDataOperator extends …Mix` block (lines 23–38) is declaration merging. It gives the class the typed method signatures of every mixin, since the mixin classes themselves are not visible to the type checker through the class.
- The base, `ServerDataOperatorBase` (`server_data_operator/handlers/index.ts:31`), extends `BaseDataOperator`. It owns `serverUrl` and the generic handlers: `handleRole`, `handleCustomEmojis`, `handleSystem`, `handleConfigs`, `handleReactions`, `handleFiles`, and `execute`.
- The constructor takes `(database, serverUrl)`. `DatabaseManager` creates it at `app/database/manager/index.ts:184`.

**Handlers defined elsewhere**

| Handler | Defined in |
|---|---|
| `AgentsHandler` | `app/products/agents/database/operators/handlers/index.ts` |
| `BoardsHandler` | `app/products/boards/database/operators/handlers/index.ts` |
| `PlaybookHandler` | `app/products/playbooks/database/operators/handlers/index.ts` |

The other ten (`Category`, `Channel`, `CustomProfile`, `Group`, `Post`, `Properties`, `Team`, `TeamThreadsSync`, `Thread`, `User`) live in `server_data_operator/handlers/*.ts`. Only the base class is in `handlers/index.ts`.

**Where a write actually happens**

`batchRecords` in `app/database/operator/base_data_operator/index.ts:191` is the one place that touches the database:

```ts
await this.database.write(async (writer) => {
    await writer.batch(...models);
}, description);
```

It only runs when `models.length > 0`. It catches errors and logs them. If the error is a corruption error, it emits `DATABASE_CORRUPTION_DETECTED`. It rethrows only when `propagateError` is true, which it is not by default.

Handlers reach it in one of two ways:

- **Direct:** many handlers, such as `handlePosts` (`post.ts:618`) and `handleUsers`, call `this.batchRecords(...)` themselves after preparing models.
- **Via `handleRecords`:** the generic path in `base_data_operator/index.ts:224`. It runs `processRecords` (dedupe against the DB), then `prepareRecords` (run the transformer), and it writes only when `prepareRecordsOnly` is false. That flag defaults to `true`, so a plain `handleRecords` call returns prepared models without writing. The caller must batch them later.
- `execute` (`server_data_operator/handlers/index.ts:234`) is the same pattern: prepare, then `batchRecords`.

**What else shares that write path**

- `AppDataOperator` inherits `batchRecords` from `BaseDataOperator`. Its `handleGlobal` and `handleInfo` use it against the app database.
- The websocket actions in `app/actions/websocket/*.ts` (channel, posts, users, roles, category) call `operator.batchRecords` directly on a `ServerDataOperator`.
- Ephemeral cleanup in `app/actions/local/ephemeral_mode/cleanup.ts` (`cleanupAiThreads` at line 211, `cleanupPlaybookRuns` at line 230) calls it through a structural `{batchRecords}` type, so it does not depend on the concrete class.

**Caveat:** the index reports 159 unresolved callers of `batchRecords`. The list above is from a grep of the source, which I checked against the index's resolved callers.