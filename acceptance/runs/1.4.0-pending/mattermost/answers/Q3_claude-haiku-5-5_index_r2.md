**Files that render `NavigationHeader`**

The component is defined in `app/components/navigation_header/index.tsx:53` as a `forwardRef<SearchRef, Props>`. Eight screens render it:

| File | Line |
|---|---|
| `app/screens/home/search/search.tsx` | 463 |
| `app/screens/home/saved_messages/saved_messages.tsx` | 213 |
| `app/screens/home/recent_mentions/recent_mentions.tsx` | 176 |
| `app/screens/global_drafts/global_drafts.tsx` | 98 |
| `app/screens/global_threads/global_threads.tsx` | 127 |
| `app/screens/channel/header/header.tsx` | 337 |
| `app/products/agents/screens/agent_chat/header.tsx` | 75 |
| `app/products/playbooks/screens/participant_playbooks/participant_playbooks.tsx` | 132 |

The index's caller list for `NavigationHeader` matches this set. Some other files also import a `NavigationHeaderTitle`, but that is a different component, so I left them out.

**Which ones show a search field**

Only `app/screens/home/search/search.tsx` does. It is the only caller that passes `hasSearch={true}` (line 467). The `hasSearch` prop defaults to `false`, and the other callers either pass `false` explicitly (saved messages, recent mentions) or omit it.

**How the ref reaches the field**

1. `search.tsx` creates `const searchRef = useRef<SearchRef>(null)` at line 122 and passes `ref={searchRef}` to `<NavigationHeader>` at line 480.
2. `NavigationHeader` is a `forwardRef`, so that ref arrives as the second argument. It is not in `...searchProps`. It is passed directly as `ref={ref}` to `<NavigationSearch>` at `index.tsx:~124`, and only when `hasSearch` is true.
3. `NavigationSearch` (`app/components/navigation_header/search.tsx:34`) is also a `forwardRef`. It forwards the ref to the `<Search>` component from `@components/search` (`search.tsx` in that component, `ref={ref}`).
4. `@components/search/index.tsx:178` calls `useImperativeHandle(ref, ...)`, so the ref ends up as a `SearchRef` handle. That handle exposes `blur`, `cancel`, `clear`, `focus` and `setCaretPosition`, and `search.tsx` uses it at lines 209 (`focus`) and 447 (`blur`).

The `hasSearch` gate matters here. When `hasSearch` is false, `NavigationSearch` is not mounted, so a ref passed to `NavigationHeader` stays null.