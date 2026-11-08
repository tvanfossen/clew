The setting is read in one place, `app/queries/servers/system.ts`, and everything else asks that gate whether archived channels are viewable. The index shows four behavioural branches. It does not show where the value is fetched from the server or stored, and I did not confirm the browse-channels archived view is gated.

**The gate**

- `archivedChannelsViewable(value)` returns `value !== 'false'` (`system.ts:304`).
- `canViewArchivedChannels(database)` reads the `ExperimentalViewArchivedChannels` config value and passes it through that check (`system.ts:306`).
- `observeCanViewArchivedChannels(database)` is the reactive version. It re-emits only when the boolean changes (`system.ts:310`).

**Where the behaviour depends on it**

| Call site | When viewable (value is not `'false'`) | When not viewable (value is `'false'`) |
|---|---|---|
| `archiveChannel`, `app/actions/remote/channel.ts:1390` | Sets the channel's `deleteAt` to now and keeps the user as a member. | Removes the current user from the channel locally. |
| `handleChannelDeletedEvent`, `app/actions/websocket/channel.ts:441` | Only sets `deleteAt`. | If the user is viewing that channel, kicks them out with `CHANNEL_ARCHIVED`. Then removes the user from the channel. |
| `searchPosts`, `app/actions/remote/search.ts:58` | Sends `include_deleted_channels: true` to the server, so archived-channel posts come back in search. | Sends `false`. |
| `observeCanViewArchivedChannels` | Emits `true`. | Emits `false`. |

`archiveChannel` and `handleChannelDeletedEvent` also remove the channel from a managed category in both branches. The category removal is not gated.

**Not gated by the setting, as far as the index shows**

- `fetchArchivedChannels` (`channel.ts:987`) calls `GET /teams/{id}/channels/deleted` with no check on the setting. Its only caller is not indexed, so I could not confirm whether the browse UI checks the setting before calling it.
- `handleArchivedPress` in the browse dropdown (`app/screens/browse_channels/dropdown_slideup.tsx:50`) has no gate in its body.
- The `Archived` post-draft banner (`app/components/post_draft/archived/index.tsx`) does not read the setting.

**Gaps in the index**

- `observeCanViewArchivedChannels` has no indexed callers. Either a component reaches it through a path the index does not resolve, or nothing uses it yet. The search for `CanViewArchived` returned only the two definitions.
- The index records no default value for this key (`config_defaults` is empty), so the default comes only from the code above.

**When the server does not send the setting**

`getConfigValue` returns `undefined` when no row exists for the key. `archivedChannelsViewable(undefined)` evaluates `undefined !== 'false'`, which is `true`. Archived channels are therefore treated as viewable: `archiveChannel` keeps the membership and marks the channel deleted, `handleChannelDeletedEvent` does not kick, and search sends `include_deleted_channels: true`. The app only switches to the restrictive behaviour when the server explicitly sends the string `'false'`.