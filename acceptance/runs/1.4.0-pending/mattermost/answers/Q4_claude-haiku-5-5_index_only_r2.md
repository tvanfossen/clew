**Short answer:** the setting is a single boolean gate, read through `canViewArchivedChannels` / `observeCanViewArchivedChannels`. Only an explicit string `'false'` turns the feature off. If the server doesn't send the key, the app treats archived channels as viewable, i.e. the feature is on.

**The gate** (`app/queries/servers/system.ts`)

- `archivedChannelsViewable(value)` is `value !== 'false'` (line 304).
- `canViewArchivedChannels(database)` is the async form (line 306). `observeCanViewArchivedChannels(database)` is the observable form, with `distinctUntilChanged` (line 310).
- A comment at lines 297–302 says the setting is deprecated. Servers newer than v10.11 stop sending it, and servers down to v5.26.2 still send it and may have disabled it. It also says a TODO exists to remove these helpers once those old servers are dropped.

**Where the behaviour depends on it**

| Location | When viewable (absent or not `'false'`) | When `'false'` |
|---|---|---|
| `app/actions/remote/channel.ts` `archiveChannel` (~1390) | Archive keeps the channel locally and sets `delete_at` to now | Current user is removed from the channel locally, and the channel is dropped from its managed category |
| `app/screens/channel_settings/archive/archive.tsx` `onPressAction` (111–123) | Closes the archive screen with `close(false)` | `close(true)` |
| `app/actions/websocket/channel.ts` `handleChannelDeletedEvent` (441–476) | Only updates `delete_at` | If the current channel is the one archived, kicks the user out (`Events.CHANNEL_ARCHIVED`), then removes the user from the channel |
| `app/actions/remote/search.ts` `searchPosts` (~62–73) | Sends `include_deleted_channels: true` with the search request | Sends `false`. This overrides the value in the params; the search screen's `getSearchParams` hardcodes `true` |
| `app/screens/browse_channels/browse_channels.tsx` `onSelectChannel` (117–166) | Archived entries take the `fetchMyChannel` path instead of `joinChannel`, because the user is already a member | Not reached for archived entries |
| Browse Channels screen (`index.ts` observes it; `canShowArchivedChannels` prop) | Archived filter and dropdown option are offered | Hidden. The `ARCHIVED` filter type is in `search_handler.tsx` |
| `app/screens/home/channel_list/categories_list/categories/header/index.ts` (line 15) | Passes `canViewArchived` to `CategoryModel.observeHasChannels` (`app/database/models/server/category.ts:107`) | Filters archived channels out of the category count |

Two of these rows are inferred from the code: the Browse Channels wiring comes from caller edges and the category-header wiring from the variable name. I did not read those function bodies.

**When the server does not send the setting**

`getConfigValue` / `observeConfigValue` return `undefined` for a missing row. `archivedChannelsViewable(undefined)` is `true`, so every row above takes its "viewable" branch. The observable also emits `true` and only changes when the value changes. The same applies before the client config has been fetched, since the row is then also missing. That is an inference from the code, not something I observed at runtime.

**Test and E2E evidence**

- `app/queries/servers/system.test.ts:692` asserts that `canViewArchivedChannels` resolves `true` when the key is absent.
- `detox/shared/server-baseline.ts:80` lists the key with `absentIsBaseline: true`.
- `detox/e2e/support/server_api/system.ts:139` has `waitForClientConfigFlag` accept an absent value as enabled, with a comment saying only an explicit `'false'` disables the feature.

**Caveat:** the check is a strict string comparison, so any value other than the exact string `'false'` (for example `'False'` or `'0'`) also counts as viewable.