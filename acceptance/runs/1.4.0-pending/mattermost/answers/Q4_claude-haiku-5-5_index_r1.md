**Short answer:** the setting is a kill switch. Only an explicit `'false'` turns archived-channel behaviour off. If the server doesn't send the key, the app treats archived channels as viewable, the same as `'true'`.

## How the value is read

All reads go through one helper, `archivedChannelsViewable(value) => value !== 'false'` (`app/queries/servers/system.ts:304`). Two exported wrappers use it:

- `canViewArchivedChannels(db)` (async, `system.ts:306`)
- `observeCanViewArchivedChannels(db)` (observable, `system.ts:310`)

Both read the `ExperimentalViewArchivedChannels` row from the client config table. A missing row gives `undefined`, which passes the check. The source comment at `system.ts:297-303` says this is because servers newer than v10.11 stopped sending the key, and older ones (down to v5.26.2) still send it and may have turned it off.

## Every place the behaviour depends on it

| Area | File:line | Effect when viewable | Effect when `'false'` |
|---|---|---|---|
| Browse Channels screen | `screens/browse_channels/index.ts:21`, `browse_channels.tsx:190` | Channel-type dropdown is shown (alongside shared channels) | Dropdown is hidden unless shared channels are on |
| Browse Channels dropdown | `channel_dropdown.tsx:67`, `dropdown_slideup.tsx:74` | "Archived Channels" option is offered | Option is removed |
| Browse Channels select | `browse_channels.tsx:139-144` | Archived channel is opened via `fetchMyChannel` and `switchToChannelById`, skipping `joinChannel` | — (this branch depends only on `delete_at`, not the flag) |
| Category header | `categories/header/index.ts:15-22`, `models/server/category.ts:107-118` | Category counts archived channels that are the current channel as "has channels" | Only active channels count |
| Archive dialog | `channel_settings/archive/index.ts:21`, `archive.tsx:109,121` | Message says archived channels can still be viewed; after archiving, the screen pops only to the previous screen | Cannot-view message; screen pops to root |
| Archive action | `actions/remote/channel.ts:1397-1401` | Sets `delete_at` locally and keeps the user in the channel | Removes the current user from the channel locally |
| Websocket channel-archived event | `actions/websocket/channel.ts:463-468` | Nothing extra; the channel stays visible | Kicks the user out if it is the current channel, then removes membership |
| Post search | `actions/remote/search.ts:62-73` | Sends `include_deleted_channels: true` to the server | Sends `false` |

Two things I did not confirm:
- The Browse Channels search handler (`search_handler.tsx`) fetches archived pages whenever the ARCHIVED type is selected. I only saw the dropdown gate it, so I have not verified that the fetch itself is guarded.
- `screens/home/search/search.tsx:77` hardcodes `include_deleted_channels: true`. That search path does not read the flag at all.

## What happens when the server does not send the setting

The app behaves as if it were `'true'`, so archived channels are fully on:

- `canViewArchivedChannels` and `observeCanViewArchivedChannels` return `true`. The unit tests cover this at `app/queries/servers/system.test.ts:692-693` and `706-707`.
- The Browse Channels Archived option is shown, archive keeps membership, and post search includes deleted channels.
- Only an explicit `'false'` disables these behaviours.

On the E2E side, the same rule is encoded. `detox/shared/server-baseline.ts:80` marks the key `absentIsBaseline: true`, and `detox/e2e/support/server_api/system.ts:139-143` accepts an absent value as enabled while still polling on failed fetches.