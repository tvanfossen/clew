**Composition.** `ServerDataOperator` (`app/database/operator/server_data_operator/index.ts:40`) is a mixin composition. The class is `mix(ServerDataOperatorBase).with(AgentsHandler, BoardsHandler, CategoryHandler, ChannelHandler, CustomProfileHandler, GroupHandler, PlaybookHandler, …)`. The index's dossier lists 14 bases in total: the base class plus 13 handler classes. A companion `interface ServerDataOperator extends …HandlerMix` (line 23) merges the matching `…Mix` type declarations so the class exposes every handler method. The class body itself only has a constructor, which takes `(database, serverUrl?)`.

**Defined elsewhere.** Ten handlers are next to it in `server_data_operator/handlers/`: Category, Channel, CustomProfile, Group, Post, Properties, Team, TeamThreadsSync, Thread and User. The base class `ServerDataOperatorBase` is in `handlers/index.ts:31`. Three handlers live in product folders:

- `AgentsHandler`: `app/products/agents/database/operators/handlers/index.ts`
- `BoardsHandler`: `app/products/boards/database/operators/handlers/index.ts`
- `PlaybookHandler`: `app/products/playbooks/database/operators/handlers/index.ts`

**Where the write happens.** Handlers do not write directly. The path is:

1. A handler method (for example `handlePosts` or `handleAIBots`) builds raw values and calls `ServerDataOperatorBase.execute(...)` (`handlers/index.ts:234`).
2. `execute` calls `prepareRecords` to turn raw values into WatermelonDB models, then calls `batchRecords` only if there are models.
3. `BaseDataOperator.batchRecords` (`app/database/operator/base_data_operator/index.ts:191`) does the actual write: `this.database.write(async (writer) => { await writer.batch(...models); }, description)`.

On error, `batchRecords` logs a warning. If the error is a database corruption error, it emits `Events.DATABASE_CORRUPTION_DETECTED` through `DeviceEventEmitter`. It rethrows only when `propagateError` is true, so by default write failures are swallowed.

**What else shares it.**

- `BaseDataOperator` is also the base of `AppDataOperator`, so the app database uses the same `batchRecords`, `prepareRecords` and `handleRecords` code.
- `execute`, `prepareRecords` and `handleRecords` are shared by all server handlers that go through `execute`.
- The index also lists `batchRecords` entries in `app/actions/local/ephemeral_mode/cleanup.ts`. They have no body in the index, so they are probably local helpers with the same name rather than shared code. I did not verify this.