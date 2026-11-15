## Short answer

`ExperimentalViewArchivedChannels` is a single boolean gate, and only an explicit `'false'` turns it off. When the server omits the setting, the app treats archived channels as viewable, the same as `'true'`.

## The decision point

`app/queries/servers/system.ts:304`:

```ts
const archivedChannelsViewable = (value?: string) => value !== 'false';
```

Everything else goes through two wrappers around it:

- `canViewArchivedChannels(database)` (`system.ts:306`) reads the stored config value once.
- `observeCanViewArchivedChannels(database)` (`system.ts:310`) observes it, with `distinctUntilChanged`.

A comment at `system.ts:297` says this setting "was the last gate on viewing archived" channels, so it is the deprecated gate.

## Every place the behaviour depends on it

**Data layer (server-side, via `searchPosts`)**

| Site | What changes when viewable |
|---|---|
| `app/actions/remote/search.ts:62` `searchPosts` | Sends `include_deleted_channels: viewArchivedChannels` to the search API, so archived-channel posts come back in search results only when viewable. |

**Write / archive flow**

| Site | When viewable | When not viewable |
|---|---|---|
| `app/actions/remote/channel.ts:1390` `archiveChannel` (check at `:1397`) | Calls `setChannelDeleteAt(now)` locally. The channel stays in the DB as archived. | Calls `removeCurrentUserFromChannel`, so the channel is dropped locally. |
| `app/actions/websocket/channel.ts:441` `handleChannelDeletedEvent` (check at `:463`) | Only stores `delete_at`. | If the user is in that channel, `handleKickFromChannel(…, CHANNEL_ARCHIVED)` runs. Then the user is removed from the channel locally. |

Both paths also call `removeChannelFromManagedCategoryIfNeeded`. The websocket handler returns early, before any of this, if the channel is in the ephemeral "leaving" or "archiving" set.

**UI**

| Site | Effect |
|---|---|
| `app/screens/browse_channels/index.ts:21` (`canShowArchivedChannels`) | Controls whether archived channels appear in Browse Channels. |
| `app/screens/browse_channels/browse_channels.tsx:117` `onSelectChannel` | The comment says archived-channel selection assumes the setting is enabled. For a channel with `delete_at > 0` the code skips `joinChannel` and calls `fetchMyChannel`, then switches to the channel. This branch is a comment-level dependency, not an explicit gate. |
| `app/screens/channel_settings/archive/index.ts:19` and `archive.tsx:111` `onPressAction` | Supplies `canViewArchivedChannels` as a prop. After a successful archive, `close(!canViewArchivedChannels)` is called with the inverse. I did not confirm exactly what that argument controls. |
| `app/screens/home/channel_list/categories_list/categories/header/index.ts:14` | `CategoryModel.observeHasChannels(canView, currentChannelId)` (`app/database/models/server/category.ts:107`). When viewable, a category counts as non-empty if it has any active channel or the current channel. When not viewable, only active channels count, so a category holding only archived channels can disappear. |

**Test and provisioning (not app runtime)**

- `detox/shared/server-baseline.ts:80` sets `TeamSettings.ExperimentalViewArchivedChannels` to `{value: true, absentIsBaseline: true}`.
- `detox/e2e/support/server_api/system.ts:139` `waitForClientConfigFlag` accepts an absent value as enabled only when `acceptAbsentAsEnabled` is set. Its comment says "Mobile treats a missing … as enabled."
- Several e2e specs assert or wait on this baseline. `channel_bookmarks_permissions.e2e.ts:67` also has a comment about the channel list when the setting is `false`.

## When the server does not send the setting

- `getConfigValue` returns `undefined`, and `archivedChannelsViewable(undefined)` returns `true`.
- So every site above behaves as if the setting were `'true'`: archived channels are kept locally and shown in Browse Channels, search includes deleted channels, and archiving keeps the channel with `delete_at` set.
- `observeCanViewArchivedChannels` also emits `true` when the config row is missing. The index does not distinguish "not yet loaded" from "absent", so before the client config syncs the app also takes the viewable path. That is inferred from the code, not confirmed by a test.
- The app's own unit test, `app/queries/servers/system.test.ts:692`, is titled "canViewArchivedChannels resolves true when ExperimentalViewArchivedChannels is absent", which matches this.