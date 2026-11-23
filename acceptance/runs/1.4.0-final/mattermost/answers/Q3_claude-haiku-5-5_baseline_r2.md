**Files that render `NavigationHeader`**

Eight production files render it, all importing from `@components/navigation_header`:

| File | `hasSearch` |
|---|---|
| `app/screens/home/search/search.tsx` | `true` |
| `app/screens/home/saved_messages/saved_messages.tsx` | `false` |
| `app/screens/home/recent_mentions/recent_mentions.tsx` | `false` |
| `app/screens/global_threads/global_threads.tsx` | not set |
| `app/screens/global_drafts/global_drafts.tsx` | not set |
| `app/screens/channel/header/header.tsx` | not set |
| `app/products/agents/screens/agent_chat/header.tsx` | not set |
| `app/products/playbooks/screens/participant_playbooks/participant_playbooks.tsx` | not set |

`global_threads.test.tsx` and `header.test.tsx` also import it. Grep also matched `channel_configuration.tsx` and `channel_share.tsx`, but I did not check whether they render the component. Only the import-and-JSX pattern above was confirmed.

**Which show a search field**

Only the Search screen (`search.tsx`) renders the search field, because it is the only caller that passes `hasSearch={true}`. The header's search row is conditional on that prop, so the other callers show no search field.

**How the ref reaches the field**

The chain is three `forwardRef` layers:

1. **`search.tsx:122`** creates `searchRef = useRef<SearchRef>(null)` and passes it as `ref={searchRef}` to `<NavigationHeader>` (line 480).
2. **`components/navigation_header/index.tsx:53`** is `forwardRef<SearchRef, Props>`. When `hasSearch` is true it renders `<NavigationSearch ... ref={ref} />` (line 134). The other props are spread through `...searchProps`.
3. **`components/navigation_header/search.tsx:34`** is also `forwardRef`. It renders `<Search ... ref={ref} />` (line 89), adding theming, the cancel-button props, and the Android tab-bar show/hide on keyboard events.
4. **`components/search/index.tsx`** is the leaf. It calls `useImperativeHandle(ref, ...)` (line 178) to expose `focus()` and `blur()`, which delegate to its internal `searchRef` on the `TextInput`.

So `searchRef.current` in `search.tsx` is the imperative `SearchRef` object (`{focus, blur}`), not the `TextInput`. The screen uses it at `search.tsx:209` (`searchRef.current?.focus?.()`) and `search.tsx:447` (`searchRef.current?.blur()`).

One thing to note: `hideHeader`, `onFocus` and `onBlur` are not forwarded by the ref. `NavigationSearch` wraps `onFocus` to call `hideHeader` before calling the caller's `onFocus`.