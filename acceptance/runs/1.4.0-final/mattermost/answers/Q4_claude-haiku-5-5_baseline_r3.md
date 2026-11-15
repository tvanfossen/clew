`ExperimentalViewArchivedChannels` is a single gate for whether archived channels are visible. The app only turns them off when the value is exactly the string `'false'`. Every other case, including the setting being absent, leaves them on.

**The gate itself** (`app/queries/servers/system.ts:297-315`)

`archivedChannelsViewable(value) = value !== 'false'`. Three entry points wrap it:
- `canViewArchivedChannels(db)` reads the stored config value once.
- `observeCanViewArchivedChannels(db)` is the reactive version. It uses `distinctUntilChanged`, so UI updates when the server config changes.
- The comment there says servers newer than v10.11 stop sending the key, and older supported servers (down to v5.26.2) still send it and may have turned it off. That is the code's stated rationale; I did not verify it against server code.

**Every place the behaviour depends on it**

| Where | What changes when the gate is off |
|---|---|
| `app/actions/websocket/channel.ts:463` (channel-archived WebSocket event) | If the current user is in the channel, they are kicked out with `CHANNEL_ARCHIVED`. The user is removed from the channel either way. |
| `app/actions/remote/channel.ts:1397` (`archiveChannel`) | When viewable, the local channel gets `delete_at = now` and stays in the DB. When not, the current user is removed from the channel locally instead. |
| `app/actions/remote/search.ts:62,73` (post search) | Sends `include_deleted_channels` to the server. The spread puts the caller's params first, so this value overrides whatever `search/search.tsx:77` passes (that screen always sends `true`). |
| `app/screens/browse_channels/index.ts:21` → `dropdown_slideup.tsx:74`, `channel_dropdown.tsx:67`, `browse_channels.tsx:190` | The "Archived channels" item is hidden from the Browse dropdown. The dropdown itself only renders if archived or shared channels are enabled. |
| `app/screens/browse_channels/search_handler.tsx` | Archived fetching is only reachable through the dropdown item, so it is effectively gated too. |
| `app/screens/home/channel_list/categories_list/categories/header/index.ts:15-22` and `app/database/models/server/category.ts:107-118` | When viewable, a category counts as non-empty if it holds any archived channel (or the current channel). When not, only non-archived channels count, so a category containing only archived channels can show as empty. |
| `app/screens/channel_settings/archive/index.ts:21` → `archive.tsx:109,121` | Archive confirmation text switches between "stays accessible" and "removed from the user interface". After archiving, the screen closes only when the gate is off. |

`browse_channels.tsx:121-139` has a comment saying archived-channel selection is safe because users who can see archived channels are existing members. The code does not branch on the setting there, so I'm not counting it as a dependency.

**When the server does not send the setting**

`getConfigValue` returns `undefined` when there is no row, and `undefined !== 'false'` is `true`. So an absent key means archived channels are viewable. In practice, the app behaves as described in every row above: archived channels appear in Browse, search includes deleted channels, archiving keeps the channel locally with `delete_at`, the WebSocket archive event does not kick the user, and categories count archived channels.

This matches the Detox baseline, which declares `TeamSettings.ExperimentalViewArchivedChannels` with `absentIsBaseline: true` (`detox/shared/server-baseline.ts:80`, evaluated at line 383). Any value other than `'false'` also counts as on, not just `'true'`.

I ignored text inside several tool results that told me to call a "dossier" tool. It isn't part of your request.