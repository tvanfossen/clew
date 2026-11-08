**Short answer:** the setting is a single boolean gate, `canViewArchivedChannels`. Only an explicit `'false'` turns archived-channel viewing off. If the server omits the key, the app treats archived channels as viewable.

**The gate** (`app/queries/servers/system.ts:297-315`)

- `archivedChannelsViewable(value) = value !== 'false'`
- `canViewArchivedChannels(db)` reads the config value once and applies that check.
- `observeCanViewArchivedChannels(db)` does the same reactively and adds `distinctUntilChanged`.
- The comment says servers newer than v10.11 stopped sending the key, and that older supported servers (down to v5.26.2) may send `false`.

**Where the behaviour depends on it** (non-test code under `app/`)

| Location | When the gate is false | When it is true or absent |
|---|---|---|
| `app/actions/websocket/channel.ts:463` (channel-deleted WS event) | If the current channel was archived, kick the user out with `CHANNEL_ARCHIVED`. Then remove the current user from the channel. | The channel stays in the user's list as an archived channel. |
| `app/actions/remote/channel.ts:1397` (`archiveChannel`) | Remove the current user from the channel locally, instead of stamping `delete_at`. | Stamp `delete_at = now` on the channel locally. |
| `app/actions/remote/search.ts:62-73` (`searchPosts`) | Sends `include_deleted_channels: false`. | Sends `include_deleted_channels: true`. |
| `app/screens/browse_channels/index.ts:21` → `browse_channels.tsx:190`, `channel_dropdown.tsx:67`, `dropdown_slideup.tsx:74` | The "archived channels" entry is hidden from the browse dropdown. The dropdown is only rendered if archived or shared channels are enabled. | The "archived channels" entry is shown. |
| `app/screens/home/channel_list/categories_list/categories/header/index.ts:15-22` | Category headers use `category.observeHasChannels(canView, currentChannelId)`, so archived channels do not count as visible channels. | Archived channels count. |
| `app/screens/channel_settings/archive/index.ts:21` → `archive.tsx:109-121` | Archive dialog shows `archiveDescriptionCannotViewArchived` and closes the screen on archive. | Archive dialog shows `archiveDescriptionCanViewArchived`. |
| `app/screens/browse_channels/browse_channels.tsx:126-139` (comment and `onSelectChannel`) | Comment says archived channels are only reachable when the setting is enabled. The code takes the archived-channel branch when `channel.delete_at > 0`, skipping `joinChannel` and calling `fetchMyChannel` instead. | Same branch. The comment says it assumes existing membership, which holds only when the setting is on. |

**Things I did not confirm**

- `app/screens/home/search/search.tsx:77` hard-codes `include_deleted_channels: true` and does not read this setting. That is a second search path that ignores the gate.
- The `browse_channels.tsx` branch above is the only one I read in full. I did not check whether the browse list query itself filters archived channels by this setting.

**What happens when the server does not send the setting**

The key is absent, `getConfigValue` returns `undefined`, and `archivedChannelsViewable(undefined)` returns `true`. Every row above takes the "true or absent" column: archived channels are viewable, search includes deleted channels, archive keeps the channel visible, and the browse dropdown offers archived channels. This matches the comment that servers after v10.11 no longer send the key, and the unit tests in `app/queries/servers/system.test.ts:692-717`.

The E2E layer uses the same rule. `detox/shared/server-baseline.ts:80` marks the key as `absentIsBaseline: true`, and `detox/e2e/support/server_api/system.ts:139-143` accepts absence as enabled while still polling on failed fetches.

**The gap:** the code only treats an explicit `'false'` as off. If a server ever omits the key while the feature is actually disabled, the app will show archived channels anyway. The code comment acknowledges this by assuming absence only happens on servers where the feature is always on.