**Files that render `NavigationHeader`:** eight, per the index's resolved JSX call edges. The definition lives in `app/components/navigation_header/index.tsx`.

| File | Component | `hasSearch` |
|---|---|---|
| `app/screens/home/search/search.tsx` | `SearchScreen` | `true` |
| `app/screens/home/recent_mentions/recent_mentions.tsx` | `RecentMentionsScreen` | `false` |
| `app/screens/home/saved_messages/saved_messages.tsx` | `SavedMessages` | `false` |
| `app/screens/channel/header/header.tsx` | `ChannelHeader` | not set (default `false`) |
| `app/products/agents/screens/agent_chat/header.tsx` | `AgentChatHeader` | not set |
| `app/screens/global_drafts/global_drafts.tsx` | `GlobalDraftsAndScheduledPosts` | not set |
| `app/screens/global_threads/global_threads.tsx` | `GlobalThreads` | not set |
| `app/products/playbooks/screens/participant_playbooks/participant_playbooks.tsx` | `ParticipantPlaybooks` | not set (tablet only) |

**Which show a search field:** only `SearchScreen` (`search.tsx`) passes `hasSearch={true}`. The other seven either set `hasSearch={false}` or leave it unset, so `NavigationSearch` is never mounted for them.

**How the ref reaches the field:**

```
SearchScreen          searchRef = useRef<SearchRef>(null)
  └─ <NavigationHeader hasSearch ref={searchRef} .../>
       forwardRef<SearchRef>  → ref is the 2nd arg
       └─ {hasSearch && <NavigationSearch {...searchProps} ref={ref} .../>}
            forwardRef<SearchRef>  → ref is the 2nd arg
            └─ <Search {...searchProps} ref={ref} testID='navigation.header.search_bar'/>
```

1. `SearchScreen` creates `searchRef` and passes it as `ref` to `NavigationHeader`. React strips `ref` from props, so it arrives as the second argument of the `forwardRef` callback.
2. `NavigationHeader` forwards that ref unchanged to `NavigationSearch`, but only inside the `hasSearch &&` branch.
3. `NavigationSearch` forwards it again to the underlying `Search` input, the element with testID `navigation.header.search_bar`.
4. `SearchScreen` uses the ref imperatively: `searchRef.current?.focus?.()` in `handleModifierTextChange`, and `searchRef.current?.blur()` in `handleEnterPressed`. It also hands `searchRef` to the `Initial` view as a prop.

Everything else `SearchScreen` passes (`onChangeText`, `onSubmitEditing`, `onFocus`, `onBlur`, `onClear`, `onCancel`, `placeholder`, `defaultValue`) travels through the `...searchProps` rest spread in both wrappers. `NavigationHeader` also consumes `hideHeader` itself and wires it into `NavigationSearch`'s focus handler.

**Caveats:**
- If `hasSearch` is false, the ref is silently dropped because `NavigationSearch` is never rendered.
- The index does not show the type of `SearchRef` or the `Search` component's imperative methods. I inferred that `focus` and `blur` exist from the call sites, not from the definition.