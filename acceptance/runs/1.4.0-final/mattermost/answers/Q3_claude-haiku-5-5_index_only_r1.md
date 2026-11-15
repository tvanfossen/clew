**Files that render `NavigationHeader`** (from the index's caller list, which reported no unresolved callers):

| File | Component | Search field? |
|---|---|---|
| `app/products/agents/screens/agent_chat/header.tsx` | `AgentChatHeader` | No |
| `app/screens/channel/header/header.tsx` | `ChannelHeader` | No |
| `app/screens/global_drafts/global_drafts.tsx` | `GlobalDraftsAndScheduledPosts` | No |
| `app/screens/global_threads/global_threads.tsx` | `GlobalThreads` | No |
| `app/products/playbooks/screens/participant_playbooks/participant_playbooks.tsx` | `ParticipantPlaybooks` | No |
| `app/screens/home/recent_mentions/recent_mentions.tsx` | `RecentMentionsScreen` | No (`hasSearch={false}`) |
| `app/screens/home/saved_messages/saved_messages.tsx` | `SavedMessages` | No (`hasSearch={false}`) |
| `app/screens/home/search/search.tsx` | `SearchScreen` | **Yes** (`hasSearch={true}`) |

Only `SearchScreen` shows a search field. The other seven either omit `hasSearch` (it defaults to `false`) or pass it as `false`.

**How the ref reaches the field**

`NavigationHeader` is a `forwardRef<SearchRef, Props>` (`app/components/navigation_header/index.tsx:53`). The chain is:

1. **`SearchScreen`** (`app/screens/home/search/search.tsx`) creates `searchRef = useRef<SearchRef>(null)` and passes `ref={searchRef}` to `<NavigationHeader hasSearch={true} …/>`.
2. **`NavigationHeader`** does not use the ref itself. When `hasSearch` is true it renders `<NavigationSearch {...searchProps} hideHeader theme topStyle ref={ref} />`. The `Header` and `NavigationHeaderLargeTitle` children do not receive it.
3. **`NavigationSearch`** (`app/components/navigation_header/search.tsx:34`) is also a `forwardRef<SearchRef>`. It passes `ref={ref}` to the `Search` component.
4. **`Search`** (`app/components/search/index.tsx:92`) is a `forwardRef<SearchRef>`. `SearchRef` is `{blur, cancel, clear, focus, setCaretPosition}` (`app/components/search/index.tsx:47`).

`SearchScreen` then uses `searchRef.current` for imperative calls: `focus()` in `handleModifierTextChange`, `blur()` in `handleEnterPressed`, and it passes `searchRef` down to `Initial` for recent-search handling.

**Caveats**
- I did not confirm the final hop by reading the body of `Search`. Its `forwardRef<SearchRef>` type signature is in the index, but I did not find an explicit `useImperativeHandle` call in the indexed code.
- The `ref` is only attached when `hasSearch` is true. For the other seven callers it is never attached to anything.