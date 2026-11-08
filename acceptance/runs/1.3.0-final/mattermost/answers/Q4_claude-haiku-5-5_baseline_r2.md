The app treats `ExperimentalViewArchivedChannels` as a single on/off gate for archived channels, and it fails open: if the server doesn't send the key, archived channels are treated as enabled. Only an explicit `"false"` turns the feature off. `"true"` and an absent key behave the same.

**Where the value is read**

All gating goes through one helper in `app/queries/servers/system.ts:297-315`. The `archivedChannelsViewable` function returns `value !== 'false'`. `canViewArchivedChannels` (async) and `observeCanViewArchivedChannels` (observable, with `distinctUntilChanged`) both wrap it. The config row is looked up with `getConfigValue` / `observeConfigValue`, which return `undefined` when no row exists.

**Every place the behaviour depends on it**

| Area | File:line | What changes when viewable is true (false is the opposite) |
|---|---|---|
| Category header | `app/screens/home/channel_list/categories_list/categories/header/index.ts:15` → `app/database/models/server/category.ts:107` | `observeHasChannels` counts archived channels as channels when deciding whether a category has content. When false, only active channels count, plus the current channel. |
| Browse Channels dropdown | `app/screens/browse_channels/index.ts:21,49` → `browse_channels.tsx:190-195` → `channel_dropdown.tsx:67-74` → `dropdown_slideup.tsx:74` | The "archived" entry is offered in the Show dropdown. The dropdown is rendered if archived or shared channels are enabled, and the sheet height counts the archived entry. |
| Archive screen copy | `app/screens/channel_settings/archive/index.ts:21` → `archive.tsx:109` | The confirm message uses the "can view archived" text or the "cannot view archived" text. |
| Archive screen navigation | `archive.tsx:121` | After a successful archive, `close(!canViewArchivedChannels)` is called, so the flag is passed as the `pop` argument. |
| Archive action | `app/actions/remote/channel.ts:1397-1401` | If viewable, the channel is kept locally with a `delete_at` timestamp (`setChannelDeleteAt`). If not, the current user is removed from the channel locally. |
| Archived-channel websocket event | `app/actions/websocket/channel.ts:463-470` | If not viewable, the app kicks the user out if it is the current channel and removes their membership. If viewable, the channel stays in the DB as archived. |
| Post search | `app/actions/remote/search.ts:62-68` | Sent to the server as `include_deleted_channels`, so search results include archived channels only when viewable. |

Two things I noticed while tracing:
- `app/screens/browse_channels/search_handler.tsx:27` declares a `canShowArchivedChannels` prop, but nothing in that file reads it. It looks dead.
- `browse_channels.tsx` has a branch that handles `channel.delete_at > 0` (archived) by calling `fetchMyChannel`. That branch does not check the flag. The comment above it assumes archived channels are only visible when the flag is on.

**When the server does not send the setting**

The value is `undefined`, so `archivedChannelsViewable` returns `true`. Every row above behaves as if the feature is enabled. The code comment in `system.ts:297-303` explains why: servers newer than v10.11 stopped sending the key because the feature is always on. Servers from v5.26.2 up to v10.11 still send it, and an explicit `false` there is honoured.

The test-side code agrees with this. `app/queries/servers/system.test.ts:692-717` covers absent (true), `"true"` (true), and `"false"` (false). The Detox harness treats absence as enabled (`detox/e2e/support/server_api/system.ts:139`), and `detox/shared/server-baseline.ts:80` marks the key with `absentIsBaseline: true`.

The helpers carry a TODO to delete them once servers ≤ v10.11 are no longer supported. At that point archived channels would be treated as always viewable.

I did not run the test suite; this answer is from reading the code.