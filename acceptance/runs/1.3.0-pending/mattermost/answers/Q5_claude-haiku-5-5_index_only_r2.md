**Short answer:** `ServerDataOperator` is a class whose bases are 11 handler mixins in `server_data_operator/handlers/` plus 3 mixins from the agents, boards and playbooks products. Every handler's DB write funnels through `BaseDataOperator.batchRecords`, which is also used by `AppDataOperator`.

**How it's built**

- `ServerDataOperator` is declared at `app/database/operator/server_data_operator/index.ts:23`. Its constructor (line 55) calls `super(database)` and stores `serverUrl`. The index shows no members of its own; the mixin wiring itself is not a symbol the index holds, so I can't confirm the exact composition mechanism from here.
- Its bases are:
  - **Defined next to it, in `server_data_operator/handlers/`:** `CategoryHandlerMix`, `ChannelHandlerMix`, `CustomProfileHandlerMix`, `GroupHandlerMix`, `PostHandlerMix`, `PropertiesHandlerMix`, `TeamHandlerMix`, `TeamThreadsSyncHandlerMix`, `ThreadHandlerMix`, `UserHandlerMix`. Each `*Mix` has a matching concrete `*Handler` class in the same folder, e.g. `PostHandler` in `handlers/post.ts`.
  - **Also in `handlers/index.ts`:** `ServerDataOperatorBase` (line 31), which extends `BaseDataOperator`. It holds `serverUrl`, `handleRole`, `handleCustomEmojis`, `handleSystem`, `handleConfigs`, `handleReactions`, `handleFiles` and the generic `execute`.
  - **Defined elsewhere, in product folders:**
    - `AgentsHandlerMix` in `app/products/agents/database/operators/handlers/index.ts`
    - `BoardsHandlerMix` in `app/products/boards/database/operators/handlers/index.ts` (line 20; it only adds `handleBoardViews`)
    - `PlaybookHandlerMix` in `app/products/playbooks/database/operators/handlers/index.ts`

**Where the write actually happens**

When a handler writes records, the chain is:

1. A handler method such as `PostHandler.handlePosts` or `UserHandler.handlePreferences` calls `this.execute(...)` (or a helper that calls `batchRecords` directly).
2. `ServerDataOperatorBase.execute` (`server_data_operator/handlers/index.ts:234`) calls `this.prepareRecords(...)` to build Model objects, then `this.batchRecords(models, description)`.
3. `BaseDataOperator.batchRecords` (`base_data_operator/index.ts:191`) is the actual write. It calls `this.database.write(async (writer) => writer.batch(...models), description)`. On error it logs a warning and, if `isDatabaseCorruptionError(e)`, emits `Events.DATABASE_CORRUPTION_DETECTED` via `DeviceEventEmitter`. It rethrows only when `propagateError` is set.

`prepareRecords` and `handleRecords` in the same base class do the de-duplication and preparation before this step.

**What else shares it**

- **`AppDataOperator`** (`app/database/operator/app_data_operator/index.ts:15`) extends `BaseDataOperator` directly. Its `handleInfo` and `handleGlobal` write through the same `batchRecords`, but against the app database, not a server database.
- **Within the server operator,** the index lists callers of `batchRecords` spanning `PostHandler` (`_createOrUpdateScheduledPost`, `_createPostsInChannelRecord`, `_deleteScheduledPostByIds`, `_mergePostInChannelChunks`, `handlePosts`, `handleReceivedPostsInChannel*`, `handleScheduledPosts`, and others), the product handlers (`AgentsHandler`, `PlaybookHandler`), `ChannelHandler.handleChannelBookmark`, `GroupHandler`, `PropertiesHandler`, `ThreadHandler`, `TeamThreadsSyncHandler`, and `BaseDataOperator.handleRecords`. The index reports 159 unresolved callers, so this list is partial.
- **Mock:** `app/database/manager/__mocks__/index.ts` creates a `ServerDataOperator` through the same constructor, so tests exercise the same base class.