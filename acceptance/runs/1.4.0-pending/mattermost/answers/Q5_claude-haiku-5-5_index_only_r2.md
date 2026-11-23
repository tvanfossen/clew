**Composition.** `ServerDataOperator` (`app/database/operator/server_data_operator/index.ts:40`) is `class ServerDataOperator extends mix(ServerDataOperatorBase).with(...)`. The mixin list is AgentsHandler, BoardsHandler, CategoryHandler, ChannelHandler, CustomProfileHandler, GroupHandler, PlaybookHandler, and the rest of the handler set. Its only own member is the constructor (`database: Database, serverUrl?: string`, line 55). The merged interface at line 23 declares the matching `*HandlerMix` types, so the typed surface comes from those interfaces.

**Base.** `ServerDataOperatorBase` (`handlers/index.ts:31`) extends `BaseDataOperator`. It holds `serverUrl` and the shared helpers: `handleRole`, `handleCustomEmojis`, `handleSystem`, `handleConfigs`, `handleReactions`, `handleFiles`, and `execute`.

**Defined next to it** (`app/database/operator/server_data_operator/handlers/`): category, channel, custom_profile, group, post, properties, team, team_threads_sync, thread, user. Each file exports a factory of the form `const XHandler = <TBase extends Constructor<ServerDataOperatorBase>>(superclass) => class extends superclass`, plus its `XHandlerMix` interface. PostHandler is the largest at about 728 lines.

**Defined elsewhere** — the three product handlers, in `app/products/`:
- `AgentsHandler`: `agents/database/operators/handlers/index.ts:35`
- `BoardsHandler`: `boards/database/operators/handlers/index.ts:24`
- `PlaybookHandler`: `playbooks/database/operators/handlers/index.ts:57`

They follow the same mixin pattern and are constrained to `Constructor<ServerDataOperatorBase>`.

**Where the write happens.** A handler does not write directly. The chain is:

1. A handler method (e.g. `PostHandler.handlePosts`, `UserHandler.handlePreferences`, `PlaybookHandler.handlePlaybookRun`) builds raw values and calls `this.execute(...)` or `prepareRecords`/`handleRecords`.
2. `ServerDataOperatorBase.execute` (`handlers/index.ts:234`) calls `prepareRecords` to build prepared Watermelon models, then `batchRecords` if there are any.
3. `BaseDataOperator.batchRecords` (`app/database/operator/base_data_operator/index.ts:191`) is the actual write. It calls `this.database.write(async (writer) => writer.batch(...models), description)`. On error it logs a warning. If the error is a database-corruption error, it emits `Events.DATABASE_CORRUPTION_DETECTED` on `DeviceEventEmitter`. It rethrows only when `propagateError` is true, which is off by default.

**What shares it.**
- `BaseDataOperator` is also the base of `AppDataOperator` (`app/database/operator/app_data_operator/index.ts`), so the app database uses the same `batchRecords` write path.
- Within the server operator, `batchRecords` is called directly by PostHandler methods (scheduled posts, channel posts, post chunks, received posts), by `ServerDataOperatorBase` (`execute`, `handleFiles`, `handleReactions`), and by handlers in channel, group, user, properties, and the agents and playbooks products. The index reports 32 callers in total and shows 25.
- `batchRecords` is also reached through `prepareRecords` and `handleRecords` on the same base class, so the create/update and dedupe paths converge there.

**Caveat.** The index also lists `batchRecords` entries in `app/actions/local/ephemeral_mode/cleanup.ts`. Those are name collisions with local symbols, not confirmed callers of the base method, so I have not counted them as sharing the write path.