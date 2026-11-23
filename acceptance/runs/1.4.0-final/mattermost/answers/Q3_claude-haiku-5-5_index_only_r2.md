**Files that render `NavigationHeader`** (from the index's caller list for `NavigationHeader`):

| File | Component | Search field? |
|---|---|---|
| `app/screens/home/search/search.tsx` | `SearchScreen` | Yes, `hasSearch={true}` |
| `app/screens/channel/header/header.tsx` | `ChannelHeader` | No |
| `app/products/agents/screens/agent_chat/header.tsx` | `AgentChatHeader` | No |
| `app/screens/global_drafts/global_drafts.tsx` | `GlobalDraftsAndScheduledPosts` | No |
| `app/screens/global_threads/global_threads.tsx` | `GlobalThreads` | No |
| `app/products/playbooks/screens/participant_playbooks/participant_playbooks.tsx` | `ParticipantPlaybooks` | No |
| `app/screens/home/recent_mentions/recent_mentions.tsx` | `RecentMentionsScreen` | No (`hasSearch={false}`) |
| `app/screens/home/saved_messages/saved_messages.tsx` | `SavedMessages` | No (`hasSearch={false}`) |

Only `SearchScreen` shows a search field. `hasSearch` defaults to `false` in `NavigationHeader`, and the search input is only mounted when it is true. `app/routes/(authenticated)/thread.tsx` also passes `hasSearch={false}`, but it uses the lower-level `Header` directly, not `NavigationHeader`.

**How the ref reaches the field**

`SearchScreen` creates `searchRef = useRef<SearchRef>(null)` and passes it as `ref={searchRef}` on `<NavigationHeader>`. The chain from there:

```
SearchScreen         useRef<SearchRef>  ──ref──▶  <NavigationHeader>        (forwardRef<SearchRef>)
  NavigationHeader   forwards `ref` and the rest of its props (...searchProps)
    └─ <NavigationSearch ref={ref} {...searchProps} hideHeader theme topStyle>   (forwardRef<SearchRef>)
         └─ <Search ref={ref} testID='navigation.header.search_bar' ...>         (components/search/index.tsx, forwardRef)
              useImperativeHandle(ref, …)  → exposes SearchRef (focus/blur/setCaretPosition)
```

- `NavigationHeader` (`app/components/navigation_header/index.tsx`) does not use the ref itself. It forwards it to `NavigationSearch` only when `hasSearch` is true.
- `NavigationHeader` takes its own layout props (`scrollValue`, `lockValue`, `hideHeader`) and spreads everything else into `NavigationSearch`. That is how `onChangeText`, `onFocus`, `onBlur`, `onClear`, `onCancel`, `onSubmitEditing` and `placeholder` reach the input.
- `NavigationSearch` (`app/components/navigation_header/search.tsx`) wraps the field in an animated view and adds Android tab-bar show/hide on keyboard events.

`SearchScreen` then uses `searchRef.current` in three places:
- `handleModifierTextChange` calls `.focus()`.
- `handleEnterPressed` calls `.blur()`.
- It passes `searchRef` down to `Initial` → `Modifiers` → `Modifier`, which calls `setCaretPosition`.

I did not read the body of `useImperativeHandle` in `components/search/index.tsx`. The list of methods the ref exposes comes from the `SearchRef` type and from how the callers use it.