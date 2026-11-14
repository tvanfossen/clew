**Short answer:** the app treats `ExperimentalViewArchivedChannels` as a single "can this user see archived channels" switch. Only an explicit `'false'` turns it off. If the server omits the setting, the app behaves as if it is `true`, so archived channels are on.

**How the value is read**

`app/queries/servers/system.ts:304` defines `archivedChannelsViewable = (value) => value !== 'false'`. Two public helpers wrap it:
- `canViewArchivedChannels(database)` (line 306): one-shot read, used in actions.
- `observeCanViewArchivedChannels(database)` (line 310): observable, `distinctUntilChanged`, used in screens.

The comment at lines 297–303 records the intent: servers newer than v10.11 stopped sending the key, and older supported servers (down to v5.26.2) still send it and may have disabled it. There is a TODO to delete these helpers once v10.11 and older are dropped.

**Every place the behaviour depends on it**

| Location | What changes |
|---|---|
| `app/actions/remote/channel.ts:1397` (`archiveChannel`) | If viewable, archive sets `delete_at` locally via `setChannelDeleteAt` and keeps the channel in the sidebar. If not, the user is removed from the channel locally (`removeCurrentUserFromChannel`). |
| `app/actions/websocket/channel.ts:463` (`handleChannelDeletedEvent`) | On a channel-deleted event: if not viewable, kick the user out of the current channel (`Events.CHANNEL_ARCHIVED`) and remove membership. If viewable, only the `delete_at` is stored. |
| `app/actions/remote/search.ts:62–73` (`searchPosts`) | Sends `include_deleted_channels` to the server, so search results include archived channels only when viewable. |
| `app/screens/browse_channels/index.ts:21` → `browse_channels.tsx:190`, `channel_dropdown.tsx:67`, `dropdown_slideup.tsx:74` | The channel-type dropdown is shown if archived OR shared channels are enabled. The "Archived Channels" option only appears when viewable. |
| `app/screens/browse_channels/search_handler.tsx:196` | Chooses the `archivedChannels` list for the ARCHIVED tab. |
| `app/screens/browse_channels/browse_channels.tsx:121–126` | `onSelectChannel` skips `joinChannel` for archived channels and calls `fetchMyChannel` + `switchToChannelById`. The comment assumes archived channels only show to existing members when the setting is enabled. |
| `app/screens/channel_settings/archive/index.ts:21` → `archive.tsx:109,121` | Archive confirmation text differs ("can view archived" vs "cannot view archived"). After archiving, `close(!canViewArchivedChannels)` closes the screen when the channel will disappear. |
| `app/database/models/server/category.ts:107` (`observeHasChannels`) via `app/screens/home/channel_list/categories_list/categories/header/index.ts:15–22` | Category header counts archived channels as "has channels" only when viewable (the current channel is always counted). |

Not app code: `detox/shared/server-baseline.ts:80` marks the key `absentIsBaseline: true`, and `detox/e2e/support/server_api/system.ts:139–142` accepts an absent key as enabled. Detox tests also assert the key is explicitly `'true'` in several archive specs.

**What the app does when the server omits the setting**

The value is `undefined` in both helpers. `undefined !== 'false'` is `true`, so:
- archive keeps channels visible with `delete_at` set, instead of removing membership;
- websocket channel-deleted events do not kick the user out;
- search sends `include_deleted_channels: true`;
- the Browse Channels "Archived" tab is shown;
- the category header counts archived channels;
- the archive dialog uses the "can view archived" message.

The unit tests confirm this: `app/queries/servers/system.test.ts:692` and `:706` expect `true` when the key is absent, for both the one-shot and observable helpers.

**Caveat:** I did not trace `getConfigValue`/`observeConfigValue` to confirm the exact missing-row path. The tests cover that path, so I am relying on them.