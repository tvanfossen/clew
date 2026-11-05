The setting only has an effect when the server sends it explicitly as `'false'`. Every other case, including absent, leaves archived channels viewable.

**Single decision point**

`app/queries/servers/system.ts:297-315` holds the whole rule:

- `archivedChannelsViewable = (value) => value !== 'false'`
- `canViewArchivedChannels(database)` is the async form and `observeCanViewArchivedChannels(database)` the observable form (with `distinctUntilChanged`). Both read the `ExperimentalViewArchivedChannels` config row.

**Every place the behaviour depends on it**

| Location | When viewable (absent, `'true'`) | When `'false'` |
|---|---|---|
| `app/actions/websocket/channel.ts:463-468` (channel archived/deleted WS event) | Channel stays in the local DB as archived | If the user is viewing that channel, kick them out with `CHANNEL_ARCHIVED`; then remove the current user from the channel locally |
| `app/actions/remote/channel.ts:1397-1401` (`archiveChannel`) | Set `delete_at = now` locally | Remove the current user from the channel locally instead |
| `app/actions/remote/search.ts:62,73` (`searchPosts`) | Sends `include_deleted_channels: true` | Sends `false` |
| `app/screens/browse_channels/index.ts:21,49` → `browse_channels.tsx:75,190` → `channel_dropdown.tsx:67`, `dropdown_slideup.tsx:74` | Archived-channels option shown in Browse Channels; the dropdown renders when this or shared channels is on | Option hidden |
| `app/screens/home/channel_list/categories_list/categories/header/index.ts:15-22` → `app/database/models/server/category.ts:107-110` | Archived channels count toward a category's `hasChannels` | Archived channels are excluded from that check |
| `app/screens/channel_settings/archive/index.ts:21` → `archive.tsx:73,109,121` | Shows the "can view archived" description; the screen stays open after archiving | Shows the "cannot view" description; the screen closes after archiving |

Two things to note:

- `app/screens/home/search/search.tsx:77` hardcodes `include_deleted_channels: true`, so the search screen ignores the setting. Only the `searchPosts` action in `remote/search.ts` honours it.
- The `browse_channels.tsx:126` comment says archived channels can be selected without a join only because the setting is on. That is an assumption about the server, not something the code checks.

**When the server does not send the setting**

The app treats it as enabled. `system.ts:297-303` says servers newer than v10.11 stopped sending the field and that an absent value means on. The unit tests confirm it: `app/queries/servers/system.test.ts:692-693` expects `canViewArchivedChannels` to resolve `true` when the key is absent, and the observable variant at lines 706-707 does the same. The Detox baseline agrees: `detox/shared/server-baseline.ts:80` sets `absentIsBaseline: true`, and `detox/e2e/support/server_api/system.ts:139` says "Mobile treats a missing ExperimentalViewArchivedChannels as enabled."

Absent-means-on is an inference from `value !== 'false'`. I did not open the config-observation helper to confirm that a missing row yields `undefined`, but the tests above cover the behaviour.

The code also carries a TODO (`system.ts:302-303`): once support for servers ≤ v10.11 is dropped, these helpers and their callers can go, and archived channels can be treated as always viewable.