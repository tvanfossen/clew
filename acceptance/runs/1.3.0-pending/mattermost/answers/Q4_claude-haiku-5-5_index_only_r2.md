The setting is read in three places. The app's default when the server omits it is to treat archived channels as viewable, which is the opposite of what a reader might assume.

**The gate.** `archivedChannelsViewable(value)` is `value !== 'false'` (`app/queries/servers/system.ts:304`). Only the exact string `'false'` turns the feature off. `true`, any other string, and `undefined` all turn it on. `canViewArchivedChannels` (`system.ts:306`) reads the stored client-config value once. `observeCanViewArchivedChannels` (`system.ts:310`) is the reactive version: it re-emits on config changes and dedupes with `distinctUntilChanged`.

**Every place the behaviour depends on it:**

1. **`archiveChannel`** (`app/actions/remote/channel.ts:1390`). After the server delete succeeds:
   - If viewable, the local channel gets `delete_at` set to now, so it stays in the local DB as an archived channel.
   - If not viewable, the current user is removed from the channel locally.
   - Either way, the channel is then removed from its managed category if needed.

2. **`handleChannelDeletedEvent`** (`app/actions/websocket/channel.ts:441`), the websocket handler for a channel-deleted event. It always stores `delete_at` via `setChannelDeleteAt`. Then, only when not viewable:
   - If the channel is the current one, it kicks the user out with `Events.CHANNEL_ARCHIVED`.
   - It removes the current user from the channel.
   - It also clears the managed category entry.
   - The handler returns early, without this branch, if the channel is currently being left or archived locally (`EphemeralStore`).

3. **`searchPosts`** (`app/actions/remote/search.ts:58`). The value is sent as `include_deleted_channels` in the post-search request, so search results include archived channels only when the setting is viewable.

4. **`observeCanViewArchivedChannels`**. This is the UI-facing reactive gate, but the index shows no resolved callers, so I could not confirm which screens or components observe it. It is the likely source of the archived-channel UI in browse/find channels, but I have not verified that.

**Not gated by it, per the index:** `fetchArchivedChannels` → `getArchivedChannels` (`GET /channels/deleted`) and `searchArchivedChannels` (`POST /channels/search_archived`) have no call path to `canViewArchivedChannels`. Neither does `removeChannelsFromArchivedTeams` in find-channels. Their callers are also unresolved, so I cannot say whether the UI hides them when the setting is off.

**When the server does not send the setting:**
- `getConfigValue` returns `undefined` when no row exists (`system.ts:170`).
- `archivedChannelsViewable(undefined)` returns `true`.
- So the app behaves as if the feature is enabled: archive keeps channels locally with `delete_at` set, archive-deleted events do not kick the user out, and search includes deleted channels.
- The same applies to `observeCanViewArchivedChannels`, which emits `undefined` and then `true`. This means the app gives the enabled behaviour before client config has loaded, too.

The index cannot show where the config row is written from the server response, so I have not confirmed that the server's string value reaches this check unchanged.