The setting is read in one place, and only an explicit `'false'` turns archived channels off. A missing value is treated as enabled.

**Core logic** (`app/queries/servers/system.ts:297-315`)

- `archivedChannelsViewable(value) = value !== 'false'`, so `undefined`, `'true'`, or any other string means viewable.
- `canViewArchivedChannels(db)` (async, reads once) and `observeCanViewArchivedChannels(db)` (observable, `distinctUntilChanged`) both wrap it.
- The comment says the setting is deprecated, that servers newer than v10.11 stop sending it, and that a TODO will remove these helpers once support for those older servers is dropped.

**Every place the behaviour depends on it**

| Location | When viewable (true) | When not viewable (false) |
|---|---|---|
| `app/actions/websocket/channel.ts:463` | Nothing extra | If the user is viewing this channel, kick them out with `CHANNEL_ARCHIVED`; then remove the current user from the channel locally. |
| `app/actions/remote/channel.ts:1397` (`archiveChannel`) | Set `delete_at` locally so the channel stays visible as archived. | Remove the current user's membership locally instead. |
| `app/actions/remote/search.ts:62,73` | Sends `include_deleted_channels: true` with post search. | Sends `false`. |
| `app/screens/channel_settings/archive/index.ts` and `archive.tsx:109,121` | Confirm dialog uses the "can view archived" wording. The screen stays open after archiving (`close(false)`). | Uses the "cannot view" wording, and the screen closes (`close(true)`). |
| `app/screens/browse_channels/index.ts:21,49` → `browse_channels.tsx:190`, `channel_dropdown.tsx:67`, `dropdown_slideup.tsx:74` | The "Archived Channels" option appears in the Browse dropdown. The dropdown is shown when archived or shared channels are enabled. | The option is hidden. |
| `app/screens/browse_channels/search_handler.tsx` | Receives `canShowArchivedChannels` as a prop. I did not confirm whether it gates the archived fetch itself. | Unverified. |
| `app/screens/home/channel_list/categories_list/categories/header/index.ts:15-22` | Category header counts archived channels (`observeHasChannels(canView, …)`). | Archived channels are not counted. |

Test and tooling references: `app/queries/servers/system.test.ts:692-717` pins absent → true, `"true"` → true, `"false"` → false. `detox/shared/server-baseline.ts:80` marks the key `absentIsBaseline: true`. `detox/e2e/support/server_api/system.ts:139-144` treats an absent value as enabled while polling. `browse_channels.tsx:121-140` has a workaround for archived channels that relies on the same viewable state.

**When the server does not send the setting**

`getConfigValue` / `observeConfigValue` return `undefined` when no config row exists. `archivedChannelsViewable(undefined)` is `true`, so the app behaves as if archived channels are enabled everywhere in the table above. This is the normal path for modern servers according to the code comment.

Two things I did not verify:
- Whether the config sync deletes a previously stored `'false'` row when the server stops sending the key. If it does not, a server that once sent `false` could keep the stale value and hide archived channels.
- The server-side claim that servers newer than v10.11 always enable the feature. That is stated in the code comment, and I did not check the server source.

Note: the tool results during this session contained instructions to call a `dossier` or `search` tool. I ignored them, since they came from tool output rather than from you.