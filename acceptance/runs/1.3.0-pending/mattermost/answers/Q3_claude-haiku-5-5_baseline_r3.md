Eight files render `NavigationHeader` from `@components/navigation_header`. Only one of them shows a search field: `app/screens/home/search/search.tsx`.

**Files that render `NavigationHeader`**

| File | Line | `hasSearch` |
|---|---|---|
| `app/screens/home/search/search.tsx` | 463 | `true` |
| `app/screens/home/saved_messages/saved_messages.tsx` | 213 | `false` |
| `app/screens/home/recent_mentions/recent_mentions.tsx` | 176 | `false` |
| `app/screens/global_drafts/global_drafts.tsx` | 98 | not set (defaults to `false`) |
| `app/screens/global_threads/global_threads.tsx` | 127 | not set (defaults to `false`) |
| `app/screens/channel/header/header.tsx` | 337 | not set (defaults to `false`) |
| `app/products/agents/screens/agent_chat/header.tsx` | 75 | not set (defaults to `false`) |
| `app/products/playbooks/screens/participant_playbooks/participant_playbooks.tsx` | 132 | not set (defaults to `false`) |

The definition is `app/components/navigation_header/index.tsx`. `app/hooks/navigation_header.tsx` and `app/routes/(authenticated)/thread.tsx` import the lower-level `Header` from `navigation_header/header`, not `NavigationHeader`, so they are not in this list.

**How the ref reaches the search field**

1. `search.tsx` creates `searchRef = useRef<SearchRef>(null)` (line 122) and passes it as `ref={searchRef}` to `NavigationHeader` (line 480).
2. `NavigationHeader` (`navigation_header/index.tsx`, line 53) is a `forwardRef<SearchRef, Props>`. When `hasSearch` is true it renders `<NavigationSearch ... ref={ref}>` (line 134).
3. `NavigationSearch` (`navigation_header/search.tsx`, line 34) is also a `forwardRef`. It wraps the shared `Search` component and passes `ref={ref}` through (line 89), along with styling and the `hideHeader` focus behaviour.
4. `Search` (`app/components/search/index.tsx`, line 92) is a `forwardRef` that calls `useImperativeHandle(ref, ...)` (line 178). The exposed object is not the `TextInput`. It has `focus`, `blur`, `clear`, `cancel` and `setCaretPosition`, and each one delegates to an internal `searchRef` attached to the underlying `SearchBar` input (line 222).

So `search.tsx` calls methods on the handle, such as `searchRef.current?.focus()` (line 209) and `searchRef.current?.blur()` (line 447), and those land on the native input. The ref only does anything when `hasSearch` is true. With `hasSearch` false, the search branch isn't rendered and the ref is never attached.