## Short answer

The setting has one effective meaning: archived channels are viewable unless the server explicitly sends `"false"`. Every consumer goes through a single helper, `archivedChannelsViewable(value) = value !== 'false'` (`app/queries/servers/system.ts:304`). If the server omits the key, the value is `undefined`, the helper returns `true`, and the app behaves as if the feature is on.

## How the value is read

- `canViewArchivedChannels(database)` (`system.ts:306`) is the async read. It is used by actions and by one websocket handler.
- `observeCanViewArchivedChannels(database)` (`system.ts:310`) is the reactive version. It is used by UI components, and it emits `distinctUntilChanged` booleans.
- The source is the local `Config` table, read with `observeConfigValue`/`getConfigValue`. An absent row yields `undefined`.
- The comment at `system.ts:297-303` documents the reasoning. Servers newer than v10.11 stopped sending the key because the feature is always on. Older supported servers (down to v5.26.2) may send `false`, so only an explicit `false` turns it off.

## Every place the behaviour depends on it

**Actions**

| Location | With `true` / absent | With `false` |
|---|---|---|
| `app/actions/remote/search.ts:62-73` (`searchPosts`) | Sends `include_deleted_channels: true` to the search API, so archived-channel posts appear in results | Sends `false` |
| `app/actions/remote/channel.ts:1397` (`archiveChannel`) | After `deleteChannel`, sets `delete_at` locally, so the channel stays visible as archived | Calls `removeCurrentUserFromChannel` locally and does not set `delete_at` |
| `app/actions/websocket/channel.ts:463` (channel-deleted/archived event handler) | Does nothing extra | If the channel is the current one, `handleKickFromChannel(... Events.CHANNEL_ARCHIVED)`, then `removeCurrentUserFromChannel` |

**UI**

| Location | Effect |
|---|---|
| `app/screens/browse_channels/index.ts:21` → `browse_channels.tsx:190` | The channel-type dropdown renders if archived viewing is on or shared channels are enabled |
| `browse_channels/channel_dropdown.tsx:67` and `dropdown_slideup.tsx:74` | The "Archived Channels" option and the bottom-sheet item count depend on it |
| `app/screens/channel_settings/archive/index.ts:21` → `archive.tsx:109,121,125` | Chooses the archive confirmation text (`archiveDescriptionCanViewArchived` vs `archiveDescriptionCannotViewArchived`). After archiving, `close(!canView)` closes the settings screen when the user can no longer see the channel |
| `app/screens/home/channel_list/categories_list/categories/header/index.ts:15` → `category.ts:107-114` | Favourites header visibility. With viewing on, it counts archived channels as well as the current channel. With it off, only non-archived channels count |

**Not gated by it**

- `browse_channels.tsx:139` branches on `channel.delete_at > 0`, not on the setting. An archived channel in the browse list always takes the `fetchMyChannel` path, even if the flag is off.
- `archive.tsx` `canUnarchive` and `channel_settings/index.ts` / `channel_info/index.ts` `canArchive`/`canUnarchive` do not read this setting.

**Other observations**

- `app/screens/home/search/search.tsx:77` hard-codes `include_deleted_channels: true` in the params it builds. `searchPosts` spreads those params and then overrides the key with `viewArchivedChannels`, so the screen's value never reaches the server. It is dead code.
- `search_handler.tsx:27` declares a `canShowArchivedChannels` prop. A grep finds no use of it inside that file.

## When the server does not send the setting

Absent means enabled everywhere in the table above:

- Search includes deleted channels.
- Archiving keeps the channel visible as archived, and the user is not removed.
- The Archived option appears in Browse Channels.
- Archive confirmation shows the "can view" message.
- Favourites header logic counts archived channels.
- The websocket handler does not kick the user out.

The only way to turn this off is an explicit `"false"`. The tests cover this in `app/queries/servers/system.test.ts:692-717`. The Detox side agrees: `detox/shared/server-baseline.ts:80` marks the key `absentIsBaseline: true`, and `detox/e2e/support/server_api/system.ts:139` notes that "Mobile treats a missing ExperimentalViewArchivedChannels as enabled."

The helper's TODO says it can be removed, with all callers treating archived channels as always viewable, once servers ≤ v10.11 are dropped.