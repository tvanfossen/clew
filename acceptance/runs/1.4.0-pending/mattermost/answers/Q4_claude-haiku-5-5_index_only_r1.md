The setting is a single config flag, `ExperimentalViewArchivedChannels`, read through one predicate. The app's behaviour changes in six places, and when the server omits the key the app treats archived channels as viewable.

**The gate**

- `archivedChannelsViewable(value)` returns `value !== 'false'` (`app/queries/servers/system.ts:304`). Only the exact string `'false'` turns the feature off. Any other value, including a missing one, turns it on.
- `canViewArchivedChannels(database)` reads the value with `getConfigValue` and applies that predicate (`system.ts:306`).
- `observeCanViewArchivedChannels(database)` is the reactive version. It uses `observeConfigValue`, applies the same predicate, and adds `distinctUntilChanged` (`system.ts:310`).

**Where the behaviour depends on it**

1. **Archiving a channel** (`archiveChannel`, `app/actions/remote/channel.ts:1390`). After the server delete call, if the setting is on, the app stamps `delete_at` on the local channel so it stays visible as archived. If it is off, the app removes the current user from the channel locally.
2. **Receiving a channel-deleted websocket event** (`handleChannelDeletedEvent`, `app/actions/websocket/channel.ts:441`). If the setting is off, and the current channel is the one deleted, the app kicks the user out with `CHANNEL_ARCHIVED`. It then removes the user from the channel locally. If the setting is on, it only sets `delete_at`. The handler skips all of this when the channel is one the client is currently archiving or leaving.
3. **Post search** (`searchPosts`, `app/actions/remote/search.ts:58`). The value is sent to the server as `include_deleted_channels`. When on, search results can include posts from archived channels.
4. **Archive/unarchive menu item** (`app/screens/channel_settings/archive/archive.tsx`, fed by `archive/index.ts:21`). The confirmation text changes between the "can view archived" and "cannot view archived" variants. After a successful archive, the screen pops to root only when the setting is off (`close(!canViewArchivedChannels)`, line 121).
5. **Category header** (`app/screens/home/channel_list/categories_list/categories/header/index.ts:15`). It observes the flag and passes it into `CategoryModel.observeHasChannels(canViewArchived, channelId)`, declared in `types/database/models/servers/category.ts:61`. I did not read the body of that method, so I have not confirmed how the flag changes its result.
6. **Browse channels** (`app/screens/browse_channels/index.ts`). It observes the flag, and the Archived filter/dropdown lives in `browse_channels.tsx` and `dropdown_slideup.tsx`. I confirmed the observation, not how the UI gates the Archived option.

Other archived-channel code, such as `fetchArchivedChannels`, `filterArchivedChannels` and `removeChannelsFromArchivedTeams`, does not read this setting. The index shows no direct dependency for them.

**When the server does not send the setting**

`getConfigValue` and `observeConfigValue` return `undefined` when there is no stored row (`system.ts:170` and `:266`). `archivedChannelsViewable(undefined)` evaluates to `true`, so the app behaves as if the feature is enabled. Concretely:

- archiving keeps channels visible as archived, rather than removing the user;
- deletion events keep the channel and do not kick the user;
- search sends `include_deleted_channels: true`;
- the archive dialog uses the "can view archived" text and does not pop to root.

Only an explicit `'false'` from the server switches the feature off.