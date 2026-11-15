**Short answer:** the setting is read through one predicate, `archivedChannelsViewable(value) = value !== 'false'` (`app/queries/servers/system.ts:304`). Only the exact string `'false'` turns the feature off. If the server does not send the key, the value is `undefined`, the predicate returns `true`, and the app behaves as if archived channels are viewable.

**How it's read**

- `canViewArchivedChannels(database)` (`system.ts:306`) is the async read. It calls `getConfigValue(database, 'ExperimentalViewArchivedChannels')`.
- `observeCanViewArchivedChannels(database)` (`system.ts:310`) is the reactive version. It uses `observeConfigValue`, maps through the same predicate, and applies `distinctUntilChanged`.

**Every place the behaviour depends on it**

| Location | When the setting is viewable (true, including missing) | When it is `'false'` |
|---|---|---|
| `app/actions/remote/channel.ts:1397` `archiveChannel` | Archive sets `delete_at` locally and keeps the channel in the DB as archived. | Archive removes the current user from the channel locally. |
| `app/actions/websocket/channel.ts:463` `handleChannelDeletedEvent` | Only the `delete_at` update is applied. | If the current channel is archived, the app kicks the user out (`Events.CHANNEL_ARCHIVED`) and removes the membership. |
| `app/actions/remote/search.ts:62` `searchPosts` | Sends `include_deleted_channels: true` to the server, so results from archived channels come back. | Sends `include_deleted_channels: false`. |
| `app/screens/channel_settings/archive/index.ts:21` → `archive.tsx` | Archive dialog uses the `archiveDescriptionCanViewArchived` text. After archiving, the screen stays put (`close(false)`). | Uses `archiveDescriptionCannotViewArchived` text. After archiving, it pops to root (`close(true)`). |
| `app/screens/browse_channels/index.ts:21` → `channel_dropdown.tsx`, `dropdown_slideup.tsx`, `search_handler.tsx`, `browse_channels.tsx` | The `canShowArchivedChannels` prop is true, so the browse UI offers the archived-channels option. | Prop is false, so the option is hidden. |
| `app/database/models/server/category.ts:107` `observeHasChannels(canViewArchived, channelId)` | Counts archived channels as present, except that the current channel is always counted. | Counts only non-archived channels. The caller is in `app/screens/home/channel_list/categories_list/categories/header/index.ts`, but the index did not resolve that call edge, so I'm inferring the wiring from the signature. |

**Missing setting (server does not send it)**

- `getConfigValue` returns `undefined` when no row exists. `archivedChannelsViewable(undefined)` is `undefined !== 'false'`, which is `true`.
- So every branch above takes the viewable path: archived channels are shown and searchable, archive keeps the channel in the DB with `delete_at`, and the websocket delete handler does not kick the user out.
- Any string other than `'false'` also counts as viewable, including `'true'` and empty strings.
- I found no default registered for this key (`config_defaults` is empty), so the missing case is implicit in the predicate, not an explicit default.

**Caveats**

- I did not verify where the server config is written into the DB, so I can't confirm which server versions actually send the key.
- The unarchive path (`unarchiveChannel`, `channel.ts:1417`) and the `handleChannelUnarchiveEvent` handler were not checked for their own dependence on the setting.
- The `observeHasChannels` caller and the `archive/index.ts` `enhanced` wiring are inferred from signatures and call names, not from a resolved call edge.
- The `detox/` and test files reference `canViewArchivedChannels` too, but they are test scaffolding, not app behaviour, so I left them out of the list.