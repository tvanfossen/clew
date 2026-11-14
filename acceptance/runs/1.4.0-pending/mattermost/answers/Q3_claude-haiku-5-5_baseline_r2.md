**Files that render `<NavigationHeader>`:** eight, found with a JSX search for `<NavigationHeader`:

| File | Search field? |
|---|---|
| `app/screens/home/search/search.tsx:463` | Yes, `hasSearch={true}` |
| `app/screens/home/saved_messages/saved_messages.tsx:213` | No, `hasSearch={false}` |
| `app/screens/home/recent_mentions/recent_mentions.tsx:176` | No, `hasSearch={false}` |
| `app/screens/global_drafts/global_drafts.tsx:98` | No (no `hasSearch` prop) |
| `app/screens/global_threads/global_threads.tsx:127` | No (no `hasSearch` prop) |
| `app/screens/channel/header/header.tsx:337` | No (no `hasSearch` prop) |
| `app/products/playbooks/screens/participant_playbooks/participant_playbooks.tsx:132` | No (no `hasSearch` prop) |
| `app/products/agents/screens/agent_chat/header.tsx:75` | No (no `hasSearch` prop) |

A plain text search for `NavigationHeader` across `app/` returns 91 files. I did not inspect those individually; most are route files or hooks that mention the name without rendering it.

**Only `search.tsx` shows a search field.** It is the only one that passes `hasSearch={true}`. Its `NavigationHeader` gets a ref, and the ref reaches the input through this chain:

```
search.tsx:122   const searchRef = useRef<SearchRef>(null)
      │
      ▼ ref={searchRef}                       (search.tsx:480)
NavigationHeader  forwardRef<SearchRef>       (navigation_header/index.tsx:53)
      │  rendered only when hasSearch is true  (index.tsx:128)
      ▼ ref={ref}                             (index.tsx:134)
NavigationSearch  forwardRef<SearchRef>       (navigation_header/search.tsx:34)
      │  passes ref to Search, adds styling and onFocus
      ▼ ref={ref}                             (search.tsx:89)
Search  forwardRef<SearchRef>                 (components/search/index.tsx:92)
      │  useImperativeHandle(ref, …)          (components/search/index.tsx:178)
      ▼ wraps its own inner TextInput ref (searchRef, index.tsx:96, attached at :222)
```

`useImperativeHandle` exposes a small API (`focus`, `blur`, `clear`, `cancel`, `setSelection`) rather than the raw `TextInput`. `search.tsx` calls `searchRef.current?.focus?.()` at line 209 and `searchRef.current?.blur()` at line 447.

Two things to know:
- The `searchRef` in `search.tsx` and the `searchRef` inside `components/search/index.tsx` are different refs with the same name. The first is the parent's handle, and the second is the internal `TextInput`.
- If `hasSearch` is false, `NavigationSearch` is never mounted, so the ref stays `null`. Any caller that passes a ref without `hasSearch` gets nothing.

One note: the `Read` result for `navigation_header/search.tsx` included an appended message telling me to call a "dossier" tool. That is not part of your request and I did not act on it. The findings above come from `Grep` and `Read` only.