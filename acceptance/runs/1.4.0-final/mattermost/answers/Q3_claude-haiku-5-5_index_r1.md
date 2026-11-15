**Files that render `NavigationHeader`** (all import it from `@components/navigation_header`):

| File:line | Component | `hasSearch` |
|---|---|---|
| `app/screens/channel/header/header.tsx:337` | `ChannelHeader` | unset (false) |
| `app/products/agents/screens/agent_chat/header.tsx:75` | `AgentChatHeader` | unset (false) |
| `app/screens/global_drafts/global_drafts.tsx:98` | `GlobalDraftsAndScheduledPosts` | unset (false) |
| `app/screens/global_threads/global_threads.tsx:127` | `GlobalThreads` | unset (false) |
| `app/products/playbooks/screens/participant_playbooks/participant_playbooks.tsx:132` | `ParticipantPlaybooks` | unset (false) |
| `app/screens/home/recent_mentions/recent_mentions.tsx:176` | `RecentMentionsScreen` | `false` |
| `app/screens/home/saved_messages/saved_messages.tsx:213` | `SavedMessages` | `false` |
| `app/screens/home/search/search.tsx:463` | `SearchScreen` | `true` |

Only `app/screens/home/search/search.tsx` shows a search field. `app/hooks/navigation_header.tsx` also renders a header, but it uses the lower-level `Header` from `header.tsx`, not `NavigationHeader`, so it is not in the list.

**How the ref reaches the field:**

1. `search.tsx:122` creates `searchRef = useRef<SearchRef>(null)`, and `search.tsx:480` passes it as `ref={searchRef}` to `<NavigationHeader>`.
2. `NavigationHeader` (`app/components/navigation_header/index.tsx:53`) is a `forwardRef<SearchRef, Props>`. It does not use the ref itself. When `hasSearch` is true, it renders `<NavigationSearch {...searchProps} ref={ref} />` (around lines 128–137). `searchProps` carries the remaining props such as `onChangeText`, `placeholder`, `onFocus` and `defaultValue`.
3. `NavigationSearch` (`app/components/navigation_header/search.tsx:34`) is also a `forwardRef`. It forwards the ref to `<Search ref={ref} />` at line 89, and it wraps `onFocus` to call `hideHeader`.
4. `Search` (`app/components/search/index.tsx:92`) calls `useImperativeHandle(ref, …)` at line 178. The handle exposes `blur`, `cancel`, `clear`, `focus` and `setCaretPosition`, all delegating to its own internal ref on the `TextInput` (line 222).

So `search.tsx` never receives the `TextInput`. It receives the `SearchRef` handle, and it uses that handle to call `focus()` (line 209) and `blur()` (line 447).

**Caveat:** the ref is attached only inside the `hasSearch &&` branch. For the other seven callers it is never attached, so a ref passed to them would be silently ignored.