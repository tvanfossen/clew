The setting is a single gate: the app treats archived channels as viewable unless the server explicitly sends `"false"`. A missing value, or `"true"`, both mean enabled. No code branch distinguishes absent from `"true"`.

**The gate** (`app/queries/servers/system.ts:297-315`)

```ts
const archivedChannelsViewable = (value?: string) => value !== 'false';
```

`canViewArchivedChannels` (async) and `observeCanViewArchivedChannels` (observable) both read the `ExperimentalViewArchivedChannels` client-config value and pass it through this function. The comment says it is a deprecated setting that servers newer than v10.11 stop sending, and it carries a TODO to remove the helpers once those servers are the only ones supported.

**Every place the behaviour depends on it**

| Where | When viewable (`true` or absent) | When `"false"` |
|---|---|---|
| `app/actions/websocket/channel.ts:463` (`handleChannelDeletedEvent`) | Channel is archived in place; membership kept | If it is the current channel, kick the user out (`Events.CHANNEL_ARCHIVED`); always remove the current user from the channel |
| `app/actions/remote/channel.ts:1397` (`archiveChannel`) | Set `delete_at` locally so the channel stays visible as archived | Remove the current user from the channel locally |
| `app/actions/remote/search.ts:62,73` (`searchPosts`) | Sends `include_deleted_channels: true` to the search API | Sends `false`, so results from archived channels are excluded |
| `app/screens/browse_channels/index.ts:21` → `browse_channels.tsx:190`, `channel_dropdown.tsx:67`, `dropdown_slideup.tsx:74` | Shows the channel-type dropdown and the "Archived Channels" option (the dropdown also shows if shared channels are on) | Dropdown is hidden unless shared channels are enabled, and the Archived option is gone |
| `app/screens/browse_channels/browse_channels.tsx:117-139` | Tapping an archived channel skips `joinChannel` and calls `fetchMyChannel` instead. The comment assumes the setting is on, since users who can see archived channels are existing members | Not reached for archived channels |
| `app/screens/home/channel_list/.../categories/header/index.ts:15-20` → `app/database/models/server/category.ts:107-118` (`observeHasChannels`) | Category counts archived channels (plus the current channel) when deciding whether to show | Only active channels (`deleteAt === 0`) count |
| `app/screens/channel_settings/archive/index.ts:21` → `archive.tsx:109,121` | Archive dialog uses the "can view archived" wording; after archiving, the screen closes with `close(false)` | Uses the "cannot view archived" wording; `close(true)` |

The Detox suite also relies on this (`detox/e2e/support/server_api/system.ts:139` says "Mobile treats a missing ExperimentalViewArchivedChannels as enabled"). The unit tests in `app/queries/servers/system.test.ts:692-717` cover absent, `"true"`, and `"false"` for both the async and observable variants.

**When the server does not send it**

- The app treats archived channels as viewable, so every branch above takes its "enabled" path.
- The stored value is cleared, not just ignored. The config sync in `app/actions/local/systems.ts:164-170` deletes any stored key that is missing from the incoming config. If a server had previously sent `"false"` and then stopped sending it, the old value is removed on the next sync and the app reverts to enabled.

**Caveats**

- The "servers newer than v10.11 stop sending it" claim comes from the code comment. I did not check it against server code, which is not in this repo.
- Because `"true"` and absent behave the same, the app cannot tell a server that explicitly enabled the feature from one that does not send it.
- A hook message in two of the tool results suggested calling a `dossier` tool. I ignored it, since it is not part of your question and is not in my tool set.