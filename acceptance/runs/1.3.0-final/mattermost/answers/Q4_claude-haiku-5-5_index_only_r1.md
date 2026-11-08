**Short answer:** The app treats `ExperimentalViewArchivedChannels` as a gate that is on unless the server sends the exact string `'false'`. When the setting is absent, the app behaves as if it is on: archived channels stay visible and are kept locally.

## How the value is read

- `app/queries/servers/system.ts:304`: `archivedChannelsViewable = (value) => value !== 'false'`. Only an explicit `'false'` turns the feature off. Anything else, including `undefined`, means viewable.
- `canViewArchivedChannels(database)` (`system.ts:306`) is the async read, and `observeCanViewArchivedChannels(database)` (`system.ts:310`) is the reactive version with `distinctUntilChanged`. Both wrap the same predicate.
- The config type is declared at `types/api/config.d.ts:128`, as a string.

## Every place the behaviour depends on it

| Location | Behaviour when viewable (on, or absent) | Behaviour when `'false'` |
|---|---|---|
| `app/actions/remote/channel.ts:1390` `archiveChannel` | Calls `setChannelDeleteAt(now)`, so the archived channel stays in the local DB | Calls `removeCurrentUserFromChannel`, so the channel is dropped locally |
| `app/actions/websocket/channel.ts:441` `handleChannelDeletedEvent` | Only stamps `delete_at` on the channel | If it is the current channel, runs `handleKickFromChannel(..., CHANNEL_ARCHIVED)`; always removes the user from the channel locally |
| `app/actions/remote/search.ts:58` `searchPosts` | Sends `include_deleted_channels: true` to the server | Sends `false` |
| `app/screens/channel_settings/archive/archive.tsx:121` `onPressAction` | After a successful archive, calls `close(!canViewArchivedChannels)` | Closes with the flag inverted |
| `app/screens/browse_channels/index.ts:21` and `browse_channels.tsx:117` `onSelectChannel` | Browse shows archived channels. Selecting one skips `joinChannel`, calls `fetchMyChannel`, then switches. The comment says archived-channel viewers are existing members when the flag is on | The UI gating is in the screen's observed prop (`canShowArchivedChannels`). I did not read the render branch, so I cannot say exactly what hides |
| `app/screens/home/channel_list/categories_list/categories/header/index.ts:15` | Observes `canViewArchived` for the category header | Same gate; I did not read how the header uses it |

The unit test at `app/queries/servers/system.test.ts:692` is named "canViewArchivedChannels resolves true when ExperimentalViewArchivedChannels is absent", which confirms the absent case for the async path.

## When the server does not send the setting

- `canViewArchivedChannels` resolves **true**, because `undefined !== 'false'`.
- Archive keeps the channel locally with `delete_at` set. Websocket delete events do not kick the user out or remove the channel.
- Search asks the server for deleted channels.
- Browse shows archived channels.

The app is designed this way on purpose. The shared baseline at `detox/shared/server-baseline.ts:80` records `TeamSettings.ExperimentalViewArchivedChannels: {value: true, absentIsBaseline: true}`. The e2e helper `waitForClientConfigFlag` (`detox/e2e/support/server_api/system.ts:139`) has `acceptAbsentAsEnabled`, which comments that mobile treats a missing key as enabled and only an explicit `'false'` turns the feature off.

## Notes

- A comment at `system.ts:297` (truncated in the index) calls this setting deprecated and says it was the last gate on viewing archived channels. I did not read the full comment.
- E2E provisioning sets the value to `true` (`detox/maestro/scripts/setup_local.sh`, `detox/maestro/GUIDELINES.md`).
- The `enhanced` symbol name is ambiguous across many files, so I did not use it for the browse and header render logic. Reading those render branches would settle exactly what the UI hides.