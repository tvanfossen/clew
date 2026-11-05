The app treats this setting as a single boolean gate, and only an explicit `'false'` turns archived-channel viewing off. If the server omits the key, the app behaves as if it is enabled.

**The gate**

`app/queries/servers/system.ts:304` defines `archivedChannelsViewable = (value?) => value !== 'false'`. It is wrapped by `canViewArchivedChannels` (async, line 306) and `observeCanViewArchivedChannels` (observable, line 310, with `distinctUntilChanged`). Both read the `ExperimentalViewArchivedChannels` row from the server config table. The comment at lines 297–303 says the setting is deprecated: servers newer than v10.11 stopped sending it, while older supported servers (down to v5.26.2) still send it and may have turned it off.

**Where the behaviour depends on it**

| Location | When the flag is viewable (true, or absent) | When it is `'false'` |
|---|---|---|
| `app/actions/remote/channel.ts:1397` (`archiveChannel`) | Sets local `delete_at` so the channel stays visible as archived | Removes the current user from the channel locally |
| `app/actions/websocket/channel.ts:463` (channel-deleted WebSocket handler) | Keeps the archived channel in the local DB | If the user is viewing it, kicks them out with `CHANNEL_ARCHIVED`, then removes the membership |
| `app/actions/remote/search.ts:62–73` (`searchPosts`) | Sends `include_deleted_channels: true` to the server | Sends `false` |
| `app/screens/channel_settings/archive/index.ts` and `archive.tsx:109–121` | Uses the "can view archived" confirmation message; calls `close(false)` after archiving | Uses the "cannot view" message; calls `close(true)` after archiving |
| `app/screens/browse_channels/index.ts:21` and `browse_channels.tsx:190` | Passes `canShowArchivedChannels` into the search handler and shows the archived-channels option in the browse UI | Hides the option. The screen still renders if shared channels are enabled |
| `app/screens/browse_channels/browse_channels.tsx:126–144` (`onSelectChannel`) | Archived channels skip `joinChannel` and call `fetchMyChannel` then `switchToChannelById` | Not gated by the flag itself. The comment assumes the flag is on, because archived channels only appear in browse when it is |
| `app/screens/home/channel_list/categories_list/categories/header/index.ts:15–22` and `app/database/models/server/category.ts:107–118` | Counts archived channels as "has channels", except that a current archived channel always counts | Counts only channels with `delete_at === 0` |

`browse_channels/channel_dropdown.tsx` and `dropdown_slideup.tsx` also take `canShowArchivedChannels` and conditionally render the archived option.

**When the server does not send the setting**

The value is `undefined`, and `archivedChannelsViewable(undefined)` returns `true`. So the app behaves as if archived channels are enabled everywhere in the table above. This is confirmed by unit tests in `app/queries/servers/system.test.ts:692–717` for both the query and observable forms. The Detox side agrees: `detox/shared/server-baseline.ts:80` marks the key `absentIsBaseline: true`, and `detox/e2e/support/server_api/system.ts:139–144` says "Mobile treats a missing ExperimentalViewArchivedChannels as enabled". Only a successful config payload with the value missing is treated this way. Failed fetches keep polling.

**Points to note**

- The app does not check server version to decide this. It relies on the server omitting the key on newer servers, which is an assumption in the code comment. I did not verify the server side.
- The TODO at `system.ts:302` plans to delete these helpers once servers at or below v10.11 are dropped, after which archived channels are always viewable.
- Only a `'false'` string turns the feature off. Other values such as `'0'` or `'False'` are treated as enabled, since the check is an exact string comparison.