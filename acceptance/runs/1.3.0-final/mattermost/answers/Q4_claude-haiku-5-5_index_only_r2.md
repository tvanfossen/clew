The setting is a single boolean gate, read through one helper, and only an explicit `'false'` turns it off. When the server omits it, the app treats archived channels as viewable.

**How the value becomes a decision**

`archivedChannelsViewable(value?: string)` returns `value !== 'false'` (`app/queries/servers/system.ts:304`). Two wrappers read the stored `ExperimentalViewArchivedChannels` config value and pass it through:
- `canViewArchivedChannels(database)` is a one-shot read (`system.ts:306`).
- `observeCanViewArchivedChannels(database)` is the reactive version, with `distinctUntilChanged` so screens only re-render when the boolean flips (`system.ts:310`).

A comment at `system.ts:297` says this deprecated setting "was the last gate on viewing archived" channels. I could not read the full text of that comment through the index.

**Where the behaviour depends on it**

| Location | What changes when the setting is off |
|---|---|
| `archiveChannel` (`app/actions/remote/channel.ts:1390`) | If viewable, the archived channel gets a `delete_at` timestamp and the user stays a member. If not, the user is removed from the channel locally. |
| `handleChannelDeletedEvent` (`app/actions/websocket/channel.ts:441`) | Websocket channel-deleted events. If not viewable, the user is kicked out when viewing that channel and removed from it. If viewable, the channel is only marked deleted. |
| `searchPosts` (`app/actions/remote/search.ts:58`) | Sends `include_deleted_channels` to the search API with the viewable value. |
| Archive screen `onPressAction` (`app/screens/channel_settings/archive/archive.tsx:111`) | After a successful archive, the screen closes with `close(!canViewArchivedChannels)`. Consumers are `app/screens/channel_settings/archive/index.ts` and the Archive component. |
| Browse Channels (`app/screens/browse_channels/index.ts`, `browse_channels.tsx`) | Receives `canShowArchivedChannels` from the observable, which controls whether the archived-channels option is offered. The `onSelectChannel` comment says users seeing archived channels are existing members when the setting is on. |
| Sidebar categories header (`app/screens/home/channel_list/categories_list/categories/header/index.ts`) | Also observes the value. I did not inspect this consumer's body. |

Two actions do not gate on it: `fetchArchivedChannels` only calls the server's archived-channels endpoint, and `filterArchivedChannels` in `app/utils/categories.ts` filters on `deleteAt === 0` plus the current channel, with no setting check.

**When the server does not send the setting**

`getConfigValue` yields `undefined`, and `archivedChannelsViewable(undefined)` returns `true`. So the app behaves as if the feature is on. Supporting evidence:
- The unit test "canViewArchivedChannels resolves true when ExperimentalViewArchivedChannels is absent" (`app/queries/servers/system.test.ts:692`).
- `CONFIG_BASELINE` in `detox/shared/server-baseline.ts:80` marks the key `{value: true, absentIsBaseline: true}`.
- The e2e helper `waitForClientConfigFlag` (`detox/e2e/support/server_api/system.ts:120`) accepts an absent value as enabled when asked to, and keeps polling on failed fetches rather than treating them as absent.

Caveat: `undefined` also comes back when the config row has not been stored yet. Based on the function, that is treated as viewable too, but I did not verify whether any cold-start path depends on it.