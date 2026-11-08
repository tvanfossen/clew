The setting is a single gate, and the app reads it through one helper. The helper treats a missing value as enabled and only an explicit `'false'` as disabled.

**The gate** (`app/queries/servers/system.ts:297-315`)

```ts
const archivedChannelsViewable = (value?: string) => value !== 'false';
```

- `canViewArchivedChannels(database)` is the async read.
- `observeCanViewArchivedChannels(database)` is the reactive version. It applies `distinctUntilChanged`, so it re-emits only when the boolean flips.

The comment says servers newer than v10.11 stop sending the key, and older supported servers (down to v5.26.2) send it and may have turned it off. A TODO says the helpers can be removed once v10.11 and older are dropped.

**Where the behaviour depends on it**

| # | Location | What changes when viewable is false |
|---|---|---|
| 1 | `app/actions/websocket/channel.ts:463` | On a channel-archived websocket event, the current user is kicked out if the channel is open and their membership is removed. When viewable, the channel is left in place with `delete_at` set. |
| 2 | `app/actions/remote/channel.ts:1397-1401` (`archiveChannel`) | After the server archives the channel, the app either sets `delete_at` locally (viewable) or removes the current user's membership (not viewable). |
| 3 | `app/actions/remote/search.ts:62-73` (`searchPosts`) | Sends `include_deleted_channels` with the value of the gate, so archived-channel posts are included in search only when viewable. |
| 4 | `app/screens/browse_channels/index.ts:21` → `browse_channels.tsx:190-199` | The channel-type dropdown is shown if archived channels are viewable or shared channels are enabled. Archived channels are passed to the dropdown as `canShowArchivedChannels`. |
| 5 | `dropdown_slideup.tsx:74`, `channel_dropdown.tsx:67`, `search_handler.tsx` | The "Archived channels" option only appears when `canShowArchivedChannels` is true. |
| 6 | `app/screens/home/channel_list/categories_list/categories/header/index.ts:15-22` → `app/database/models/server/category.ts:107-118` (`observeHasChannels`) | When viewable, a category counts as non-empty if it has any channel, including archived ones (or the current channel). When not, only channels with `delete_at === 0` count, so an all-archived category can show as empty. |
| 7 | `app/screens/channel_settings/archive/index.ts:21` → `archive.tsx:109-125` | The archive confirmation shows the "can view archived" or "cannot view archived" description. On confirm, the screen closes differently depending on the value (`close(!canViewArchivedChannels)`). |
| 8 | `app/screens/browse_channels/browse_channels.tsx:139-144` (`onSelectChannel`) | Archived channels take a branch that skips `joinChannel` and calls `fetchMyChannel` plus switch. This branch is reached only when archived channels are listed, so it depends on the gate indirectly. The code has no direct check, and the comment states the assumption. |

Detox also encodes the setting. `detox/shared/server-baseline.ts:80` has `absentIsBaseline: true`, so a missing key counts as the baseline. `detox/e2e/support/server_api/system.ts:139-143` accepts an absent key as enabled while polling. `browse_channels.e2e.ts:180-185` fails the test if the value is explicitly `false`.

**When the server does not send the setting**

`getConfigValue` returns `undefined`, so `archivedChannelsViewable(undefined)` returns `true`. Every consumer above therefore behaves as if archived channels are enabled: the archived dropdown appears, archived channels stay in the DB with `delete_at` set, archive keeps membership, search includes deleted channels, and categories count archived channels. The unit test at `app/queries/servers/system.test.ts:692` asserts exactly this.

I did not read the body of `getConfigValue` itself. The "absent means undefined" step is inferred from the helper's signature and that test, not from reading the function.