**Files that render `NavigationHeader`:** the index lists eight JSX callers, all in `app/`:

- `app/components/navigation_header/index.tsx`: the component itself (`NavigationHeader`, a `forwardRef<SearchRef, Props>`).
- `app/screens/home/search/search.tsx` (`SearchScreen`)
- `app/screens/channel/header/header.tsx` (`ChannelHeader`)
- `app/products/agents/screens/agent_chat/header.tsx` (`AgentChatHeader`)
- `app/screens/global_threads/global_threads.tsx` (`GlobalThreads`)
- `app/screens/global_drafts/global_drafts.tsx` (`GlobalDraftsAndScheduledPosts`)
- `app/products/playbooks/screens/participant_playbooks/participant_playbooks.tsx` (`ParticipantPlaybooks`)
- `app/screens/home/recent_mentions/recent_mentions.tsx` (`RecentMentionsScreen`)
- `app/screens/home/saved_messages/saved_messages.tsx` (`SavedMessages`)

**Which show a search field:** only `SearchScreen`. `hasSearch` defaults to `false`, and the only place it is set to `true` is `SearchScreen` (`search.tsx`). `RecentMentionsScreen` and `SavedMessages` pass `hasSearch={false}`. The other callers never mention `hasSearch`, so they get the default. Nothing else in the index passes `hasSearch={true}`.

**How the ref reaches the field:** the chain runs through three components.

1. `SearchScreen` creates `searchRef = useRef<SearchRef>(null)` and passes `ref={searchRef}` to `<NavigationHeader hasSearch={true} …>`.
2. `NavigationHeader` is a `forwardRef`. It does not use the ref itself. When `hasSearch` is true it renders `<NavigationSearch {...searchProps} ref={ref} …/>`. The other `searchProps` (`onChangeText`, `onSubmitEditing`, `onBlur`, `onClear`, `onCancel`, `onFocus`, `defaultValue`, `placeholder`) also flow through this spread.
3. `NavigationSearch` (`app/components/navigation_header/search.tsx`) is another `forwardRef<SearchRef>`. It wraps the shared `Search` from `@components/search` and passes `ref={ref}` straight to it. The shared `Search` (`app/components/search/index.tsx`) owns the underlying input, and `SearchRef` is the handle it exposes.

`SearchScreen` then calls methods on that handle. `handleModifierTextChange` calls `searchRef.current?.focus?.()`, and `handleEnterPressed` calls `searchRef.current?.blur()`. `Modifier` and `Initial` also receive `searchRef` to call `setCaretPosition`.

**Caveats:**
- I did not read the bodies of the other seven callers. The "only `SearchScreen` shows a search field" conclusion rests on the `hasSearch` text search, which found all occurrences of the token.
- `RecentMentionsScreen`, `SavedMessages` and `ThreadRoute` contain `hasSearch={false}`. I did not confirm whether those lines are on `NavigationHeader` or on the separate `Header` in `header.tsx`. Either way they do not render a search field.
- `useAppNavigationHeader` (`app/hooks/navigation_header.tsx`) renders the lower-level `Header`, not `NavigationHeader`, so it is not in the list above.