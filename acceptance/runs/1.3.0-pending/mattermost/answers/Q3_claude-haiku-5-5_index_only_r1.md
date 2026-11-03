**Files that render `NavigationHeader`** (8, from the index's caller list):

| File | Component | Passes `hasSearch`? |
|---|---|---|
| `app/screens/home/search/search.tsx` | `SearchScreen` | `hasSearch={true}` |
| `app/screens/home/saved_messages/saved_messages.tsx` | `SavedMessages` | `hasSearch={false}` |
| `app/screens/home/recent_mentions/recent_mentions.tsx` | `RecentMentionsScreen` | `hasSearch={false}` |
| `app/screens/channel/header/header.tsx` | `ChannelHeader` | not passed (default `false`) |
| `app/screens/global_threads/global_threads.tsx` | `GlobalThreads` | not passed |
| `app/screens/global_drafts/global_drafts.tsx` | `GlobalDraftsAndScheduledPosts` | not passed |
| `app/products/agents/screens/agent_chat/header.tsx` | `AgentChatHeader` | not passed |
| `app/products/playbooks/screens/participant_playbooks/participant_playbooks.tsx` | `ParticipantPlaybooks` | not passed (tablet branch only) |

Only `SearchScreen` shows a search field.

**How the ref reaches the field**

`NavigationHeader` is `forwardRef<SearchRef, Props>` (`app/components/navigation_header/index.tsx:53`). The ref flows through three layers:

```
SearchScreen                       search.tsx
  searchRef = useRef<SearchRef>()
  <NavigationHeader ref={searchRef} hasSearch ...>
        │
        ▼
NavigationHeader (forwardRef)      index.tsx
  {hasSearch && <NavigationSearch {...searchProps} hideHeader theme topStyle ref={ref} />}
        │
        ▼
NavigationSearch (forwardRef)      search.tsx (navigation_header)
  <Search {...searchProps} onFocus=... cancelButtonProps=... ref={ref} testID='navigation.header.search_bar' />
```

- `NavigationHeader` takes the ref as its second argument and forwards it to `NavigationSearch` only when `hasSearch` is true. Without `hasSearch`, the ref is attached to nothing.
- Everything else for the field arrives through `...searchProps`, the rest-spread that `NavigationHeader` does not consume: `onChangeText`, `onSubmitEditing`, `onBlur`, `onFocus`, `onClear`, `onCancel`, `placeholder`, `defaultValue`, `blurOnSubmit`.
- `hideHeader` is destructured in `NavigationHeader` and passed explicitly, so `NavigationSearch` can call it on focus.
- `NavigationSearch` also wraps `onFocus` and adds the Android tab-bar show/hide emitters on keyboard events.

`SearchScreen` uses the ref for imperative control: `searchRef.current?.focus?.()` and `.blur()` in `handleModifierTextChange` and `handleEnterPressed`. It also passes `searchRef` to the `Initial` recent-searches component.

**Limits of this answer**

- The index does not resolve the innermost `Search` component's definition, so I could not confirm what `SearchRef` exposes beyond `focus` and `blur`.
- The index lists `SavedMessages` in two files (`app/screens/home/saved_messages/saved_messages.tsx` and `app/screens/pinned_messages/pinned_messages.tsx`). The caller edge points to the home version, and I did not check whether the pinned-messages one also renders `NavigationHeader`.