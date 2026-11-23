**Short answer:** `ServerDataOperator` is a mixin composition. Most handlers live next to it in `handlers/`, but the Agents, Boards and Playbooks handlers are defined in their product folders. Every handler's write goes through one method, `BaseDataOperator.batchRecords`, which wraps `database.write` (`app/database/operator/base_data_operator/index.ts:191-211`). `AppDataOperator` shares that base, so it uses the same write path.

**How the class is built**

- `app/database/operator/server_data_operator/index.ts:40-59` declares `class ServerDataOperator extends mix(ServerDataOperatorBase).with(...)`. The base is `ServerDataOperatorBase`, and 13 mixins are applied in order: Agents, Boards, Category, Channel, CustomProfile, Group, Playbook, Post, Properties, Team, Thread, TeamThreadsSync, User.
- `mix` (`app/utils/mix.ts`) is a small reducer: `mixins.reduce((c, m) => m(c), superclass)`. Each mixin is a function that takes a base class and returns a subclass.
- The `interface ServerDataOperator extends …Mix {}` block at lines 23-38 merges the typed `*HandlerMix` interfaces into the class, so callers see the method signatures.
- The constructor (line 55) calls `super(database)` and stores `serverUrl`. `DatabaseManager` creates instances at `app/database/manager/index.ts:184`.

**Where the handlers are defined**

| Handler | Location |
|---|---|
| `ServerDataOperatorBase` (base) | `server_data_operator/handlers/index.ts` (same folder) |
| Category, Channel, CustomProfile, Group, Post, Properties, Team, TeamThreadsSync, Thread, User | `server_data_operator/handlers/<name>.ts` (same folder) |
| `AgentsHandler` | `app/products/agents/database/operators/handlers/index.ts` |
| `BoardsHandler` | `app/products/boards/database/operators/handlers/index.ts` |
| `PlaybookHandler` | `app/products/playbooks/database/operators/handlers/index.ts` |

The product files are reached through the `@agents`, `@boards` and `@playbooks` path aliases (`tsconfig.json`, `babel.config.js`). Each product handler is a `Constructor<ServerDataOperatorBase>` mixin, the same pattern as the in-folder handlers.

**What performs the database write**

A handler does not write directly in the normal case. The chain is:

1. A handler method (e.g. `AgentsHandler.handleAIBots`, `agents/.../handlers/index.ts:43`) builds records with `this.handleRecords(...)`.
2. `BaseDataOperator.handleRecords` (`base_data_operator/index.ts:224`) calls `processRecords` to split the raw input into create, update and delete sets, then calls `prepareRecords` to run the transformer per record.
3. If `prepareRecordsOnly` is false, it calls `this.batchRecords(models, description)`.
4. `batchRecords` runs `this.database.write(async (writer) => writer.batch(...models), description)`. On error it logs, emits `Events.DATABASE_CORRUPTION_DETECTED` if the error is a corruption error, and rethrows only when `propagateError` is set.

Some handlers skip this and call `database.write` themselves. Examples are `post.ts:516` and `thread.ts:74`. Those are exceptions to the single-path rule.

**What else shares it**

- **`BaseDataOperator`** is the shared parent. `ServerDataOperatorBase` extends it, and so does `AppDataOperator` (`app/database/operator/app_data_operator/index.ts:15`). Both inherit `batchRecords`, `handleRecords`, `prepareRecords` and `processRecords`, so the app database and the per-server databases share one write path.
- **Within the server operator**, `ServerDataOperatorBase.execute`, `handleFiles` and `handleReactions` also end in `batchRecords`. Every product handler reaches it through `this`.
- **Callers outside the operator:** the index shows about 232 unresolved callers of `batchRecords` and no direct edges from the cleanup actions. I did not verify those, so I am not claiming they reach the operator.