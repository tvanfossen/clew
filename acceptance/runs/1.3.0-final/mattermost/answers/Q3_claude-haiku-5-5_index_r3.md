**Files that render `NavigationHeader`**

Eight files in `app/` render it with JSX, all importing it from `@components/navigation_header`:

| File | `hasSearch` |
|---|---|
| `app/screens/home/search/search.tsx` | `true` |
| `app/screens/home/saved_messages/saved_messages.tsx` | `false` |
| `app/screens/home/recent_mentions/recent_mentions.tsx` | `false` |
| `app/screens/global_threads/global_threads.tsx` | not set (default `false`) |
| `app/screens/global_drafts/global_drafts.tsx` | not set |
| `app/screens/channel/header/header.tsx` | not set |
| `app/products/agents/screens/agent_chat/header.tsx` | not set |
| `app/products/playbooks/screens/participant_playbooks/participant_playbooks.tsx` | not set |

The `hasSearch` values come from grep. The "not set" rows are inferred from the absence of any `hasSearch` in those files. The index's callers list for `NavigationHeader` agrees with this set.

Two near-misses are not render sites. `app/hooks/navigation_header.tsx` (`useAppNavigationHeader`) takes a `hasSearch` argument but renders the separate `Header` component. `app/routes/(authenticated)/thread.tsx` also renders `Header`, not `NavigationHeader`.

**Which show a search field**

Only `search.tsx` (the Search screen, around line 463) passes `hasSearch={true}`. Its search field is therefore the only search field rendered through `NavigationHeader`.

**How the ref reaches the field**

1. `search.tsx:122` creates `const searchRef = useRef<SearchRef>(null)`.
2. `search.tsx:480` passes it as `ref={searchRef}` to `<NavigationHeader>`.
3. `navigation_header/index.tsx:53` wraps the component in `forwardRef<SearchRef, Props>`, so the ref arrives as the second argument `ref`.
4. When `hasSearch` is true, `index.tsx:128-135` renders `<NavigationSearch {...searchProps} hideHeader topStyle theme ref={ref}/>`. The text-field props (`onChangeText`, `placeholder`, `onClear`, `onCancel`, `defaultValue`, and so on) travel through `...searchProps`.
5. `navigation_header/search.tsx:34-89` is another `forwardRef<SearchRef>`. It adds theme styling and keyboard/tab-bar handling, then passes `ref={ref}` to `<Search>`.
6. `components/search/index.tsx:178` calls `useImperativeHandle(ref, ...)`. It exposes `focus`, `blur`, `clear`, `cancel`, and `setCaretPosition`/`setSelection` on `SearchRef`. The internal `TextInput` is held in a separate `searchRef` (line 96, attached at line 222).

So `search.tsx` never touches the `TextInput`. It calls methods on the imperative handle, which forwards to the input. For example, `search.tsx:209` calls `searchRef.current?.focus?.()` and `search.tsx:447` calls `blur()`.

**Caveat:** `index.tsx` forwards the ref only inside the `hasSearch &&` branch. Passing a ref to `NavigationHeader` without `hasSearch={true}` leaves the ref unattached.