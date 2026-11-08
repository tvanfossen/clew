**Composition.** `ServerDataOperator` (`app/database/operator/server_data_operator/index.ts:40`) is a mixin stack built with the `mix()` helper (`app/utils/mix.ts`). It starts from `ServerDataOperatorBase` and applies 13 handler mixins in order: Agents, Boards, Category, Channel, CustomProfile, Group, Playbook, Post, Properties, Team, Thread, TeamThreadsSync, User. Each mixin is a function `(superclass) => class extends superclass`. A matching `*HandlerMix` interface is merged in at `index.ts:23-38` so TypeScript knows the methods exist. The class constructor takes `(database, serverUrl)` and stores the URL; `DatabaseManager` creates it at `app/database/manager/index.ts:184`.

The inheritance chain is:

```
BaseDataOperator                       app/database/operator/base_data_operator/index.ts
  └─ ServerDataOperatorBase            server_data_operator/handlers/index.ts
       └─ ServerDataOperator (mix)     server_data_operator/index.ts
```

**Where the handlers live.**

| Defined next to `index.ts` (`server_data_operator/handlers/`) | Defined elsewhere |
|---|---|
| category, channel, custom_profile, group, post, properties, team, team_threads_sync, thread, user | `AgentsHandler`: `app/products/agents/database/operators/handlers/index.ts` |
| | `BoardsHandler`: `app/products/boards/database/operators/handlers/index.ts` |
| | `PlaybookHandler`: `app/products/playbooks/database/operators/handlers/index.ts` |

The three product handlers are imported through the `@agents`, `@boards` and `@playbooks` path aliases. Reactions, files, roles, emojis, system and configs have no separate handler file. Their methods (`handleReactions`, `handleFiles`, `handleRole`, and so on) are defined directly on `ServerDataOperatorBase`.

**The write path.** A handler such as `handlePosts` or `handleAIBots` does not call the database directly. The write goes through this chain:

```
handler (e.g. handleAIBots, handlePlaybookRun)
  └─ handleRecords(...)                      base_data_operator  (default prepareRecordsOnly = true)
       ├─ processRecords(...)                diff raws against existing rows → create / update / delete lists
       ├─ prepareRecords(...)                transformer per record → prepareCreate / prepareUpdate,
       │                                     deletes → prepareDestroyPermanently
       └─ batchRecords(models, description)  if !prepareRecordsOnly
            └─ database.write(writer => writer.batch(...models))   ← the actual DB write
```

So `batchRecords` at `base_data_operator/index.ts` (around line 191) is the single write funnel. Two details matter:

- `handleRecords` defaults to `prepareRecordsOnly = true`, so it returns unsaved models unless the caller passes `false`. The product handlers do the same thing with their own `batchRecords` arrays: they call `this.batchRecords(...)` only when `!prepareRecordsOnly`.
- `batchRecords` catches errors and logs a warning. It only re-throws when `propagateError` is set. On a database corruption error it emits `Events.DATABASE_CORRUPTION_DETECTED`.

**What else shares it.**

- `batchRecords`, `processRecords`, `prepareRecords` and `handleRecords` all live on `BaseDataOperator`, so every server handler uses them. `AppDataOperator` also extends `BaseDataOperator` (created at `app/database/manager/index.ts:121`), so it shares the same write code.
- `execute()` on `ServerDataOperatorBase` is a shortcut that does `prepareRecords` followed by `batchRecords`.
- The mock manager (`app/database/manager/__mocks__/index.ts`) builds the same classes, so tests exercise the same write code.

**Exceptions that bypass `batchRecords`.** Two places call `database.write(...)` directly to destroy records: deleted posts in `handlers/post.ts` (around line 516) and deleted threads in `handlers/thread.ts` (around line 74). Those writes do not go through `batchRecords`, so they skip its warning log and its corruption event. If you are auditing write error handling, those two sites are the ones to check.