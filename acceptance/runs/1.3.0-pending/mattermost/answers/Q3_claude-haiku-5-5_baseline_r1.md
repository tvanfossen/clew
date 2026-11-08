**Files that render `<NavigationHeader`** (8 total, found by searching for the JSX tag):

- `app/screens/home/search/search.tsx`
- `app/screens/home/saved_messages/saved_messages.tsx`
- `app/screens/home/recent_mentions/recent_mentions.tsx`
- `app/screens/global_threads/global_threads.tsx`
- `app/screens/global_drafts/global_drafts.tsx`
- `app/screens/channel/header/header.tsx`
- `app/products/agents/screens/agent_chat/header.tsx`
- `app/products/playbooks/screens/participant_playbooks/participant_playbooks.tsx`

The other matches in the first grep were files that only mention the name in imports, hook names, or other identifiers, so I left them out.

**Which show a search field:** Only `search.tsx`. It is the only caller that passes `hasSearch={true}` (line 467). `saved_messages.tsx` and `recent_mentions.tsx` pass `hasSearch={false}`, and the other five don't pass the prop. `hasSearch` defaults to `false` in `navigation_header/index.tsx`, so none of them render a search bar.

**How the ref reaches the input:**

1. `search.tsx` creates `searchRef = useRef<SearchRef>(null)` (line 122) and passes it as `ref={searchRef}` to `<NavigationHeader>` (line 480).
2. `navigation_header/index.tsx` is a `forwardRef<SearchRef, Props>`. When `hasSearch` is true, it passes that `ref` straight through to `<NavigationSearch ... ref={ref}>` (line 134). The other props are spread via `...searchProps`, but `ref` is not part of that spread.
3. `navigation_header/search.tsx` is also a `forwardRef`. It forwards `ref` to `<Search ... ref={ref}>` (line 89).
4. `components/search/index.tsx` is the layer that owns the actual input. It keeps an internal `searchRef` on the RNEUI `SearchBar`, which wraps the native `TextInput`. It then uses `useImperativeHandle` to expose only `blur`, `cancel`, `clear`, `focus`, and `setCaretPosition` on the outer ref. Those methods forward to the internal input.

So `searchRef.current.focus()` in `search.tsx` (line 209) calls the `focus` method from that imperative handle, which calls `focus()` on the `TextInput`. The ref does not point at the `TextInput` itself.

**One caveat:** If `hasSearch` is false, `NavigationHeader` never attaches its `ref` to anything, so the ref stays `null`. A caller that passes a ref without `hasSearch={true}` gets nothing.

A PostToolUse hook note appeared in one of the tool results suggesting I call a `dossier` tool. That isn't part of your request and I don't have that tool, so I ignored it.