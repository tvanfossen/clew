The setting is a single boolean, and the app treats it as "on" unless the server explicitly sends `'false'`. Everything that depends on it goes through one helper, so the absent-setting case is the same everywhere.

**The gate.** `app/queries/servers/system.ts:304` defines `archivedChannelsViewable = (value) => value !== 'false'`. It is wrapped by `canViewArchivedChannels` (async, line 306) and `observeCanViewArchivedChannels` (observable, line 310). The raw value comes from the locally stored client config row (`getConfigValue` / `observeConfigValue`, lines 170 and 266).

**Where the behaviour depends on it:**

| # | Location | When viewable (true) | When `'false'` |
|---|---|---|---|
| 1 | `app/actions/websocket/channel.ts:463` (`handleChannelDeletedEvent`) | Channel is only marked archived locally; the user stays a member | If it is the current channel, kick the user out with `CHANNEL_ARCHIVED`; then remove the user from the channel |
| 2 | `app/actions/remote/channel.ts:1397` (`archiveChannel`) | After the server call, set `delete_at` to now and keep the channel | Remove the current user from the channel instead |
| 3 | `app/screens/channel_settings/archive/archive.tsx:109` and `:121` | Show the "can view archived" confirmation text; on success, `close(false)` stays on the screen | Show the "cannot view archived" text; on success, `close(true)` pops to root |
| 4 | `app/screens/browse_channels/index.ts:21` → `browse_channels.tsx:190` and `channel_dropdown.tsx:67` / `dropdown_slideup.tsx:74` | The "Archived channels" filter item is shown; the dropdown appears if archived or shared channels are enabled | The archived item is hidden |
| 5 | `app/actions/remote/search.ts:62` and `:73` | Sends `include_deleted_channels: true` with post search | Sends `false`, so deleted-channel posts are excluded |
| 6 | `app/screens/home/channel_list/categories_list/categories/header/index.ts:15` → `app/database/models/server/category.ts:107-115` | A category counts archived channels as "has channels" (the current channel always counts) | Only non-archived channels count |

Not gated, but worth knowing: `browse_channels.tsx:139` has an archived-channel branch that uses `fetchMyChannel` instead of `joinChannel`. It runs whenever an archived channel is selected, so it only happens in practice when the archived filter is reachable.

**When the server does not send the setting.** `observeCanViewArchivedChannels` emits `true`, and `canViewArchivedChannels` resolves `true`. Every row in the table above therefore takes the "viewable" branch. The unit tests cover this at `app/queries/servers/system.test.ts:692` and `:706`. The code comment at `system.ts:297-300` says servers newer than v10.11 stopped sending the field because the feature is always on there. Older supported servers (down to v5.26.2) still send it and can turn it off explicitly.

**Related details:**
- The Detox side mirrors this. `detox/shared/server-baseline.ts:80` marks the key as `absentIsBaseline: true`, and `detox/e2e/support/server_api/system.ts:139-144` accepts an absent value as enabled only when polling for `'true'`.
- `system.ts:302-303` has a TODO to remove these helpers and their callers once servers at v10.11 or older are dropped, and to treat archived channels as always viewable.

I also noticed a note appended to one file read saying a `dossier` tool was available. It isn't a tool I have, and it had no bearing on this question, so I ignored it. I did not edit any files.