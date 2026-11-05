**Files that render `NavigationHeader`:** ten JSX sites, all importing the default export from `@components/navigation_header`:

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

`app/screens/global_threads/global_threads.test.tsx` and `app/screens/channel/header/header.test.tsx` also import it, but only for tests. The dossier's caller list matches the grep.

**Which show a search field:** only `app/screens/home/search/search.tsx`, which passes `hasSearch={true}`. The other nine pass `hasSearch={false}` or omit it. With `hasSearch` false, `NavigationHeader` renders no search input, so the ref is dropped.

**How the ref reaches the input:**

```
search.tsx        const searchRef = useRef<SearchRef>(null)          (line 122)
   │ ref={searchRef}                                                (line 480)
   ▼
navigation_header/index.tsx   forwardRef<SearchRef, Props>           (line 53)
   │ <NavigationSearch {...searchProps} ref={ref} />                 (line ~135)
   ▼
navigation_header/search.tsx  forwardRef<SearchRef, Props>           (line 34)
   │ <Search {...searchProps} ref={ref} testID='navigation.header.search_bar' />  (line 89)
   ▼
components/search/index.tsx   forwardRef + useImperativeHandle       (lines 92, 178)
   │ exposes blur / cancel / clear / focus / setCaretPosition,
   │ delegating to an internal ref on the underlying input
```

- The screen calls `searchRef.current?.focus?.()` (line 209) and `searchRef.current?.blur()` (line 447).
- Props such as `onChangeText`, `onSubmitEditing`, `placeholder`, `onFocus`, `defaultValue` travel through `...searchProps` at each hop. `NavigationHeader` strips only the header-specific props and forwards the rest.
- `NavigationSearch` also wraps `onFocus` to call `hideHeader` before the screen's own handler runs.

**Not part of this chain:** `app/hooks/navigation_header.tsx` (`useAppNavigationHeader`) renders the internal `Header` from `components/navigation_header/header.tsx`, not `NavigationHeader`, so it never creates a search field. It is used by `app/routes/(authenticated)/thread.tsx`, which passes `hasSearch={false}`.