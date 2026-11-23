**Composition.** `ServerDataOperator` (`app/database/operator/server_data_operator/index.ts:40`) is `class ServerDataOperator extends mix(ServerDataOperatorBase).with(AgentsHandler, BoardsHandler, CategoryHandler, ChannelHandler, CustomProfileHandler, GroupHandler, PlaybookHandler, …)`. Its constructor is `(database, serverUrl?)` at line 55. A matching `interface ServerDataOperator extends …Mix` at line 23 supplies the method typings through declaration merging.

**Where each piece is defined**

| Piece | Location |
|---|---|
| `ServerDataOperatorBase` (base; `extends BaseDataOperator`) | `server_data_operator/handlers/index.ts:31` |
| `CategoryHandler`, `ChannelHandler`, `CustomProfileHandler`, `GroupHandler`, `PostHandler`, `PropertiesHandler`, `TeamHandler`, `TeamThreadsSyncHandler`, `ThreadHandler`, `UserHandler` | `server_data_operator/handlers/*.ts`, next to the operator |
| `AgentsHandler` | `app/products/agents/database/operators/handlers/index.ts` |
| `BoardsHandler` | `app/products/boards/database/operators/handlers/index.ts` |
| `PlaybookHandler` | `app/products/playbooks/database/operators/handlers/index.ts` |

So three of the mixed-in handlers come from product folders, not from the core handlers directory.

**The actual database write**

Handlers never call WatermelonDB directly. The chain is:

```
PostHandler.handlePosts / GroupHandler.handleGroups / AgentsHandler.handleAIBots / …
  └─> BaseDataOperator.handleRecords   (dedupe, then prepare; batches only if prepareRecordsOnly=false)
  └─> ServerDataOperatorBase.execute   (prepare, then always batch)
        └─> BaseDataOperator.batchRecords   (app/database/operator/base_data_operator/index.ts:191)
              └─> this.database.write(writer => writer.batch(...models), description)
```

`batchRecords` is the only place the write happens. It catches errors and logs them. If `isDatabaseCorruptionError` matches, it emits `Events.DATABASE_CORRUPTION_DETECTED`. It rethrows only when `propagateError` is true, and that defaults to false, so write failures are normally swallowed.

Two things to watch:
- `handleRecords` defaults to `prepareRecordsOnly = true`. In that mode it returns prepared models without writing, so the caller must batch them later.
- `ServerDataOperatorBase` methods such as `handleReactions`, `handleFiles` and `handleChannelBookmark` call `batchRecords` directly in some paths.

**What else shares it**

- `BaseDataOperator` is the shared base. Its other subclass, `AppDataOperator` (`app/database/operator/app_data_operator/index.ts`), uses the same `handleRecords` and `batchRecords` for `handleGlobal` and `handleInfo`. So the app database and each server database share one write path.
- Within the server operator, the callers of `batchRecords` and `handleRecords` span nearly every handler file, including the agents, boards and playbooks handlers.
- The index also reports `batchRecords` name matches in `app/actions/local/ephemeral_mode/cleanup.ts`. I did not confirm whether those call this method or are unrelated local names.