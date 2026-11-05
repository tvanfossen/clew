**Short answer:** the app treats the setting as on unless the server sends the exact string `'false'`. When the server omits it, the app behaves as if it is on.

**How the flag is read**

- `archivedChannelsViewable(value?)` returns `value !== 'false'` (`app/queries/servers/system.ts:304`).
- `canViewArchivedChannels(database)` (`system.ts:306`) reads the `ExperimentalViewArchivedChannels` config value and passes it through that check. It is the one-shot read.
- `observeCanViewArchivedChannels(database)` (`system.ts:310`) is the reactive version. It maps the config value through the same check and uses `distinctUntilChanged()`.

**Every place the behaviour depends on it**

| Location | What changes when viewable is false |
|---|---|
| `archiveChannel` (`app/actions/remote/channel.ts:1390`) | Viewable: after the server delete, the channel is kept locally with a `delete_at` timestamp. Not viewable: the current user is removed from the channel locally. |
| `handleChannelDeletedEvent` (`app/actions/websocket/channel.ts:441`) | Viewable: only `delete_at` is set. Not viewable: if the archived channel is the current one, the user is kicked out with `Events.CHANNEL_ARCHIVED`, and the user is removed from the channel locally. Both paths are skipped while the channel is being left or archived. |
| `searchPosts` (`app/actions/remote/search.ts:58`) | Sends `include_deleted_channels: viewArchivedChannels` to the server search, so archived-channel results are only requested when viewable. |
| Archive screen `onPressAction` (`app/screens/channel_settings/archive/archive.tsx:111`) | Calls `close(!canViewArchivedChannels)` after a successful archive. The `close` parameter's exact effect is not visible in the index. |
| Archive screen props (`archive.tsx:19`, `:73`) | Receives `canViewArchivedChannels` from `observeCanViewArchivedChannels` via `app/screens/channel_settings/archive/index.ts`. |
| Browse Channels index (`app/screens/browse_channels/index.ts`) | Wired to `observeCanViewArchivedChannels` per the caller edges. I did not read the body. |
| Sidebar category header (`app/screens/home/channel_list/categories_list/categories/header/index.ts`) | Wired to `observeCanViewArchivedChannels` per the caller edges. I did not read the body. |

One related spot is not a gate on the setting. `BrowseChannels.onSelectChannel` (`app/screens/browse_channels/browse_channels.tsx:117`) branches on `channel.delete_at`, not on the flag. Its comment assumes that archived channels shown in Browse are only visible when the setting is enabled.

**When the server does not send the setting**

- `getConfigValue` returns `undefined`, so `archivedChannelsViewable(undefined)` returns `true`.
- Every gate above therefore takes the viewable path: archived channels stay local, search includes deleted channels, and websocket archive events do not kick the user out.
- Only an explicit `'false'` turns the feature off. The source comment at `system.ts:297` says the setting is deprecated and was the last gate on viewing archived channels.
- The test suite agrees. `app/queries/servers/system.test.ts:692` asserts that `canViewArchivedChannels` resolves `true` when the key is absent.
- The Detox side matches. `CONFIG_BASELINE` (`detox/shared/server-baseline.ts:80`) marks it `absentIsBaseline: true`, and `waitForClientConfigFlag` (`detox/e2e/support/server_api/system.ts:120`) accepts an absent value as enabled when `acceptAbsentAsEnabled` is set. Its comment says failed fetches are not treated as absent.