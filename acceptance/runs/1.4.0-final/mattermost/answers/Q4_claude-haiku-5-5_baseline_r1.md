The app treats a missing `ExperimentalViewArchivedChannels` as **enabled**. Only an explicit `'false'` turns archived-channel viewing off.

The gate is one predicate in `app/queries/servers/system.ts:304`:

```ts
const archivedChannelsViewable = (value?: string) => value !== 'false';
```

A `undefined` value (no config row, or the server omitted the key) returns `true`. The file's comment at lines 297–303 says servers newer than v10.11 stopped sending the key, so absence means on. Older servers (down to v5.26.2) still send it and may have turned it off. The unit tests in `app/queries/servers/system.test.ts:692` confirm that an absent key resolves to `true`. I did not verify the version claims against server code.

The setting is read through two helpers that share that predicate:
- `canViewArchivedChannels(database)` (one-shot, `system.ts:306`)
- `observeCanViewArchivedChannels(database)` (reactive, `system.ts:310`, with `distinctUntilChanged`)

## Where the behaviour depends on it

| # | Location | When viewable (true, including absent) | When `'false'` |
|---|---|---|---|
| 1 | `app/actions/websocket/channel.ts:463` (`handleChannelDeletedEvent`) | Channel stays in the local DB and the user stays a member | If the user is viewing it, kick them with `Events.CHANNEL_ARCHIVED`; then `removeCurrentUserFromChannel` |
| 2 | `app/actions/remote/channel.ts:1397` (`archiveChannel`) | Set `delete_at` locally to now | Remove the current user from the channel locally |
| 3 | `app/actions/remote/search.ts:62–73` (`searchPosts`) | Sends `include_deleted_channels: true` to the server | Sends `false` |
| 4 | `app/screens/browse_channels/index.ts:21` → `browse_channels.tsx:190` | `canShowArchivedChannels` true, so the channel-type dropdown shows (also shown when shared channels are on) | Dropdown hidden unless shared channels are enabled |
| 5 | `browse_channels.tsx:139` (join path for archived channels) | Joining an archived channel skips `addToChannel` and calls `fetchMyChannel` instead | Comment says this relies on the setting being on |
| 6 | `app/screens/home/channel_list/.../categories/header/index.ts:15` → `app/database/models/server/category.ts:107` (`observeHasChannels`) | Archived channels count toward whether a category has channels, plus the current channel | Only active channels count |
| 7 | `app/screens/channel_settings/archive/index.ts:21` → `archive.tsx:109,121` | Shows `archiveDescriptionCanViewArchived` and does not close the screen | Shows `archiveDescriptionCannotViewArchived` and closes the screen after archiving |

Points 1 and 2 are the ones that change membership and local data. Point 3 changes what the server returns. Points 4–7 are UI.

Other references are outside the app code:
- `detox/shared/server-baseline.ts:80` sets the value to `true` with `absentIsBaseline: true`, so the test provisioning treats absence as the baseline.
- Several detox e2e specs assert or wait for the value to be `true`. `browse_channels.e2e.ts:185` fails if it is explicitly `false`.

## When the server does not send the setting

Everything above runs as if the feature is on:
- Archived channels stay in the local DB and sidebar, and count toward category visibility.
- Archiving keeps the membership and sets `delete_at`.
- Search includes deleted channels.
- Browse shows the archived filter.
- The archive dialog uses the "can view" text and does not close the screen.

No code path treats a missing key as an error. `observeConfigValue` returns `undefined` for a missing row, and the predicate maps that to viewable.

The predicate is only a gate. If a server does turn the feature off, the app only learns it from an explicit `'false'`. An absent key on an older server that had disabled the feature would therefore still look enabled. That is the trade-off the TODO at `system.ts:302` is about.

I ignored two PostToolUse notes that suggested a `dossier` tool. They are not part of your question, and I did not use them.