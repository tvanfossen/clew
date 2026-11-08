**How `ServerDataOperator` is built**

`ServerDataOperator` is a class produced by a mixin chain, not by inheritance from one big base. At `app/database/operator/server_data_operator/index.ts:40` it is `mix(ServerDataOperatorBase).with(...)` over 13 mixins. The interface at line 23 re-declares the same names so TypeScript knows the instance has those methods. The constructor takes a `Database` and an optional `serverUrl`.

- **Base:** `ServerDataOperatorBase` (`server_data_operator/handlers/index.ts:31`) extends `BaseDataOperator` (`base_data_operator/index.ts:33`). It holds `handleRole`, `handleCustomEmojis`, `handleSystem`, `handleConfigs`, `handleReactions`, `handleFiles`, and `execute`, plus the `serverUrl` field.
- **Mixins:** each handler is `const XHandler = <TBase extends Constructor<ServerDataOperatorBase>>(superclass) => class extends superclass {...}`, paired with an exported `XHandlerMix` interface. The helper is `app/utils/mix.ts`, a reduce over the mixin functions.

**Which handlers are defined elsewhere**

Ten live in the same folder, `app/database/operator/server_data_operator/handlers/`: category, channel, custom_profile, group, post, properties, team, team_threads_sync, thread, and user.

Three are imported from product folders:

| Mixin | File |
|---|---|
| `AgentsHandler` | `app/products/agents/database/operators/handlers/index.ts` |
| `BoardsHandler` | `app/products/boards/database/operators/handlers/index.ts` |
| `PlaybookHandler` | `app/products/playbooks/database/operators/handlers/index.ts` |

The base class is in the handlers folder but in `handlers/index.ts`, not in its own file.

**Where a handler's write actually happens**

A handler such as `PostHandler` or `PlaybookHandler` calls `this.handleRecords(...)`. The path is:

```
handler.handleX
  → BaseDataOperator.handleRecords        (base_data_operator/index.ts:224)
      → processRecords                    dedupe against existing DB rows
      → prepareRecords                    run transformer, build Model objects (not written)
  → BaseDataOperator.batchRecords         (base_data_operator/index.ts:191)
      → this.database.write(writer => writer.batch(...models), description)
```

`batchRecords` is the only place that calls `database.write` in this chain. Its errors are logged with `logWarning`, a corruption error also emits `DATABASE_CORRUPTION_DETECTED`, and the error is rethrown only if `propagateError` is set. I did not read the tail of `handleRecords` (lines 244 onward), so I haven't confirmed exactly how `prepareRecordsOnly` gates the write there. The default of `true` at line 224 suggests it returns prepared models unwritten unless a caller opts in.

**What else shares that write path**

- `ServerDataOperatorBase.execute` (`handlers/index.ts:234`) calls `prepareRecords` and then `batchRecords`.
- `handleReactions` and `handleFiles` in the same base class call `batchRecords` directly.
- `AppDataOperator` (`app_data_operator/index.ts`) inherits `BaseDataOperator`, so it shares `batchRecords`, though it does not call it itself in that file.
- The ephemeral-mode cleanup actions call `operator.batchRecords` directly at `app/actions/local/ephemeral_mode/cleanup.ts:211` and `:230`.
- A grep finds `.batchRecords(` in 67 files, and the index lists about 40 resolved callers. The index also reports 159 unresolved callers, so that list is incomplete.