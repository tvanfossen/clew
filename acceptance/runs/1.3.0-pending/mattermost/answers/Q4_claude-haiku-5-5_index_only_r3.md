The setting is read in one place, `app/queries/servers/system.ts`, and it is off only when the server sends the exact string `'false'`. If the server omits it, the app treats archived channels as viewable, the same as `'true'`.

**How the value is interpreted**

- `archivedChannelsViewable(value?)` returns `value !== 'false'` (`system.ts:304`). So `undefined`, `'true'`, or any other string means viewable.
- `canViewArchivedChannels(database)` reads the stored client-config value and applies that rule (`system.ts:306`).
- `observeCanViewArchivedChannels(database)` is the reactive version. It observes the same key, maps through the same rule, and suppresses repeats with `distinctUntilChanged` (`system.ts:310`).
- `getConfigValue` returns `undefined` when no row exists for the key (`system.ts:170`), so "not sent" reaches the rule as `undefined`.

**Every place that depends on it**

1. **`archiveChannel`** (`app/actions/remote/channel.ts:1390`). After `client.deleteChannel`:
   - If viewable, it stamps `delete_at` locally with `setChannelDeleteAt`, so the channel stays visible as archived.
   - If not viewable, it calls `removeCurrentUserFromChannel`, which drops the channel from the user's view.
   - Either way it then removes the channel from managed categories.

2. **`handleChannelDeletedEvent`** (`app/actions/websocket/channel.ts:441`). This is the WebSocket path for a channel being archived by someone else.
   - It always records `delete_at`.
   - If not viewable and the channel is the current one, it calls `handleKickFromChannel` with `Events.CHANNEL_ARCHIVED`.
   - If not viewable, it also calls `removeCurrentUserFromChannel`.
   - It returns early for channels in the ephemeral "leaving" or "archiving" sets, so the local archive action is not processed twice.

3. **`searchPosts`** (`app/actions/remote/search.ts:58`). It passes the flag to the server as `include_deleted_channels`. `fetchRecentMentions` calls this, so recent-mentions results include or exclude posts from archived channels accordingly.

4. **`observeCanViewArchivedChannels`** is the reactive form. The index shows no direct callers, so the UI components that consume it are not visible to me. Their existence is inferred from the `observeConfigValue` caller list, which includes this function.

**What is not gated by the setting**

- `filterArchivedChannels` (`app/utils/categories.ts:30`) always hides channels with `deleteAt !== 0`, except the current channel. It does not read the setting, so the sidebar behaviour depends on whatever `delete_at` values are already stored.
- `fetchArchivedChannels` → `getArchivedChannels` (`GET …/channels/deleted`) and `searchArchivedChannels` (`POST …/channels/search_archived`) make no check of the setting in the index. Their call sites are in UI code that I could not see, so I cannot say whether the UI gates them.

**When the server does not send the setting**

- `getConfigValue` returns `undefined`.
- `archivedChannelsViewable(undefined)` returns `true`.
- So the app behaves as if the feature is on: archived channels are kept with `delete_at` set, `include_deleted_channels` is sent as `true`, and the user is not removed from channels on archive or on the archive WebSocket event.
- Only an explicit `'false'` produces the removal and kick behaviour.

**Caveats**

- I found no default value declared for this key (`config_defaults` is empty), so the "absent means on" behaviour comes from the comparison in the code, not a declared default.
- The index does not show which code writes the config row from the server response, so I could not verify how a missing key is stored.