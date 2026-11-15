## How `ServerDataOperator` is built

`ServerDataOperator` is a class that extends a mixin chain, not a plain subclass. In `app/database/operator/server_data_operator/index.ts:40`, it is `mix(ServerDataOperatorBase).with(...)` over 13 handler classes. `mix` (`app/utils/mix.ts`) is a tiny builder that folds each handler over the base with `reduce`. A matching `interface ServerDataOperator extends ...Mix` block (lines 23–38) gives TypeScript the method signatures. The constructor takes a WatermelonDB `Database` and an optional `serverUrl`, which is set after `super()`.

`ServerDataOperatorBase` lives in `handlers/index.ts` (not in the top-level file) and provides the non-table-specific methods: `handleRole`, `handleSystem`, `handleConfigs`, `handleCustomEmojis`, `handleReactions`, `handleFiles`, and `execute`. It extends `BaseDataOperator`.

## Handlers defined elsewhere

Ten handlers are defined in `app/database/operator/server_data_operator/handlers/*.ts`, next to the base. Three come from product folders:

| Handler | Defined in |
|---|---|
| `AgentsHandler` | `app/products/agents/database/operators/handlers/index.ts` |
| `BoardsHandler` | `app/products/boards/database/operators/handlers/index.ts` |
| `PlaybookHandler` | `app/products/playbooks/database/operators/handlers/index.ts` |

These are the same mixin pattern, so they plug into `ServerDataOperator` with no extra wiring. Their methods (`handleAIBots`, `handleBoardViews`, `handlePlaybookRun`, etc.) call the shared base methods below.

## The actual database write

Handlers do not call `database.write` themselves in the normal path. The chain is:

1. **Handler** (e.g. `handleUsers`) calls `this.handleRecords({...}, 'handleUsers')`.
2. **`BaseDataOperator.handleRecords`** (`app/database/operator/base_data_operator/index.ts:224`) calls `processRecords` to diff raw values against existing rows (dedupe, create vs. update vs. delete). Then it calls `prepareRecords`, which runs each transformer to build WatermelonDB `prepareCreate`/`prepareUpdate` models and `prepareDestroyPermanently` for deletes. Finally, unless `prepareRecordsOnly` is set, it calls `batchRecords`.
3. **`BaseDataOperator.batchRecords`** (line 191) is the one place that performs the write: `this.database.write(async (writer) => { await writer.batch(...models); })`. It logs failures, emits `DATABASE_CORRUPTION_DETECTED` on corruption errors, and rethrows only when `propagateError` is true.

Note that `prepareRecordsOnly` defaults to `true` in `handleRecords` (and in the base handlers). A handler call that does not pass `prepareRecordsOnly: false` only returns prepared models, and nothing is written until a caller batches them.

## What else shares this path

- **`AppDataOperator`** (`app/database/operator/app_data_operator/index.ts`) extends `BaseDataOperator`, so it shares `handleRecords`, `prepareRecords`, `processRecords`, and `batchRecords` against the app database.
- **`ServerDataOperatorBase.execute`, `handleFiles`, `handleReactions`** call `prepareRecords` and then `batchRecords` directly in the same file.
- **Test helper** `app/database/operator/utils/test.ts:97` does its own `writer.batch` for fixtures.

## Exceptions that bypass `batchRecords`

Two handlers open their own `database.write` for hard deletes:

- `ThreadHandler` at `handlers/thread.ts:74` destroys threads, `threadsInTeam`, and participants for deleted thread IDs.
- `PostHandler` at `handlers/post.ts:516` destroys posts with `delete_at > 0` before its `processRecords` pass.

Both are separate transactions and do not use `batchRecords`, so their errors do not get the corruption-event handling. Outside the operator, many actions under `app/actions/local/` and `app/products/playbooks/actions/local/` also call `database.write` directly, bypassing the operators entirely.