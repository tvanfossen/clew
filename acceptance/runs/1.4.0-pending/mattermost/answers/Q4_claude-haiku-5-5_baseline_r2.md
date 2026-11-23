The setting is a single boolean gate, `canViewArchivedChannels`. Only an explicit string `'false'` turns it off. Everything else, including absence, counts as on. Each place below reads that one helper; none of them reads the raw config value.

**Core logic** (`app/queries/servers/system.ts:297-315`)

```ts
const archivedChannelsViewable = (value?: string) => value !== 'false';
canViewArchivedChannels(db)           // async, reads config row
observeCanViewArchivedChannels(db)    // observable, distinctUntilChanged
```

The comment says servers newer than v10.11 stopped sending the field because the feature is always on. Servers down to v5.26.2 still send it and may have set it to `false`. The TODO says to delete these helpers once those old servers are no longer supported.

**Where the behaviour depends on it**

| Area | Location | When on (true or absent) | When off (`'false'`) |
|---|---|---|---|
| Channel deleted websocket event | `app/actions/websocket/channel.ts:463-468` | Only stores `delete_at`; the user stays a member | If viewing that channel, kicks the user out with the `CHANNEL_ARCHIVED` event. Then removes the current user from the channel locally. |
| Archive a channel | `app/actions/remote/channel.ts:1397-1401` | Sets `delete_at` locally to now | Removes the current user from the channel locally (not awaited) |
| Post search | `app/actions/remote/search.ts:62,73` | Sends `include_deleted_channels: true` | Sends `false` |
| Browse channels, data | `app/screens/browse_channels/index.ts:21,49` | Passes `canShowArchivedChannels` to the screen | Passes `false` |
| Browse channels, UI | `browse_channels.tsx:190-197`, `dropdown_slideup.tsx:74-79` | Shows the channel-type dropdown with an "Archived" option | Dropdown only appears if shared channels are enabled, with no Archived option |
| Browse channels, filter | `search_handler.tsx:39-40` | Archived filter is selectable | Archived filter unavailable |
| Browse channels, select | `browse_channels.tsx:139-141` | Archived channel selected: `fetchMyChannel` then close | Same code path, but the option is hidden |
| Sidebar category header | `categories/header/index.ts:15-22` → `app/database/models/server/category.ts:107-116` | Category counts archived channels as having channels | Only non-archived channels count |
| Archive confirmation | `app/screens/channel_settings/archive/archive.tsx:109,121` | Uses the "can view archived" message and stays on the screen after archiving | Uses the "cannot view" message and pops to root after archiving |

Two things I noticed while reading:

- The search screen hardcodes `include_deleted_channels: true` (`app/screens/home/search/search.tsx:77`). `searchPosts` spreads the params first and then sets `include_deleted_channels` from the gate (`remote/search.ts:72-73`), so the gate wins and the hardcoded value is ignored.
- When the gate is off, `category.observeHasChannels` does not keep the current channel visible if it is archived. With the gate on, it does (`category.ts:111`). That looks inconsistent, but I did not run the app to confirm it.

**When the server does not send the setting**

`getConfigValue` returns `undefined` when there is no config row. `archivedChannelsViewable(undefined)` returns `true`. So the app behaves as if archived channels are viewable:

- Archived channels stay in the user's membership and remain browsable.
- Search includes deleted channels.
- The Archived filter appears in Browse Channels.
- The archive dialog uses the "can view" wording.

This is covered by unit tests in `app/queries/servers/system.test.ts:692-717`. The detox harness follows the same rule: `detox/e2e/support/server_api/system.ts:139-144` treats a missing value as enabled, and `detox/shared/server-baseline.ts:80` marks it `absentIsBaseline: true`.

One caveat: the code does not separate "server omitted the key" from "config not stored yet", so an empty database also reads as enabled. I inferred that from the code and did not test it.