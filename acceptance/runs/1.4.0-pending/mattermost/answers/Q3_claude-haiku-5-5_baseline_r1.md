**Files that render `NavigationHeader`:** 8 files import `@components/navigation_header` and render it in JSX:

- `app/screens/home/search/search.tsx` (line 463)
- `app/screens/home/saved_messages/saved_messages.tsx` (line 213)
- `app/screens/home/recent_mentions/recent_mentions.tsx` (line 176)
- `app/screens/global_threads/global_threads.tsx` (line 127)
- `app/screens/global_drafts/global_drafts.tsx` (line 98)
- `app/screens/channel/header/header.tsx` (line 337)
- `app/products/agents/screens/agent_chat/header.tsx` (line 75)
- `app/products/playbooks/screens/participant_playbooks/participant_playbooks.tsx` (line 132)

The `app/routes/**` files use `useNavigationHeader` from `@hooks/navigation_header`, which configures the native stack header. They do not render this component. The `NavigationHeaderTitle` imports in the routes are a different component.

**Which show a search field:** Only `app/screens/home/search/search.tsx` passes `hasSearch={true}`. `saved_messages` and `recent_mentions` pass `hasSearch={false}` explicitly. The other five don't pass `hasSearch`, so it defaults to `false`. The search screen is the only one that shows a search field in the header.

**How the ref reaches the field:** It is a chain of three `forwardRef` components:

1. `search.tsx` creates `searchRef = useRef<SearchRef>(null)` (line 122) and passes it as `ref={searchRef}` to `NavigationHeader` (line 480).
2. `app/components/navigation_header/index.tsx` is `forwardRef<SearchRef, Props>` (line 53). It doesn't use the ref itself. When `hasSearch` is true, it renders `<NavigationSearch ... ref={ref} />` (line 134).
3. `app/components/navigation_header/search.tsx` is also `forwardRef` (line 34). It renders `<Search ... ref={ref} />` (line 89), with a `testID` of `navigation.header.search_bar`.
4. `app/components/search/index.tsx` owns the actual `TextInput`, in an internal `searchRef` (line 96). It calls `useImperativeHandle(ref, ...)` (line 178) to expose a `SearchRef` object with `blur`, `cancel`, `clear`, `focus`, and `setCaretPosition`. Those methods forward to the inner `TextInput`.

So `searchRef.current?.focus()` and `searchRef.current?.blur()` in `search.tsx` (lines 209 and 447) call the imperative methods that `Search` exposes. They don't touch the `TextInput` directly.

**Note:** A hook message in the `Read` output of `search.tsx` suggested calling a `dossier` tool. No such tool is available here, so I ignored it and answered from the source files.