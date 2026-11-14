**Short answer:** `ExperimentalViewArchivedChannels` is a single client-side switch. Only the string `'false'` turns it off. Anything else, including the setting being absent, leaves archived channels viewable.

**How the flag is read**

- `archivedChannelsViewable(value)` returns `value !== 'false'` (`app/queries/servers/system.ts:304`).
- `canViewArchivedChannels(database)` reads the config value and applies that check (`system.ts:306`). It is the async, one-shot form.
- `observeCanViewArchivedChannels(database)` does the same from `observeConfigValue`, then `distinctUntilChanged()` (`system.ts:310`). It is the reactive form that the UI uses.

**Where the behaviour depends on it**

Non-exhaustive count is 13 call sites in the index. Grouped by what changes:

| Area | Location | With flag on (or absent) | With flag `'false'` |
|---|---|---|---|
| Archiving a channel | `archiveChannel` in `app/actions/remote/channel.ts:1390` | Sets `delete_at` locally, so the channel stays in the local DB as archived | Removes the current user from the channel locally |
| Delete/archive WebSocket event | `handleChannelDeletedEvent` in `app/actions/websocket/channel.ts:441` | Only updates `delete_at` | If the user is viewing that channel, kicks them out (`Events.CHANNEL_ARCHIVED`), then removes the user from the channel |
| Unarchive WebSocket event | `handleChannelUnarchiveEvent` (`websocket/channel.ts:71`) | Sets `delete_at` to 0 (not gated by the flag) | Same |
| Post search | `searchPosts` in `app/actions/remote/search.ts:58` | Sends `include_deleted_channels: true` to the server | Sends `false` |
| Channel settings archive screen | `app/screens/channel_settings/archive/index.ts:21` and `archive.tsx` | Uses the "can view archived" archive-description copy. After archiving, it closes only the current screen (`close(!canViewArchivedChannels)`) | Uses the "cannot view" copy and pops to root after archiving |
| Browse channels | `app/screens/browse_channels/index.ts:21`, `channel_dropdown.tsx`, `dropdown_slideup.tsx`, `search_handler.tsx`, `browse_channels.tsx` | Shows the "Archived Channels" option in the dropdown, which adds a bottom-sheet row and a snap-point item | Hides the option |
| Channel list categories | `app/screens/home/channel_list/categories_list/categories/header/index.ts:15` | Passed into `CategoryModel.observeHasChannels(canViewArchived, …)` (`app/database/models/server/category.ts:107`) so archived channels count as channels in the header | Only non-deleted channels count (the `delete_at === 0` filter). Caller of `observeHasChannels` is not resolved in the index, so I did not confirm this path end to end |

**When the server does not send the setting**

`getConfigValue` returns `undefined` when there is no row for the key (`system.ts:170`). `archivedChannelsViewable(undefined)` is `true`, so the app behaves as if the flag is **on**:

- Archiving keeps the channel locally with `delete_at` set.
- The archived dropdown option is shown.
- Search asks the server to include deleted channels.
- The "can view archived" copy is used.

I'm inferring that a missing key in the config table means the server did not send it. I didn't open the code that populates that table, so that link is not verified from the index. Also, the index has no entry for the server-side meaning of the flag, so this describes client behaviour only.