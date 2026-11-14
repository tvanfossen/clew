**Files that render `NavigationHeader`**

Per the index, these render it (`app/components/navigation_header/index.tsx`):

- `app/products/agents/screens/agent_chat/header.tsx` (`AgentChatHeader`)
- `app/screens/channel/header/header.tsx` (`ChannelHeader`)
- `app/screens/global_drafts/global_drafts.tsx` (`GlobalDraftsAndScheduledPosts`)
- `app/screens/global_threads/global_threads.tsx` (`GlobalThreads`)
- `app/products/playbooks/screens/participant_playbooks/participant_playbooks.tsx` (`ParticipantPlaybooks`)
- `app/screens/home/recent_mentions/recent_mentions.tsx` (`RecentMentionsScreen`)
- `app/screens/home/saved_messages/saved_messages.tsx` (`SavedMessages`)
- `app/screens/home/search/search.tsx` (`SearchScreen`)

Caveat: the `SavedMessages` name is also a candidate in `app/screens/pinned_messages/pinned_messages.tsx`, and I did not confirm whether that file renders `NavigationHeader`. `app/routes/(authenticated)/thread.tsx` also passes `hasSearch={false}`, but it is not in the caller list, so I did not count it.

**Which show a search field**

Only `SearchScreen` does. It is the only site that passes `hasSearch={true}`; the other callers either pass `hasSearch={false}` or omit it. `NavigationHeader` defaults `hasSearch` to `false`, and the search field is mounted only when it is true.

**How the ref reaches the field**

1. `SearchScreen` creates `searchRef = useRef<SearchRef>(null)` and passes `ref={searchRef}` to `<NavigationHeader hasSearch={true} …>`. Its other search props (`onChangeText`, `onSubmitEditing`, `onFocus`, `onBlur`, `onClear`, `onCancel`, `placeholder`, `defaultValue`) travel the same route.
2. `NavigationHeader` is `forwardRef<SearchRef, Props>`. It does not use the ref itself. It spreads the rest of its props into `<NavigationSearch {...searchProps} ref={ref} />`, inside `{hasSearch && …}`.
3. `NavigationSearch` (`app/components/navigation_header/search.tsx`) is also `forwardRef`. It renders `<Search {...searchProps} ref={ref} />` with the navigation-header styling.
4. `Search` (`app/components/search/index.tsx`) is `forwardRef` and calls `useImperativeHandle` at about line 178. The ref is therefore not attached to the `TextInput` directly. It exposes the `SearchRef` API: `blur`, `cancel`, `clear`, `focus` and `setCaretPosition`.

`SearchScreen` then calls `searchRef.current?.focus()` and `.blur()`, and passes `searchRef` down to the recent-search and modifier components (`Initial` and `Modifiers`), which call `setCaretPosition`.

`Header` (`app/components/navigation_header/header.tsx`) receives no ref. It only uses `hasSearch` to hide the title while the search field is shown.