**Short answer:** `ExperimentalViewArchivedChannels` is a single gate with one rule: only an explicit `'false'` turns archived-channel viewing off. Any other value, including the setting being absent, turns it on. When the server doesn't send it, the app behaves as if the feature is enabled.

## The gate

All checks go through one helper in `app/queries/servers/system.ts`:

- Line 304: `const archivedChannelsViewable = (value?: string) => value !== 'false';`
- Line 306: `canViewArchivedChannels(database)` (async, reads the stored config value)
- Line 310: `observeCanViewArchivedChannels(database)` (observable, re-emits when the stored value changes)

The comment above the helper explains the rule. Servers newer than v10.11 stopped sending the setting because the feature is always on. Servers from v5.26.2 up to v10.11 still send it and may have disabled it. The file also has a TODO to remove the helpers and treat archived channels as always viewable once those older servers are dropped.

## Where the behaviour depends on it

| # | Location | When viewable (absent or `'true'`) | When `'false'` |
|---|---|---|---|
| 1 | `app/screens/browse_channels/index.ts:21` → `browse_channels.tsx:190`, `channel_dropdown.tsx:67`, `dropdown_slideup.tsx:74` | Dropdown is shown with an "Archived Channels" option | Archived option is hidden. The dropdown only appears if shared channels are enabled. |
| 2 | `app/screens/home/channel_list/categories_list/categories/header/index.ts:15-22` → `app/database/models/server/category.ts:107-118` | A category counts as non-empty if it has archived channels (the current channel is always counted) | Only non-archived channels count, so a category holding only archived channels can be hidden |
| 3 | `app/screens/channel_settings/archive/index.ts:21`, `archive.tsx:109,121` | Archive confirmation uses the "can view archived" text. After archiving, the screen stays open. | Uses the "cannot view archived" text. After archiving, it pops to the root. |
| 4 | `app/actions/remote/channel.ts:1397-1401` (`archiveChannel`) | Sets `delete_at` locally, so the channel stays in the list as archived | Removes the current user from the channel instead |
| 5 | `app/actions/websocket/channel.ts:463-468` (channel archived event) | No extra action | If the user is in the archived channel, kicks them out (`handleKickFromChannel`), then removes them from the channel |
| 6 | `app/actions/remote/search.ts:62,73` | Sends `include_deleted_channels: true` with post search | Sends `false`, so archived-channel results are excluded |

One related point: `browse_channels.tsx` (around lines 139-144) opens an archived channel via `fetchMyChannel` instead of `joinChannel`. That branch is keyed on `delete_at > 0`, not on this setting, so the flag only controls whether the archived option is reachable in the first place.

## When the server does not send the setting

The app treats it as **enabled**. `getConfigValue` and `observeConfigValue` return `undefined` when there is no stored row (`system.ts:170-173`, `266-270`). The helper then returns `true`. The unit tests in `app/queries/servers/system.test.ts:692-717` cover absent, `'true'` and `'false'`.

Two consequences to keep in mind:

- **Pre-sync state looks the same as absent.** A missing row is indistinguishable from "server didn't send it", so before client config has been stored, archived UI is also enabled. The code does not separate "not loaded yet" from "not sent".
- **Test tooling follows the same rule.** `detox/e2e/support/server_api/system.ts:128-144` accepts an absent value as enabled, but only when the expected value is `'true'`. `detox/shared/server-baseline.ts:80` records the setting with `absentIsBaseline: true`.

I did not run the test suite. The conclusions come from reading the source and the tests.