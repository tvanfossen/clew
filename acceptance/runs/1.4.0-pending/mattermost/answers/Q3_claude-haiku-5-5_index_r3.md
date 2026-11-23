The `NavigationHeader` component is rendered by eight files, but only the Search screen shows a search field. The ref reaches that field through `forwardRef` in two hops.

**Files that render `NavigationHeader`** (defined in `app/components/navigation_header/index.tsx:53`):

| File | Component | Shows search? |
|---|---|---|
| `app/screens/home/search/search.tsx:463` | `SearchScreen` | Yes, `hasSearch={true}` |
| `app/screens/home/saved_messages/saved_messages.tsx:218` | `SavedMessages` | No, `hasSearch={false}` |
| `app/screens/home/recent_mentions/recent_mentions.tsx:181` | `RecentMentionsScreen` | No, `hasSearch={false}` |
| `app/screens/global_drafts/global_drafts.tsx` | `GlobalDraftsAndScheduledPosts` | No (no `hasSearch` passed) |
| `app/screens/global_threads/global_threads.tsx` | `GlobalThreads` | No (no `hasSearch` passed) |
| `app/screens/channel/header/header.tsx` | `ChannelHeader` | No (no `hasSearch` passed) |
| `app/products/playbooks/screens/participant_playbooks/participant_playbooks.tsx` | `ParticipantPlaybooks` | No (no `hasSearch` passed) |
| `app/products/agents/screens/agent_chat/header.tsx` | `AgentChatHeader` | No (no `hasSearch` passed) |

Only `SearchScreen` shows a search field. The other seven pass no `hasSearch` or pass `false`, so `NavigationHeader` never renders `NavigationSearch` for them.

**How the ref reaches the input:**

1. **Screen creates the ref.** `search.tsx:122` declares `const searchRef = useRef<SearchRef>(null)`, and `search.tsx:480` passes it as `ref={searchRef}` on `<NavigationHeader>`.
2. **`NavigationHeader` forwards it.** It is declared as `forwardRef<SearchRef, Props>`. When `hasSearch` is true, it renders `<NavigationSearch ... ref={ref} />` (`index.tsx`, the `hasSearch &&` block). If `hasSearch` is false, the ref is not attached to anything.
3. **`NavigationSearch` forwards it again.** `app/components/navigation_header/search.tsx:34` is another `forwardRef`. It passes `ref={ref}` to the base `<Search>` component (line 89), after adding its theming and focus and keyboard handling.
4. **The base `Search` exposes an imperative handle.** `app/components/search/index.tsx:178` calls `useImperativeHandle(ref, () => ({ blur, focus }))`. That handle is the `SearchRef` type (`index.tsx:47`).

The result is that `searchRef.current` in `search.tsx` is the `{blur, focus}` handle from the base `Search` component. `search.tsx:209` calls `searchRef.current?.focus?.()` and `search.tsx:447` calls `searchRef.current?.blur()`.

One consequence: because the ref is only attached inside the `hasSearch &&` branch, a caller that passes a ref without `hasSearch={true}` gets a ref that is never populated.