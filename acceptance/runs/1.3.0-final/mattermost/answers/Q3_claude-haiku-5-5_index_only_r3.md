**Files that render `NavigationHeader`** (the index's JSX call-site edges, all resolved):

| File | Screen / component | Shows search field? |
|---|---|---|
| `app/screens/home/search/search.tsx` (`SearchScreen`) | Search tab | **Yes**: `hasSearch={true}` |
| `app/screens/home/recent_mentions/recent_mentions.tsx` (`RecentMentionsScreen`) | Recent mentions | No: `hasSearch={false}` |
| `app/screens/home/saved_messages/saved_messages.tsx` (`SavedMessages`) | Saved messages | No: `hasSearch={false}` |
| `app/screens/global_threads/global_threads.tsx` (`GlobalThreads`) | Threads | No: prop not set, so defaults to `false` |
| `app/screens/global_drafts/global_drafts.tsx` (`GlobalDraftsAndScheduledPosts`) | Drafts / scheduled posts | No: prop not set |
| `app/screens/channel/header/header.tsx` (`ChannelHeader`) | Channel header | No: prop not set |
| `app/products/agents/screens/agent_chat/header.tsx` (`AgentChatHeader`) | Agent chat header | No: prop not set |
| `app/products/playbooks/screens/participant_playbooks/participant_playbooks.tsx` (`ParticipantPlaybooks`) | Participant playbooks | No: prop not set |

Only `SearchScreen` renders a search field. The "not set" entries rely on the `hasSearch = false` default in `NavigationHeader`; I checked for `hasSearch` across the code and none of those files pass it. `app/routes/(authenticated)/thread.tsx` (`ThreadRoute`) also passes `hasSearch={false}`, but it is not a direct `NavigationHeader` caller in the index, so I did not count it.

**How the ref reaches the field:**

1. `SearchScreen` creates `searchRef = useRef<SearchRef>(null)` and passes `ref={searchRef}` to `<NavigationHeader hasSearch={true} …/>`.
2. `NavigationHeader` (`app/components/navigation_header/index.tsx`, lines 53–139) is a `forwardRef<SearchRef, Props>`. It does not use the ref itself. When `hasSearch` is true, it renders `<NavigationSearch {...searchProps} hideHeader theme topStyle ref={ref} />`. The `...searchProps` rest spread is how props like `onChangeText`, `onFocus`, `onClear`, `onCancel` and `placeholder` reach the search.
3. `NavigationSearch` (`app/components/navigation_header/search.tsx`, lines 34–94) is also a `forwardRef`. It forwards the ref to `<Search … ref={ref} testID='navigation.header.search_bar' />`.
4. `Search` (`app/components/search/index.tsx`, line 92) is the component that owns the `TextInput`. It holds an internal `searchRef = useRef<TextInput>` and calls `useImperativeHandle(ref, …)` to expose the `SearchRef` API: `blur`, `cancel`, `clear`, `focus` and `setCaretPosition`. Each method delegates to the internal `TextInput`.

So `SearchScreen` gets a `SearchRef` handle, not the `TextInput` itself. Its uses are `searchRef.current?.focus?.()` in `handleModifierTextChange`, `searchRef.current?.blur()` in `handleEnterPressed`, and passing `searchRef` into `Initial`. When `hasSearch` is false, `NavigationSearch` is not mounted, so the ref stays `null`.