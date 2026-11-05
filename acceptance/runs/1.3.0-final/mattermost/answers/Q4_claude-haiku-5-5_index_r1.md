The setting is a single boolean gate, read in one place and checked at several call sites. The app treats an absent value the same as `"true"`: archived channels stay viewable.

**Where the value is read** (`app/queries/servers/system.ts:297-315`)

- `archivedChannelsViewable(value) = value !== 'false'`. Only the exact string `'false'` turns the feature off.
- `canViewArchivedChannels(db)` is the one-shot async read. `observeCanViewArchivedChannels(db)` is the reactive version, with `distinctUntilChanged`.
- The comment there says the setting is deprecated. Servers newer than v10.11 stop sending it. Older supported servers (down to v5.26.2) still send it and may have turned it off. A TODO says to remove these helpers once v10.11 support is dropped.

**Every place the behaviour depends on it**

| # | Location | When viewable (true, or absent) | When `'false'` |
|---|---|---|---|
| 1 | `app/actions/remote/channel.ts:1397` (`archiveChannel`) | After the server delete, sets a local `delete_at`, so the channel stays visible as archived | Calls `removeCurrentUserFromChannel` instead, dropping the channel locally |
| 2 | `app/actions/websocket/channel.ts:463` (`handleChannelDeletedEvent`) | Keeps the channel in the DB as archived | If it is the current channel, kicks the user with `CHANNEL_ARCHIVED`, then removes membership |
| 3 | `app/actions/remote/search.ts:62,73` (`searchPosts`) | Sends `include_deleted_channels: true` to the server, so results from archived channels come back | Sends `false` |
| 4 | `app/screens/browse_channels/index.ts:21` → `browse_channels.tsx:190` and `channel_dropdown.tsx:67`, `dropdown_slideup.tsx:74` | Shows the channel-type dropdown and the "Archived" option; the sheet snap height counts that item | Hides the archived option. If shared channels are also off, the dropdown is not rendered |
| 5 | `browse_channels.tsx:117-144` (`onSelectChannel`) | Archived channels are opened via `fetchMyChannel` plus `switchToChannelById`, skipping `joinChannel` (the comment says the server rejects joins on archived channels) | Not reached in practice, since archived channels are not listed |
| 6 | `app/screens/home/channel_list/categories_list/categories/header/index.ts:15-22` → `app/database/models/server/category.ts:107-118` (`observeHasChannels`) | A category holding only archived channels still counts as non-empty, and the current channel is always counted | Only non-archived channels count, so an all-archived category hides |
| 7 | `app/screens/channel_settings/archive/index.ts:21` → `archive.tsx:109,121` | Shows `archiveDescriptionCanViewArchived` and calls `close(false)` after archiving | Shows `archiveDescriptionCannotViewArchived` and calls `close(true)` |

**Ungated exception:** `app/screens/home/search/search.tsx:77` hardcodes `include_deleted_channels: true`. Home search ignores the setting, unlike `searchPosts` in the Browse and search paths.

**When the server does not send the setting at all**

- `canViewArchivedChannels` resolves `true`. `observeCanViewArchivedChannels` emits `true` and does not change afterward.
- Every gate in the table takes its "viewable" branch. Archived channels are kept locally, shown in Browse, included in search, and the archive dialog uses the "can view" wording.
- This is the expected case for current servers. The unit tests at `app/queries/servers/system.test.ts:692-717` assert `true` for absent, `true` for `'true'`, and `false` for `'false'`.
- The detox side agrees. `detox/shared/server-baseline.ts:80` marks it `absentIsBaseline: true`, and `detox/e2e/support/server_api/system.ts:139` says "Mobile treats a missing ExperimentalViewArchivedChannels as enabled."

I did not check how the client config is stored when the key is missing. The "absent → true" result rests on the `value?: string` signature and the unit tests, not on a trace of the write path.