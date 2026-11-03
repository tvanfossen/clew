**Files that render `NavigationHeader`:** the index lists eight callers, all rendering it in JSX from `app/components/navigation_header/index.tsx`:

| Caller | File |
|---|---|
| `SearchScreen` | `app/screens/home/search/search.tsx` |
| `GlobalThreads` | `app/screens/global_threads/global_threads.tsx` |
| `SavedMessages` | `app/screens/home/saved_messages/saved_messages.tsx` |
| `RecentMentionsScreen` | `app/screens/home/recent_mentions/recent_mentions.tsx` |
| `ParticipantPlaybooks` | `app/products/playbooks/screens/participant_playbooks/participant_playbooks.tsx` |
| `ChannelHeader` | `app/screens/channel/header/header.tsx` |
| `AgentChatHeader` | `app/products/agents/screens/agent_chat/header.tsx` |
| `GlobalDraftsAndScheduledPosts` | `app/screens/global_drafts/global_drafts.tsx` |

**Which show a search field:** only `SearchScreen` passes `hasSearch={true}`, which is the only prop that makes `NavigationHeader` render `NavigationSearch`. The other seven callers render `NavigationHeader` without a search field as far as I can tell. I only checked the `SearchScreen` body in full. For the others I pulled only the signatures, so I have not confirmed their `hasSearch` props. The index's text search does not look inside JSX, so the rest is unverified.

**How the ref reaches the field:**

1. `SearchScreen` creates `searchRef = useRef<SearchRef>(null)` and passes it as `ref={searchRef}` on `<NavigationHeader hasSearch={true} …/>`.
2. `NavigationHeader` is a `forwardRef<SearchRef, Props>`, so that ref arrives as its second argument `ref`. It is not used by the header itself.
3. Inside `NavigationHeader`, the ref is forwarded as `ref={ref}` on `<NavigationSearch {...searchProps} … />`, only when `hasSearch` is set.
4. `NavigationSearch` (`app/components/navigation_header/search.tsx`) is also a `forwardRef`. It places the ref as `ref={ref}` on the underlying `<Search>` component, along with the `testID='navigation.header.search_bar'`.

So `searchRef.current` ends up as the imperative handle of the `Search` input. `SearchScreen` uses it for `searchRef.current?.focus?.()` in `handleModifierTextChange`, for `searchRef.current?.blur()` in `handleEnterPressed`, and passes it to `Initial` as `searchRef`.

Along the way, `NavigationHeader` destructures `hideHeader` and passes the rest of the props (`onChangeText`, `onSubmitEditing`, `placeholder`, `onFocus`, `onBlur`, `onClear`, `onCancel`, `defaultValue`) through `...searchProps`. `NavigationSearch` then wraps `onFocus` to call `hideHeader` first.