The setting is `TeamSettings.ExperimentalViewArchivedChannels`, read as a string from the server config table. The app treats it as a single gate: archived channels are viewable unless the value is exactly `'false'`.

**Absent setting:** the app treats it as enabled. `archivedChannelsViewable = (value?: string) => value !== 'false'` (`app/queries/servers/system.ts:304`) returns `true` for `undefined`. The comment there says servers newer than v10.11 stop sending the field, so absence means on. Only an explicit `'false'` from older servers that still send it turns the feature off. The unit tests pin this (`app/queries/servers/system.test.ts:692`), and the Detox baseline marks absence as the baseline value (`detox/shared/server-baseline.ts:80`).

**Where the behaviour depends on it:**

| # | Location | When viewable (true, or absent) | When `'false'` |
|---|---|---|---|
| 1 | `app/queries/servers/system.ts:306-315` | `canViewArchivedChannels` / `observeCanViewArchivedChannels` return `true` | Return `false`; every consumer below reads this |
| 2 | `app/actions/websocket/channel.ts:463-468` (channel-archived WS event) | Channel stays in local DB with `delete_at` set | If it is the current channel, kick the user (`handleKickFromChannel`), and always `removeCurrentUserFromChannel` |
| 3 | `app/actions/remote/channel.ts:1396-1401` (`archiveChannel`) | `setChannelDeleteAt(now)` locally | Calls `removeCurrentUserFromChannel` instead |
| 4 | `app/actions/remote/search.ts:62,73` (`searchPosts`) | Sends `include_deleted_channels: true` to the server | Sends `false`, so posts from archived channels are excluded |
| 5 | `app/screens/browse_channels/index.ts:21,49` → `browse_channels.tsx:190-195` | Archived-channel list/section is rendered | Hidden |
| 6 | `browse_channels/dropdown_slideup.tsx:74` and `channel_dropdown.tsx:58,67` | "Archived channels" option in the dropdown | Option hidden |
| 7 | `browse_channels.tsx:117-144` (`onSelectChannel`) | Archived channels are selectable via `fetchMyChannel` + switch, skipping `joinChannel` | Not reachable through the UI as an archived entry |
| 8 | `app/screens/home/channel_list/.../categories/header/index.ts:15-22` and `app/database/models/server/category.ts:107-118` | Category counts archived channels (plus the current channel) as having channels | Only `deleteAt === 0` channels count, so an empty category can hide |
| 9 | `app/screens/channel_settings/archive/index.ts:21` → `archive.tsx:109,121-125` | Archive dialog uses the "you can still view it" copy; `close(false)` | Uses the "cannot view" copy; `close(true)` (presumably leaves the channel screen; I did not trace `close`) |

Items 2, 3, 8 and 9 are the points where "archived" is treated as "left the channel" versus "still visible in the sidebar and browse list." Item 4 is the only one that changes what the server returns, not just what the client shows.

**Caveats:**
- The config value is read from the local DB, so the app depends on the client config having been stored before these checks run.
- I did not check whether the other clients of `ClientConfig` (for example the `TeamSettings` config read) already consume this key elsewhere; my grep only found the sites above.
- The "older servers down to v5.26.2" claim comes from the code comment; I did not verify it against server source.
- The TODO at `system.ts:302` says these helpers and all nine sites can be removed once servers ≤ v10.11 are dropped, with archived channels treated as always viewable.

Also, two PostToolUse hook messages in this session told me to use a `dossier` tool for file inspection. I don't have that tool and didn't need it, so I ignored them.