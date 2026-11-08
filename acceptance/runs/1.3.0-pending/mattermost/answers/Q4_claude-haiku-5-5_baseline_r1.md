The setting is a single gate, and it is read through one helper. The app treats the setting as **on unless the server explicitly sends `"false"`**. The helper is `archivedChannelsViewable(value) = value !== 'false'` in `app/queries/servers/system.ts:304`, and its comment explains why: servers newer than v10.11 stopped sending the key, while older supported servers (down to v5.26.2) still send it and may have turned it off.

**When the server omits the setting:** `getConfigValue` returns `undefined`, so `undefined !== 'false'` is true. Archived channels are viewable and every feature below behaves as if the setting were `true`. Only `'true'`, absent, or anything other than `'false'` leads to the enabled path. A `'false'` value is the only way to disable it.

**Where the behaviour depends on it**

| Area | Location | When enabled (true / absent) | When `'false'` |
|---|---|---|---|
| Query helpers | `app/queries/servers/system.ts:306,310` (`canViewArchivedChannels`, `observeCanViewArchivedChannels`) | Returns true | Returns false; all callers below use these |
| Server search | `app/actions/remote/search.ts:62,73` | Sends `include_deleted_channels: true` to the server search | Sends `false` |
| Archive a channel | `app/actions/remote/channel.ts:1397-1401` | Sets `delete_at` locally and keeps the user as a member | Removes the current user from the channel locally |
| Archive event from websocket | `app/actions/websocket/channel.ts:463-468` | Does nothing extra | If the archived channel is current, emits `CHANNEL_ARCHIVED` and kicks the user out; then removes the user from the channel |
| Browse Channels | `app/screens/browse_channels/index.ts:21,49`, `browse_channels.tsx:75,190-195` | Shows the archived-channel section/dropdown (also shown when shared channels are on) | Hides it, unless shared channels are enabled |
| Browse dropdown | `dropdown_slideup.tsx:74`, `channel_dropdown.tsx:67` | Shows the "archived channels" option | Hides it |
| Opening an archived channel from Browse | `browse_channels.tsx:139-143` | Uses `fetchMyChannel` path, because archived users are assumed to be existing members | Same code path; the comment assumes the setting is on |
| Archive dialog | `app/screens/channel_settings/archive/index.ts:21`, `archive.tsx:109,121` | Shows `archiveDescriptionCanViewArchived`; closes with `close(false)` | Shows `archiveDescriptionCannotViewArchived`; closes with `close(true)` |
| Sidebar category header | `app/screens/home/channel_list/categories_list/categories/header/index.ts:15-20`, `app/database/models/server/category.ts:107-110` | Archived channels count toward whether a category `hasChannels` | They don't count |

**Places that do not gate on it**

- `app/screens/home/search/search.tsx:77` hard-codes `include_deleted_channels: true`. I only saw that one line and did not read its surrounding logic, so this is an inconsistency to check, not a confirmed bug.
- `use_home_effects.ts:70` listens for `CHANNEL_ARCHIVED` without checking the setting. The gate sits upstream in the websocket handler, so this is expected.

**Tests and E2E**

- `app/queries/servers/system.test.ts:692-717` covers absent, `'true'`, and `'false'` for both helpers.
- `detox/e2e/support/server_api/system.ts:139-144` says mobile treats a missing key as enabled. The poll helper only accepts absence when the expected value is `'true'`, and it keeps polling on failed fetches.
- `detox/shared/server-baseline.ts:80` sets `absentIsBaseline: true` for this key.

**Open points**

- The code comments say the setting is always on for newer servers, and the TODO at `system.ts:302` plans to remove these helpers once v10.11 and older support is dropped.
- I did not check how a stored `'false'` gets written or cleared during config sync. That would be the next thing to confirm if you need the full lifecycle.