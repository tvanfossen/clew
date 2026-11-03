The app treats `ExperimentalViewArchivedChannels` as a single gate for whether archived channels are visible. Only an explicit `"false"` turns that gate off. If the server omits the key, the app behaves as if archived channels are enabled.

**Where the value is read**

The helper is in `app/queries/servers/system.ts:297-315`. `archivedChannelsViewable(value)` returns `value !== 'false'`. Two wrappers use it:
- `canViewArchivedChannels(database)` reads the value once, for action code.
- `observeCanViewArchivedChannels(database)` is the reactive version for UI, with `distinctUntilChanged`.

**Every place the behaviour depends on it**

*Realtime and actions*
1. **`handleChannelDeletedEvent`** (`app/actions/websocket/channel.ts:463`). When a channel is archived and the setting is off, the app kicks the user out if that channel is open, then removes the user from the channel. When the setting is on, it only records `delete_at`.
2. **`archiveChannel`** (`app/actions/remote/channel.ts:1397`). With the setting on, it stamps `delete_at` locally and keeps the channel. With it off, it calls `removeCurrentUserFromChannel` (not awaited) instead.
3. **`searchPosts`** (`app/actions/remote/search.ts:62-73`). It passes `include_deleted_channels` to the search request set to the same boolean.

*UI*
4. **Browse Channels** (`app/screens/browse_channels/index.ts:21,49`). The flag reaches `browse_channels.tsx:75,190-195`, which shows the channel dropdown when archived or shared channels are enabled. `dropdown_slideup.tsx:74` shows the archived-channels option only when the flag is true, and `channel_dropdown.tsx:67` does the same. The comment at `browse_channels.tsx:121-126` relies on archived channels being visible.
5. **Sidebar category header** (`app/screens/home/channel_list/categories_list/categories/header/index.ts:15-22`). `CategoryModel.observeHasChannels` (`app/database/models/server/category.ts:107-118`) counts archived channels as present when the flag is on, but ignores them when it is off. The current channel always counts.
6. **Archive screen** (`app/screens/channel_settings/archive/archive.tsx:109,121,125`, `index.ts:21-24`). The archive confirmation shows one of two messages depending on the flag. The code also calls `close(!canViewArchivedChannels)`, but I did not trace what that argument controls.

*Tests and tooling (not app behaviour)*
- `detox/shared/server-baseline.ts:80` marks the key `absentIsBaseline: true`.
- `detox/e2e/support/server_api/system.ts:139-144` treats an absent value as enabled when polling client config. It keeps polling on failed fetches.
- `browse_channels.e2e.ts:180-185` fails the run if the key is explicitly `false`.
- Unit tests in `app/queries/servers/system.test.ts:692-717` cover absent, `"true"` and `"false"`.

**When the server does not send the setting**

`getConfigValue` and `observeConfigValue` return `undefined`, and `archivedChannelsViewable(undefined)` returns `true`. So every path above behaves as if archived channels are on. Concretely, archived channels stay in the local DB and appear in Browse Channels, the archive flow stamps `delete_at` instead of leaving the channel, search includes deleted channels, and the sidebar counts archived channels.

The code comment at `system.ts:297-303` gives the reason. Servers newer than v10.11 stopped sending the key, and the feature is always on there. Older servers (down to v5.26.2) still send it and may set it to `false`. A TODO says the helpers and their callers can be removed once support for servers at or below v10.11 is dropped.

I did not check the server side, so the v10.11 cutoff is taken from the code comment.