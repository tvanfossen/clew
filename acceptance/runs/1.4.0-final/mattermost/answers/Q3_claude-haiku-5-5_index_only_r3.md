**Files that render `NavigationHeader`** (from the index's caller list, `app/components/navigation_header/index.tsx`):

| File | Component | Search field? |
|---|---|---|
| `app/screens/home/search/search.tsx` | `SearchScreen` | **Yes**, `hasSearch={true}` |
| `app/screens/channel/header/header.tsx` | `ChannelHeader` | No |
| `app/products/agents/screens/agent_chat/header.tsx` | `AgentChatHeader` | No |
| `app/screens/global_drafts/global_drafts.tsx` | `GlobalDraftsAndScheduledPosts` | No |
| `app/screens/global_threads/global_threads.tsx` | `GlobalThreads` | No |
| `app/products/playbooks/screens/participant_playbooks/participant_playbooks.tsx` | `ParticipantPlaybooks` | No |
| `app/screens/home/recent_mentions/recent_mentions.tsx` | `RecentMentionsScreen` | No (`hasSearch={false}`) |
| `app/screens/home/saved_messages/saved_messages.tsx` | `SavedMessages` | No (`hasSearch={false}`) |

Only `SearchScreen` is a search screen. The other seven leave `hasSearch` at its default of `false`, so they render no search row.

**How the ref reaches the field** (`SearchScreen` is the only one that passes a ref):

1. `search.tsx` creates `searchRef = useRef<SearchRef>(null)` and passes `ref={searchRef}` to `<NavigationHeader hasSearch={true} …>`.
2. `NavigationHeader` is a `forwardRef`. It does not use the ref itself. When `hasSearch` is true it renders `<NavigationSearch {...searchProps} ref={ref} …/>`. When `hasSearch` is false, the ref is dropped.
3. `NavigationSearch` (`app/components/navigation_header/search.tsx`) is also a `forwardRef`. It spreads the search props, adds its own `onFocus` wrapper (which calls `hideHeader` and then the caller's `onFocus`), and renders `<Search {...searchProps} ref={ref} testID='navigation.header.search_bar' />`.
4. So `searchRef.current` ends up as the `Search` input's instance. `SearchScreen` uses it for `.focus()` (in `handleModifierTextChange`) and `.blur()` (in `handleEnterPressed`). It also passes `searchRef` as a prop to `Initial`, which is a second consumer of the same ref.

**Caveats:**
- I could not read the library `Search` component's definition, so I did not confirm its ref type. The chain above is verified up to that component.
- The index's caller list is complete for `NavigationHeader` (eight rows, no truncation note), but I inferred the `hasSearch` defaults for the seven non-search files from the absence of the prop and the `hasSearch={false}` hits.
- `useAppNavigationHeader` (`app/hooks/navigation_header.tsx`) also takes `hasSearch`, but it renders the lower-level `Header` component, not `NavigationHeader`, so it is not a render site for this question. The `ThreadRoute` hit in `app/routes/(authenticated)/thread.tsx` is a similar `hasSearch={false}` use, and I did not confirm which header component it renders.