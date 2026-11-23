**Files that render `<NavigationHeader>`:** eight files render the component directly:

- `app/screens/home/search/search.tsx`: the only one that shows a search field (`hasSearch={true}`, line 463).
- `app/screens/home/recent_mentions/recent_mentions.tsx` and `app/screens/home/saved_messages/saved_messages.tsx`: pass `hasSearch={false}`.
- `app/screens/global_threads/global_threads.tsx`, `app/screens/global_drafts/global_drafts.tsx`, `app/screens/channel/header/header.tsx`, `app/products/agents/screens/agent_chat/header.tsx`, `app/products/playbooks/screens/participant_playbooks/participant_playbooks.tsx`: no `hasSearch` prop, so no search field.

The other ~80 matches are `NavigationHeaderTitle` or the `useNavigationHeader` hook, not the `NavigationHeader` component. `app/components/navigation_header/index.tsx` is the definition, and it imports `NavigationHeaderLargeTitle` and `Header` internally.

**How the ref reaches the field:** the chain has three `forwardRef` hops.

1. `search.tsx` creates `searchRef = useRef<SearchRef>(null)` (line 122) and passes `ref={searchRef}` to `<NavigationHeader>` (line 480).
2. `NavigationHeader` (`app/components/navigation_header/index.tsx`) is a `forwardRef<SearchRef, Props>`. It doesn't use the ref itself. It forwards it to `<NavigationSearch ... ref={ref}>`, but only when `hasSearch` is true.
3. `NavigationSearch` (`app/components/navigation_header/search.tsx`) is also a `forwardRef`. It forwards the ref to `<Search ... ref={ref}>` from `app/components/search/index.tsx`.
4. `Search` calls `useImperativeHandle(ref, () => ({blur, cancel, clear, focus, setCaretPosition}))` (line 178). Those methods delegate to its own internal `searchRef`, which points at the underlying `SearchBar`/`TextInput`.

So `searchRef.current.focus()` and `.blur()` in `search.tsx` (lines 209 and 447) call the `SearchRef` methods exposed by `Search`, not the native input directly. The `SearchRef` type is the only contract, so the screen never sees the TextInput. Also note that `hideHeader` and the search props are passed through `...searchProps` and are not part of the ref path.