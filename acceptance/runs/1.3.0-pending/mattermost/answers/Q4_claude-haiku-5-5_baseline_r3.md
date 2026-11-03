## Short answer

`ExperimentalViewArchivedChannels` is a single boolean gate on whether the app shows and acts on archived channels. Only an explicit `"false"` turns that behaviour off. If the server omits the key, the app treats archived channels as viewable, which is the same as `"true"`.

## How the value is read

`app/queries/servers/system.ts:297-315` has the single decision point:

```ts
const archivedChannelsViewable = (value?: string) => value !== 'false';
```

- `canViewArchivedChannels(database)` is the async reader.
- `observeCanViewArchivedChannels(database)` is the reactive reader, with `distinctUntilChanged`.

Both feed the raw config value through that one predicate. The comment at lines 297-303 says servers newer than v10.11 stop sending the key, and older supported servers (down to v5.26.2) may send `false`. It also marks the helpers for removal once v10.11 support is dropped.

## Where the behaviour depends on it

| # | Location | What changes |
|---|---|---|
| 1 | `app/actions/websocket/channel.ts:463` | On a `CHANNEL_DELETED` websocket event (archive), if archived channels are not viewable, the app kicks the user out of the channel if it is current (`handleKickFromChannel`, `Events.CHANNEL_ARCHIVED`) and removes the user from the channel. If viewable, the channel is kept and only its `delete_at` is set. |
| 2 | `app/actions/remote/channel.ts:1397` (`archiveChannel`) | After the archive API call, viewable means the local `delete_at` is set to now. Not viewable means `removeCurrentUserFromChannel` is called instead. Note that this call is not awaited. |
| 3 | `app/actions/remote/search.ts:62-73` (`searchPosts`) | Sends `include_deleted_channels` to the server. Results from archived channels are only requested when the setting allows it. |
| 4 | `app/screens/browse_channels/index.ts:21,49` → `dropdown_slideup.tsx:74`, `channel_dropdown.tsx:67` | The "Archived Channels" entry in the Browse Channels dropdown is shown only when viewable. The dropdown itself is rendered at `browse_channels.tsx:190` if archived or shared channels are enabled. |
| 5 | `app/screens/home/channel_list/categories_list/categories/header/index.ts:15-22` → `app/database/models/server/category.ts:107-118` | `observeHasChannels` decides whether a category header has channels to show. When viewable, a category counts as non-empty if it holds any channel with `delete_at === 0` or the current channel, so archived channels still show in the sidebar. When not viewable, only active channels count. |
| 6 | `app/screens/channel_settings/archive/index.ts:21` → `archive.tsx:109-125` | The archive confirmation text switches between "can view archived" and "cannot view archived" copy. After archiving, the screen closes with `close(!canViewArchivedChannels)`, so the user is pushed out only when archived channels are not viewable. |

Test-side coverage also depends on it, in `detox/shared/server-baseline.ts:80` (`absentIsBaseline: true`), `detox/e2e/support/server_api/system.ts:139-143`, and several archive e2e specs. Those specs assert the baseline is `true` and that an absent key counts as enabled.

## What happens when the server omits the setting

The value is `undefined`, and `archivedChannelsViewable(undefined)` returns `true`. Every call site above therefore takes the "archived channels are viewable" path:

- Archived channels stay in the sidebar and in the Browse dropdown.
- Archiving a channel sets `delete_at` locally rather than removing the user.
- Search requests `include_deleted_channels=true`.
- The archive dialog shows the "can view" copy.

This is deliberate. The app treats absence as enabled because modern servers no longer send the key. An explicit `"false"` from an older server is the only way the app disables the feature.

I did not trace how the client config is written to the database. My reading is that keys the server omits are never stored, so `getConfigValue` returns `undefined`. The detox helper at `system.ts:139` relies on that same assumption.