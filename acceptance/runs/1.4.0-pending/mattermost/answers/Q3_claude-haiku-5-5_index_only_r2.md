**Files that render `NavigationHeader`** (`app/components/navigation_header/index.tsx`, line 53)

The index lists eight direct JSX callers, all in the app (not tests):

| Caller | File | Passes `hasSearch`? |
|---|---|---|
| `SearchScreen` | `app/screens/home/search/search.tsx` | Yes, `true` |
| `ChannelHeader` | `app/screens/channel/header/header.tsx` | No (default `false`) |
| `AgentChatHeader` | `app/products/agents/screens/agent_chat/header.tsx` | No |
| `GlobalThreads` | `app/screens/global_threads/global_threads.tsx` | No |
| `GlobalDraftsAndScheduledPosts` | `app/screens/global_drafts/global_drafts.tsx` | No |
| `ParticipantPlaybooks` | `app/products/playbooks/screens/participant_playbooks/participant_playbooks.tsx` | No |
| `RecentMentionsScreen` | `app/screens/home/recent_mentions/recent_mentions.tsx` | `false` |
| `SavedMessages` | `app/screens/home/saved_messages/saved_messages.tsx` | `false` |

A code search for `hasSearch` found no mention in the other callers, so they get the default `false`.

**Which show a search field:** only `SearchScreen`. It is the only caller with `hasSearch={true}`. When that flag is set, `NavigationHeader` renders its `NavigationSearch` child (`app/components/navigation_header/search.tsx`), which wraps the `Search` input. The other seven callers render no search field.

**How the ref reaches the field:**

1. `SearchScreen` creates `searchRef = useRef<SearchRef>(null)` and passes `ref={searchRef}` to `<NavigationHeader>`.
2. `NavigationHeader` is a `forwardRef<SearchRef, Props>`. It does not use the ref itself. Only when `hasSearch` is true does it render `<NavigationSearch ... ref={ref} />`.
3. `NavigationSearch` is also a `forwardRef<SearchRef>`. It forwards the ref to the inner `<Search ... ref={ref} />` input.

So the chain is `SearchScreen.searchRef → NavigationHeader → NavigationSearch → Search input`. `SearchScreen` then calls `searchRef.current?.focus?.()` (in `handleModifierTextChange`) and `searchRef.current?.blur()` (in `handleEnterPressed`). The same ref is also passed to `Initial` as `searchRef`.

One consequence: a ref passed to `NavigationHeader` without `hasSearch` is silently dropped, because the `NavigationSearch` branch that consumes it never renders. I did not open the inner `Search` component, so I can't confirm the final hop beyond the forwarded `ref` prop.