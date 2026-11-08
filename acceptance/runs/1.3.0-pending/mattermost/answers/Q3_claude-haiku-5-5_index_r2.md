**Files that render `NavigationHeader`** (`app/components/navigation_header/index.tsx`, the component is defined at line 53):

| File | Line | `hasSearch` |
|---|---|---|
| `app/screens/home/search/search.tsx` | 463 | `true` |
| `app/screens/channel/header/header.tsx` | 337 | not passed (defaults to `false`) |
| `app/screens/home/saved_messages/saved_messages.tsx` | 213 | `false` |
| `app/screens/home/recent_mentions/recent_mentions.tsx` | 176 | `false` |
| `app/screens/global_drafts/global_drafts.tsx` | 98 | not passed |
| `app/screens/global_threads/global_threads.tsx` | 127 | not passed |
| `app/products/playbooks/screens/participant_playbooks/participant_playbooks.tsx` | 132 | not passed |
| `app/products/agents/screens/agent_chat/header.tsx` | 75 | not passed |

The index's caller list matches the grep for `<NavigationHeader`, so I found no extra call sites. `app/hooks/navigation_header.tsx` also builds a header, but it renders the inner `Header` from `components/navigation_header/header.tsx`, not `NavigationHeader`. The thread route in `app/routes/(authenticated)/thread.tsx` does the same.

**Only one screen shows a search field:** `search.tsx` is the only caller with `hasSearch={true}`. The `hasSearch` flag is what makes `NavigationHeader` render its search bar.

**How the ref reaches the field:**

1. `search.tsx` creates `searchRef = useRef<SearchRef>(null)` (line 122) and passes `ref={searchRef}` to `<NavigationHeader>` (line 480).
2. `NavigationHeader` is a `forwardRef<SearchRef, Props>`. When `hasSearch` is true, it renders `<NavigationSearch … ref={ref} />` (index.tsx, around line 128–137). It does not use the ref itself.
3. `NavigationSearch` (`app/components/navigation_header/search.tsx`) is also `forwardRef` and passes `ref={ref}` to `<Search>`, which wraps the search input.
4. `Search` (`app/components/search/index.tsx`) calls `useImperativeHandle(ref, …)` at line 178. The handle exposes `focus()` and `blur()`, which delegate to its internal input ref.

So `searchRef.current` in `search.tsx` is the `Search` imperative handle. `search.tsx` calls `searchRef.current?.focus?.()` (line 209) and `searchRef.current?.blur()` (line 447). Those calls go through `NavigationHeader` and `NavigationSearch` without either one touching the handle.