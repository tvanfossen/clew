**Short answer:** `ServerDataOperator` is a mixin composition of one base class and about a dozen handler mixins. Most handlers live in `server_data_operator/handlers/`, but Agents, Boards and Playbooks handlers live in their product folders. Every handler write funnels through `BaseDataOperator.batchRecords()`, which calls `database.write()` and `writer.batch()`. That same method is shared by `AppDataOperator` and by roughly 200 call sites outside the handlers.

**How the class is built**

- `app/database/operator/server_data_operator/index.ts:40` declares `class ServerDataOperator extends mix(ServerDataOperatorBase).with(...)`. The `mix` helper is `app/utils/mix.ts`. The interface at lines 23–38 merges the handler mix-in types so TypeScript sees all the methods.
- The base is `ServerDataOperatorBase` in `server_data_operator/handlers/index.ts:31`. It extends `BaseDataOperator` and adds `serverUrl` plus these handlers: `handleRole`, `handleCustomEmojis`, `handleSystem`, `handleConfigs`, `handleReactions`, `handleFiles`, and `execute`.
- `DatabaseManager` creates it at `app/database/manager/index.ts:184` as `new ServerDataOperator(database, serverUrl)`. The app-level database uses `AppDataOperator` instead.

**Where the handlers are defined**

| Handler | Location |
|---|---|
| category, channel, custom_profile, group, post, properties, team, team_threads_sync, thread, user | `app/database/operator/server_data_operator/handlers/` (next to the class) |
| AgentsHandler | `app/products/agents/database/operators/handlers/index.ts` |
| BoardsHandler | `app/products/boards/database/operators/handlers/index.ts` |
| PlaybookHandler | `app/products/playbooks/database/operators/handlers/index.ts` |

The product handlers import `ServerDataOperatorBase` as a type only. They are plugged in through the same `mix(...).with(...)` call, so they can use `this.batchRecords` and `this.processRecords` from the base.

**Which code performs the database write**

1. A handler builds raw values and calls one of three paths. Most use `handleRecords`, which does `processRecords` (dedupe against the DB), then `prepareRecords` (run transformers), then `batchRecords` only if `prepareRecordsOnly` is false. The default is `true`, so the handler returns unsaved models unless the caller opts in. Some use `execute`, and the agents and playbooks handlers call `batchRecords` directly.
2. The actual write is `BaseDataOperator.batchRecords()` in `app/database/operator/base_data_operator/index.ts:191`:
   ```
   this.database.write(async (writer) => writer.batch(...models), description)
   ```
   It logs and swallows errors unless `propagateError` is set. It also emits `DATABASE_CORRUPTION_DETECTED` on corruption errors.
3. `processRecords`, `prepareRecords`, `handleRecords` and `batchRecords` all live in `BaseDataOperator`. `ServerDataOperatorBase.execute` and `AppDataOperator` reuse them.

**What else shares the write path**

- **`AppDataOperator`** (`app/database/operator/app_data_operator/index.ts`) extends the same `BaseDataOperator`, so it shares `batchRecords` and the other helpers. It writes to the app DB rather than a server DB.
- **Direct callers of `operator.batchRecords`** are spread across `app/actions/remote`, `app/actions/local`, `app/actions/websocket`, `app/queries/servers` and `app/products/*`. Examples: `createPost`, `fetchPosts`, `handlePostEdited`, `addReaction`, `storeCategories`.
- **Bypasses that call `database.write` directly** and do not go through `batchRecords`:
  - `handlers/post.ts:516` destroys deleted posts.
  - `handlers/thread.ts:74` destroys deleted threads.
  - Many playbook local actions do the same.
  - `app/queries/servers/custom_profile.ts:137` writes its own batches.
  - `app/actions/local/redaction.ts:135` uses `writer.batch` inside its own `database.write`.

  These do not get the corruption-event handling that `batchRecords` provides. The redaction case also has a comment saying `handleSystem` cannot be nested inside its write.

I have not run the test suite; this is from reading the code.