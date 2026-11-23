**Short answer:** the setting is a single boolean gate, `canViewArchivedChannels`, and the app treats it as enabled unless the server explicitly sends `"false"`. If the server omits it, the app behaves as if it is enabled.

**The gate** (`app/queries/servers/system.ts:297-315`)

- `archivedChannelsViewable(value) = value !== 'false'`. Only an explicit `'false'` turns archived-channel viewing off. `undefined`, `'true'`, or any other string leave it on.
- `canViewArchivedChannels(database)` is the async read. `observeCanViewArchivedChannels(database)` is the observable version. Both use the same predicate, and the observable applies `distinctUntilChanged`.
- The code comment says servers newer than v10.11 stopped sending the key, and older supported servers (down to v5.26.2) still send it and may have turned it off. It also has a TODO to delete these helpers once v10.11 and older are dropped.

**Every place the behaviour depends on it**

| Location | What it does with the value |
|---|---|
| `app/actions/remote/channel.ts:1397` (`archiveChannel`) | If viewable, sets `delete_at` locally so the channel stays in the list as archived. If not, calls `removeCurrentUserFromChannel` instead. |
| `app/actions/websocket/channel.ts:463` (`handleChannelDeletedEvent`) | If not viewable, kicks the user out if they are on that channel (`handleKickFromChannel` with `CHANNEL_ARCHIVED`), then removes them from the channel. If viewable, only sets `delete_at`. |
| `app/actions/remote/search.ts:62-73` (`searchPosts`) | Passes the value as `include_deleted_channels` in the search request, so archived-channel results are returned only when viewable. |
| `app/screens/browse_channels/index.ts:21` → `browse_channels.tsx:126` | Exposes `canShowArchivedChannels` to the Browse Channels screen. `onSelectChannel` has a branch for channels with `delete_at > 0` that uses `fetchMyChannel` and skips `joinChannel`. The comment states this path assumes archived channels are visible in Browse only when the setting is enabled. |
| `app/screens/home/channel_list/categories_list/categories/header/index.ts:15-22` | Feeds `category.observeHasChannels(canView, currentChannelId)`, which affects whether a category header shows when it has channels. I did not read the body of `observeHasChannels`, so I can't say exactly how it uses the flag. |
| `app/screens/channel_settings/archive/index.ts:21` → `archive.tsx:109-125` | Chooses between the "can view archived" and "cannot view archived" archive confirmation text. After archiving, `close(!canViewArchivedChannels)` is called. I did not confirm what the `close` argument means. |
| `app/screens/browse_channels/search_handler` (via `index.ts`) | Receives `canShowArchivedChannels` as a prop. I did not open the component to confirm how it uses it. |

**When the server does not send the setting**

The app treats archived channels as viewable:

- `canViewArchivedChannels` resolves `true`, and `observeCanViewArchivedChannels` emits `true`. Both are covered by tests in `app/queries/servers/system.test.ts:692-717`.
- Archiving keeps the channel with a `delete_at` (the "can view" path).
- Search includes deleted channels.
- Browse shows archived channels.

Only an explicit `'false'` produces the opposite behaviour. The Detox side agrees: `detox/shared/server-baseline.ts:80` marks the key with `absentIsBaseline: true`, and `detox/e2e/support/server_api/system.ts:139` says "Mobile treats a missing ExperimentalViewArchivedChannels as enabled."