The setting is a one-way kill switch. Only an explicit `"false"` hides archived channels. Anything else, including absence, leaves them on.

**Core logic** (`app/queries/servers/system.ts:297-315`)

- `archivedChannelsViewable(value) = value !== 'false'`. The comment says servers newer than v10.11 stop sending the key, so absent means on. Older servers (down to v5.26.2) may send `'false'`.
- `canViewArchivedChannels(database)` is the async read. `observeCanViewArchivedChannels(database)` is the reactive version, with `distinctUntilChanged`.
- The file carries a TODO to delete these helpers once servers ≤10.11 are dropped and treat archived channels as always viewable.

**Every place the behaviour depends on it**

| Where | What changes when the value is `'false'` |
|---|---|
| `app/actions/websocket/channel.ts:463` (`handleChannelDeletedEvent`) | A channel-archived websocket event kicks the user out if it is the current channel, then removes the user from the channel. When on, the channel stays as an archived membership. |
| `app/actions/remote/channel.ts:1397` (`archiveChannel`) | After the server delete succeeds: when on, it records `delete_at` locally. When off, it removes the current user from the channel locally. |
| `app/actions/remote/search.ts:62-73` (`searchPosts`) | Sends `include_deleted_channels` to the server. Off means search excludes posts from deleted channels. |
| `app/screens/channel_settings/archive/index.ts` → `archive.tsx:109,121` | Archive dialog copy switches between "can view archived" and "cannot view archived". After archiving, the settings screen is closed with `close(!canViewArchived)`. |
| `app/screens/browse_channels/index.ts:21,49` → `browse_channels.tsx:190-195` and `dropdown_slideup.tsx:74-78` | The "Archived Channels" dropdown entry is only rendered when on. The browse screen also shows the dropdown when shared channels are enabled, so the entry can be hidden while the dropdown stays. |
| `app/screens/browse_channels/channel_dropdown.tsx:67-82` | Shows the "Show: Archived Channels" label only when on. |
| `app/screens/browse_channels/search_handler.tsx` | Passes the flag through to its archived-channel results, which exist only when the flag is on. |
| `app/screens/home/channel_list/categories_list/categories/header/index.ts:15-22` → `database/models/server/category.ts:107-110` | `observeHasChannels(canView, currentChannelId)` decides whether a category header counts as having channels, and the archived-channel case depends on `canView`. I read the call site, not the full model method. |
| `app/screens/browse_channels/browse_channels.tsx:126` | Comment only. The "join archived channel" path relies on the flag being on, since archived browse results imply existing membership. It is not a code gate. |

**Test and provisioning references (not app behaviour)**

- `detox/e2e/support/server_api/system.ts:139-143` treats absent as enabled when waiting for the flag.
- `detox/shared/server-baseline.ts:80` marks the key `absentIsBaseline: true`, so an absent key counts as the baseline.
- Several Detox specs assert the baseline `true`, and `browse_channels.e2e.ts:180-185` fails if the shared server has it explicitly `false`.

**When the server does not send the setting at all**

The app treats archived channels as viewable. `value` is `undefined`, so `undefined !== 'false'` is true. Every gate above takes the "on" branch: the archived dropdown entry shows, archiving keeps a local `delete_at` record, websocket archive events keep the membership, search includes deleted channels, and the archive dialog uses the "can view" copy. Existing tests cover this: `system.test.ts:692-717` asserts true for absent, `"true"` and `"false"` in both the async and observable forms.

One gap I did not verify: the absent case depends on the key not being in the local config table. The tests seed it with `handleConfigs`, but I did not check whether a previously stored `'false'` row is cleared when a later client config omits the key. If it is not, a server that stops sending the key could leave a stale `'false'` in the app.