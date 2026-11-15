The setting is a single client-side gate with one rule: only an explicit `'false'` turns archived-channel viewing off. Absent, `undefined`, or `'true'` all mean on.

**The gate**

`app/queries/servers/system.ts:297-315` holds the only logic:

```ts
const archivedChannelsViewable = (value?: string) => value !== 'false';
```

`canViewArchivedChannels()` (async) and `observeCanViewArchivedChannels()` (observable, with `distinctUntilChanged`) both read `ExperimentalViewArchivedChannels` from the server config and pass it through this function. Every behaviour below goes through one of these two.

**Where the behaviour depends on it**

| # | Location | What changes when the value is `false` (true = on) |
|---|---|---|
| 1 | `app/actions/websocket/channel.ts:463` | When a channel is archived over the websocket and the setting is off, the app kicks the user out if that channel is current (`handleKickFromChannel` with `CHANNEL_ARCHIVED`) and removes the user's membership. When on, the membership is kept. |
| 2 | `app/actions/remote/channel.ts:1397` (`archiveChannel`) | On success, if on, the app sets `delete_at` locally so the channel stays as an archived membership. If off, it removes the current user from the channel locally. |
| 3 | `app/actions/remote/search.ts:62-73` (`searchPosts`) | Sends `include_deleted_channels` to the server with the value of the setting, so archived channels appear in search results only when on. |
| 4 | `app/screens/browse_channels/index.ts:21` → `dropdown_slideup.tsx:74`, `browse_channels.tsx:190-195`, `search_handler.tsx:196`, `channel_dropdown.tsx:67` | Controls whether the "Archived Channels" entry appears in the Browse Channels dropdown and whether the archived list is populated. |
| 5 | `app/screens/browse_channels/browse_channels.tsx:117-139` (`onSelectChannel`) | Not a direct branch on the setting, but the comment relies on it: an archived channel is only visible here to existing members when the setting is on, so the code skips `joinChannel` for archived channels. |
| 6 | `app/screens/home/channel_list/categories_list/categories/header/index.ts:15-22` → `app/database/models/server/category.ts:107-118` (`observeHasChannels`) | When on, a category counts as non-empty if it has any channel with `delete_at === 0` or the current channel, so the header stays visible for a category holding only archived channels. When off, only active channels count. |
| 7 | `app/screens/channel_settings/archive/archive.tsx:109` and `:121` | Chooses the archive confirmation text (`archiveDescriptionCanViewArchived` vs `archiveDescriptionCannotViewArchived`) and calls `close(!canViewArchivedChannels)` after archiving, so the screen closes when the user will lose access to the channel. |

Not gated: `app/screens/home/search/search.tsx:77` hardcodes `include_deleted_channels: true`, so that search path ignores the setting. Detox tests in `detox/` also reference the setting but only for provisioning and test baselines, not app behaviour.

**When the server does not send the setting**

The app treats it as enabled. `archivedChannelsViewable(undefined)` returns `true`, and the existing tests in `app/queries/servers/system.test.ts:692-717` assert this for both the async and observable forms. The code comment at `system.ts:297-303` says the reason: servers newer than v10.11 stopped sending this field because the feature is always on. Older supported servers (down to v5.26.2) still send it, and only an explicit `'false'` disables archived channels. The detox baseline (`detox/shared/server-baseline.ts:80`) marks it `absentIsBaseline: true` for the same reason.

The comment's TODO says these helpers and their callers can be removed once servers ≤ v10.11 are no longer supported. Until then, the app keeps the gate for those older servers.

I did not open the websocket handler's enclosing function name or trace the config-storage path for a missing key. The "absent → true" conclusion rests on the helper's logic and the tests, not on a read of how the config handler stores missing keys.