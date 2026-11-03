**Files that render `NavigationHeader`** (`app/components/navigation_header/index.tsx`, the `NavigationHeader` forwardRef component):

| File | Uses `hasSearch` |
|---|---|
| `app/screens/home/search/search.tsx:463` | `true` (search field shown) |
| `app/screens/channel/header/header.tsx:337` | not set (default `false`) |
| `app/screens/global_drafts/global_drafts.tsx:98` | not set |
| `app/screens/global_threads/global_threads.tsx:127` | not set |
| `app/screens/home/recent_mentions/recent_mentions.tsx:176` | `false` |
| `app/screens/home/saved_messages/saved_messages.tsx:213` | `false` |
| `app/products/playbooks/screens/participant_playbooks/participant_playbooks.tsx:132` | not set |
| `app/products/agents/screens/agent_chat/header.tsx:75` | not set |

The index lists these eight call sites with no unresolved callers. Grep confirms no other `hasSearch` usage in those files, so only the Search screen shows a search field.

**How the ref reaches the field:**

1. `search.tsx` creates `searchRef = useRef<SearchRef>(null)` (line 122) and passes `ref={searchRef}` to `NavigationHeader` (line 480).
2. `NavigationHeader` is a `forwardRef<SearchRef, Props>`. When `hasSearch` is true, it renders `<NavigationSearch {...searchProps} ... ref={ref} />` (`navigation_header/index.tsx`, near the end of the component). The ref is forwarded as-is, and `searchProps` (placeholder, `onChangeText`, `onSubmitEditing`, `onFocus`, `onBlur`, `onClear`, `onCancel`, `defaultValue`, etc.) are spread through as well.
3. `NavigationSearch` (`app/components/navigation_header/search.tsx`) is another `forwardRef<SearchRef>`. It wraps the shared `Search` component in an animated container and passes `ref={ref}` through again.
4. `Search` (`app/components/search/index.tsx`) is the final forwardRef. It calls `useImperativeHandle(ref, …)` (line 178) to expose `focus()` and `blur()`, which delegate to its internal `TextInput` ref.

So `searchRef.current.focus()` / `.blur()` in `search.tsx` runs the `Search` component's imperative handle, which drives the actual input. The ref does not pass through `NavigationHeader`'s own logic; it is forwarded untouched at each level until it reaches `Search`.