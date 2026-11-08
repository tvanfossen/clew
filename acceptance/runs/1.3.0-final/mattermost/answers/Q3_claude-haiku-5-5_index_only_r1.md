**Files that render `NavigationHeader`** (eight, from the index's JSX call edges):

| File | Component | `hasSearch` |
|---|---|---|
| `app/screens/home/search/search.tsx` | `SearchScreen` | `true` |
| `app/screens/home/saved_messages/saved_messages.tsx` | `SavedMessages` | `false` |
| `app/screens/home/recent_mentions/recent_mentions.tsx` | `RecentMentionsScreen` | `false` |
| `app/screens/global_threads/global_threads.tsx` | `GlobalThreads` | not set (default `false`) |
| `app/screens/global_drafts/global_drafts.tsx` | `GlobalDraftsAndScheduledPosts` | not set |
| `app/screens/channel/header/header.tsx` | `ChannelHeader` | not set |
| `app/products/agents/screens/agent_chat/header.tsx` | `AgentChatHeader` | not set |
| `app/products/playbooks/screens/participant_playbooks/participant_playbooks.tsx` | `ParticipantPlaybooks` | not set |

The `hasSearch` grep found no other `true` value, so only `SearchScreen` shows a search field. The `ThreadRoute` hit in `app/routes/(authenticated)/thread.tsx` passes `hasSearch={false}` but is not a resolved caller of `NavigationHeader`; I did not check what it renders.

**How the ref reaches the field**

1. `SearchScreen` creates `const searchRef = useRef<SearchRef>(null)` and passes it as `ref={searchRef}` to `<NavigationHeader hasSearch={true} ...>`.
2. `NavigationHeader` is a `forwardRef<SearchRef, Props>` (`app/components/navigation_header/index.tsx:53`). It does not attach the ref to its own `Animated.View`. When `hasSearch` is true, it renders `<NavigationSearch {...searchProps} hideHeader theme topStyle ref={ref} />`. The `Header` and `NavigationHeaderLargeTitle` children do not receive the ref.
3. `NavigationSearch` (`app/components/navigation_header/search.tsx:34`) is also a `forwardRef<SearchRef>`. It renders `<Search {...searchProps} ... ref={ref} testID='navigation.header.search_bar' />`, so the ref lands on the input component. I did not check the `Search` component itself, so the step from `Search` to the native `TextInput` is unverified.

The `searchProps` rest object carries `onChangeText`, `onSubmitEditing`, `onFocus`, `onBlur`, `onClear`, `onCancel`, `placeholder` and `defaultValue` from `SearchScreen` through to `Search`. `hideHeader` is destructured out in `NavigationHeader` and passed explicitly.

```
SearchScreen
  searchRef = useRef<SearchRef>
  │  ref={searchRef}
  ▼
NavigationHeader (forwardRef)         ── ref not attached to its own View
  │  hasSearch && <NavigationSearch ref={ref} {...searchProps}/>
  ▼
NavigationSearch (forwardRef)
  │  <Search ref={ref} testID='navigation.header.search_bar'/>
  ▼
Search input
```

`SearchScreen` also passes `searchRef` directly to `Initial`, and calls `searchRef.current?.focus?.()` and `.blur()` itself, so the same ref drives the input from outside the header.