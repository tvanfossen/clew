Only one screen renders a search field through NavigationHeader: the Home Search screen. Eight files render `<NavigationHeader>`, and the Search screen is the only one that turns search on.

**Files that render `<NavigationHeader>`** (the 91-file grep for the name was mostly import lines):

- `app/screens/home/search/search.tsx`, with `hasSearch={true}`
- `app/screens/home/saved_messages/saved_messages.tsx`, with `hasSearch={false}`
- `app/screens/home/recent_mentions/recent_mentions.tsx`, with `hasSearch={false}`
- `app/screens/global_threads/global_threads.tsx`
- `app/screens/global_drafts/global_drafts.tsx`
- `app/screens/channel/header/header.tsx`
- `app/products/playbooks/screens/participant_playbooks/participant_playbooks.tsx`
- `app/products/agents/screens/agent_chat/header.tsx`

The last five don't set `hasSearch`, so it defaults to `false` in `app/components/navigation_header/index.tsx:54`.

**Ref path for the search field.** The chain runs through three forwarding layers:

1. **Screen** (`app/screens/home/search/search.tsx`): `const searchRef = useRef<SearchRef>(null)` at line 122, passed as `ref={searchRef}` at line 480.
2. **NavigationHeader** (`app/components/navigation_header/index.tsx:53`): `forwardRef<SearchRef, Props>`. It doesn't attach the ref to its own header or large-title pieces. It forwards it only to `<NavigationSearch ref={ref}>` when `hasSearch` is true (line 134).
3. **NavigationSearch** (`app/components/navigation_header/search.tsx:34`): another `forwardRef`, which passes the ref to `<Search ref={ref}>` at line 89. It also wires the keyboard-show/hide tab-bar emitters and hides the header on focus.
4. **Search** (`app/components/search/index.tsx:92`): the innermost `forwardRef`. It calls `useImperativeHandle(ref, …)` at line 178, exposing `focus()` and `blur()` that act on its internal input.

The screen then calls `searchRef.current?.focus?.()` (line 209) and `searchRef.current?.blur()` (line 447). The screen never touches the TextInput directly; it only sees the `SearchRef` handle that `Search` exposes.