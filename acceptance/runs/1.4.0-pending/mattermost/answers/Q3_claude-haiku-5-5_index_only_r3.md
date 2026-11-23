**Files that render `NavigationHeader`**

The index lists eight callers. Each is a screen or header component that renders the JSX element:

| File | Component | `hasSearch` |
|---|---|---|
| `app/screens/home/search/search.tsx` | `SearchScreen` | `true` |
| `app/screens/home/recent_mentions/recent_mentions.tsx` | `RecentMentionsScreen` | `false` |
| `app/screens/home/saved_messages/saved_messages.tsx` | `SavedMessages` | `false` |
| `app/screens/channel/header/header.tsx` | `ChannelHeader` | not passed (default `false`) |
| `app/screens/global_threads/global_threads.tsx` | `GlobalThreads` | not passed |
| `app/screens/global_drafts/global_drafts.tsx` | `GlobalDraftsAndScheduledPosts` | not passed |
| `app/products/agents/screens/agent_chat/header.tsx` | `AgentChatHeader` | not passed |
| `app/products/playbooks/screens/participant_playbooks/participant_playbooks.tsx` | `ParticipantPlaybooks` | not passed (rendered only when `isTabletView`) |

A search for the token `hasSearch` returns only these: `true` in `SearchScreen`, and `false` in the recent-mentions and saved-messages screens. The `ChannelHeader` body was truncated before its JSX, so I confirmed its omission from the token search rather than from the body.

**Only `SearchScreen` shows a search field.** `NavigationHeader` defaults `hasSearch` to `false`, and only the `hasSearch && <NavigationSearch …/>` branch in `app/components/navigation_header/index.tsx` renders an input.

**How the ref reaches the field**

1. `SearchScreen` creates `const searchRef = useRef<SearchRef>(null)` in `app/screens/home/search/search.tsx`, then passes `ref={searchRef}` to `<NavigationHeader hasSearch={true} …/>`.
2. `NavigationHeader` is a `forwardRef<SearchRef, Props>` (`index.tsx:53`). Its `ref` argument is not attached to its own view. It is forwarded to `<NavigationSearch … ref={ref} />`, but only inside the `hasSearch` branch.
3. `NavigationSearch` (`app/components/navigation_header/search.tsx:34`) is also a `forwardRef`. It forwards `ref` to the underlying `<Search>` component, which is the element that owns the text input.
4. `SearchScreen` then uses `searchRef.current` for `focus()` in `handleModifierTextChange` and for `blur()` in `handleEnterPressed`.

The chain is therefore `SearchScreen.searchRef` → `NavigationHeader` (forwardRef) → `NavigationSearch` (forwardRef) → `Search` input. The other props it receives (`onChangeText`, `onSubmitEditing`, `onFocus`, `onBlur`, `onClear`, `onCancel`, `placeholder`, `defaultValue`) travel through `...searchProps` the same way. `NavigationSearch` consumes `hideHeader` itself, calling it from its wrapped `onFocus`.

**Caveat:** if a caller passes a ref to `NavigationHeader` without `hasSearch`, the ref is never attached to anything. Only the `hasSearch` path gives the ref a target.