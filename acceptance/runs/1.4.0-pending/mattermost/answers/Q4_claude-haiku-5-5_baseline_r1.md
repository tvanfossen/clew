The setting is a single "view archived channels" switch, and the app reads it in about ten places. The one-line rule is that only an explicit `'false'` turns archived-channel viewing off. Anything else, including the key being absent, leaves it on.

**Where the value is read**

All gating goes through one helper in `app/queries/servers/system.ts:304-315`:

- `archivedChannelsViewable(value) = value !== 'false'`
- `canViewArchivedChannels(db)` reads it once (async), for actions.
- `observeCanViewArchivedChannels(db)` observes it for UI, with `distinctUntilChanged`.

The callers:

| Area | Location | Effect when enabled | Effect when disabled |
|---|---|---|---|
| Browse Channels, dropdown | `screens/browse_channels/index.ts:21`, `browse_channels.tsx:190-197`, `channel_dropdown.tsx:67`, `dropdown_slideup.tsx:74` | "Archived" filter shown in the dropdown (and the dropdown itself is shown if shared channels is on) | Archived option hidden |
| Browse Channels, search | `search_handler.tsx:27` and the `ARCHIVED` fetch branch (`:160-162`) | Archived fetch available | Only the prop is visible in my reading; I did not confirm the fetch is gated here |
| Sidebar category header | `categories/header/index.ts:15-22` → `database/models/server/category.ts:107-111` | `observeHasChannels` counts archived channels when deciding whether a category has channels | Only non-archived channels count (plus the current channel); I did not read the rest of that method |
| Archive screen copy | `channel_settings/archive/index.ts:21`, `archive.tsx:109` | "You can still view it" description | "Cannot view" description |
| Archive screen navigation | `archive.tsx:121` | Stays in channel settings after archive (`close(false)`) | Closes the screen (`close(true)`) |
| Archive action | `app/actions/remote/channel.ts:1397-1401` | Sets `delete_at` locally, keeps the channel | Removes the current user from the channel locally |
| WebSocket channel-archived event | `app/actions/websocket/channel.ts:463-468` | Only updates `delete_at` | If the user is in that channel, kicks them out (`CHANNEL_ARCHIVED`), then removes membership |
| Search | `app/actions/remote/search.ts:62-73` | Sends `include_deleted_channels: true` | Sends `false` |
| Browse channel tap | `browse_channels.tsx:121-139` | Comment only; the code branches on `channel.delete_at`, not on the setting | — |

**When the server does not send the setting**

The key is simply absent, so `getConfigValue` returns `undefined`, and `archivedChannelsViewable(undefined)` returns `true`. Archived channels are viewable, the archive flow keeps the channel, and the sidebar and search behave as in the enabled case. The same applies while client config has not synced yet.

This is the normal case on modern servers. The comment at `system.ts:297-303` says servers newer than v10.11 stopped sending the key, and older servers (down to v5.26.2) send it and may set it to `false`. The code marks a TODO to remove these helpers once v10.11 and older are dropped.

The Detox side agrees: `detox/shared/server-baseline.ts:80` treats the key as `value: true` with `absentIsBaseline: true`, and `detox/e2e/support/server_api/system.ts:139-143` accepts absence as enabled.

**Caveats**

- I did not read the rest of `category.ts` `observeHasChannels` past line 113, so the non-archived branch is described from its first lines only.
- I did not confirm that `search_handler.tsx` gates its archived fetch on the prop.