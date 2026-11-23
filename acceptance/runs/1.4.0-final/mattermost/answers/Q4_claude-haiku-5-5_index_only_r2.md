The setting is a single server config value, `ExperimentalViewArchivedChannels`. The app reads it in one place and treats only the literal string `'false'` as off. When the server doesn't send it, the app behaves as if it were on.

**How the value is read** (`app/queries/servers/system.ts`)
- `archivedChannelsViewable(value)` returns `value !== 'false'` (line 304).
- `canViewArchivedChannels(database)` (line 306) reads the stored config value and passes it through that check. It is the one-shot async form.
- `observeCanViewArchivedChannels(database)` (line 310) is the reactive form. It maps the same check over `observeConfigValue` and applies `distinctUntilChanged`.

**Where the behaviour depends on it**

| Location | What changes when the setting is off (`'false'`) | What changes when it is on or absent |
|---|---|---|
| `app/actions/remote/channel.ts:1390` `archiveChannel` | Removes the current user from the channel locally. | Sets `delete_at` locally on the channel and keeps the membership row. |
| `app/actions/websocket/channel.ts:441` `handleChannelDeletedEvent` | If the user is viewing the channel, calls `handleKickFromChannel` with `CHANNEL_ARCHIVED`, then removes the user from the channel. | Only records `delete_at`; the channel stays in the local DB. |
| `app/actions/remote/search.ts:58` `searchPosts` (line 62) | Sends `include_deleted_channels: false` to the server. | Sends `include_deleted_channels: true`. |
| `app/screens/browse_channels/index.ts:21` | Passes `canShowArchivedChannels` down to `browse_channels.tsx`, `channel_dropdown.tsx` and `dropdown_slideup.tsx`. The archived filter in `search_handler.tsx:39` only applies when the option is shown. I did not read the exact gating condition. | Same props, with the value set to true. |
| `app/screens/channel_settings/archive/index.ts:21` and `archive.tsx:111-123` | After a successful archive, calls `close(!canViewArchivedChannels)`. I did not read `close`'s signature, so I can't say exactly what the flag does. | Keeps the screen open per the flag's meaning. |
| `app/screens/home/channel_list/categories_list/categories/header/index.ts:15` | Passes the flag into the category header. I inferred that it reaches `CategoryModel.observeHasChannels(canViewArchived, channelId)` (`app/database/models/server/category.ts:107`), but the caller link did not resolve in the index. | When true, archived channels count as channels in the category, plus the currently open one. When false, only channels with `delete_at === 0` count. |

Two more are reached through the same check in the archive flow: `archiveChannel` and `handleChannelDeletedEvent` both call `canViewArchivedChannels`.

**When the server does not send the setting**

`getConfigValue` and `observeConfigValue` return `undefined` when there is no row (`system.ts:170-173` and `266-270`). `archivedChannelsViewable(undefined)` evaluates `undefined !== 'false'`, which is `true`. So an absent setting means:
- Archiving marks channels with `delete_at` and keeps membership.
- Deleted-channel events don't kick the user out.
- Post search asks the server for deleted channels.
- The browse and category UI shows archived channels.

The absent case is therefore the "viewable" path, not the legacy removal path.

**Caveats**
- I did not inspect where the config value is written. The index shows only the read side.
- The `close(!canViewArchivedChannels)` argument and the `canShowArchivedChannels` gating in the dropdowns are unverified beyond the call sites shown above.