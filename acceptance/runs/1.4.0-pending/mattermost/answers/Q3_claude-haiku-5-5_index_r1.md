Eight files render `NavigationHeader`, and only one of them shows a search field: `app/screens/home/search/search.tsx`. Its ref reaches the input through a chain of three `forwardRef` hops, ending in an imperative `{focus, blur}` handle.

**Files rendering `NavigationHeader`**

| File | Line | Search? |
|---|---|---|
| `app/screens/home/search/search.tsx` | 463 | Yes, `hasSearch={true}` |
| `app/screens/home/saved_messages/saved_messages.tsx` | 213 | Passes `hasSearch={false}` |
| `app/screens/home/recent_mentions/recent_mentions.tsx` | 176 | Passes `hasSearch={false}` |
| `app/screens/global_threads/global_threads.tsx` | 127 | No `hasSearch` prop |
| `app/screens/channel/header/header.tsx` | 337 | No `hasSearch` prop |
| `app/screens/global_drafts/global_drafts.tsx` | 98 | No `hasSearch` prop |
| `app/products/playbooks/screens/participant_playbooks/participant_playbooks.tsx` | 132 | No `hasSearch` prop |
| `app/products/agents/screens/agent_chat/header.tsx` | 75 | No `hasSearch` prop |

The index confirms these as the only JSX call sites. `hasSearch` defaults to `false`, so the last five render no search bar.

**How the ref reaches the field**

1. **Caller.** `search.tsx:122` creates `const searchRef = useRef<SearchRef>(null)`. It passes `ref={searchRef}` to `<NavigationHeader>` at line 480, alongside `hasSearch={true}` and the search props (`onChangeText`, `onSubmitEditing`, `onClear`, `onCancel`, `placeholder`, and so on).
2. **`NavigationHeader`.** `app/components/navigation_header/index.tsx` is `forwardRef<SearchRef, Props>`. It pulls `hasSearch` out of the props and collects the rest into `...searchProps`. The ref is not attached to the title header or the large title. It is forwarded only into `<NavigationSearch {...searchProps} ... ref={ref} />`, which renders only when `hasSearch` is true (lines 128–138).
3. **`NavigationSearch`.** `app/components/navigation_header/search.tsx` is also `forwardRef<SearchRef>`. It wraps the `onFocus` handler to call `hideHeader`, adds header styling, and renders `<Search ... ref={ref} testID='navigation.header.search_bar' />` (lines 79–91).
4. **`Search`.** `app/components/search/index.tsx` is `forwardRef<SearchRef>`. It keeps its own internal ref on the `TextInput` (line 222) and exposes `blur()` and `focus()` through `useImperativeHandle` (lines 178–190), which delegate to that internal ref.

So `searchRef` does not point at the `TextInput`. It holds the `{focus, blur}` handle that `Search` builds. The screen uses it directly: `searchRef.current?.focus?.()` at `search.tsx:209` and `searchRef.current?.blur()` at line 447.

If `hasSearch` is false, the ref is silently dropped, because `NavigationSearch` is never rendered. Passing a ref to a non-search header does nothing.