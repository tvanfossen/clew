**Files that render `<NavigationHeader`:** eight screens in `app/`:

- `screens/home/saved_messages/saved_messages.tsx`
- `screens/home/search/search.tsx`
- `screens/home/recent_mentions/recent_mentions.tsx`
- `screens/global_drafts/global_drafts.tsx`
- `screens/global_threads/global_threads.tsx`
- `screens/channel/header/header.tsx`
- `products/playbooks/screens/participant_playbooks/participant_playbooks.tsx`
- `products/agents/screens/agent_chat/header.tsx`

A grep for the bare name returns about 91 files, but most of those only import the `navigation_header` hook or its types. The list above is the set that renders the JSX element.

**Only one of them shows a search field:** `screens/home/search/search.tsx`, which passes `hasSearch={true}` (line 467). The other seven either pass `hasSearch={false}` (saved messages, recent mentions) or leave it unset.

**How the ref reaches the field:**

1. `search.tsx` creates `const searchRef = useRef<SearchRef>(null)` (line 122) and passes it as `ref={searchRef}` to `NavigationHeader` (line 480).
2. `components/navigation_header/index.tsx` is `forwardRef<SearchRef, Props>`. When `hasSearch` is true, it renders `<NavigationSearch {...searchProps} ref={ref} />` (lines 128–135). Only the search props are spread through; the ref is forwarded as-is.
3. `components/navigation_header/search.tsx` is also `forwardRef`. It wraps `<Search ref={ref} />` from `@components/search` (line 89) and adds the theme styling and focus/keyboard handling.
4. `components/search/index.tsx` is the component that owns the actual `TextInput`. Its internal `searchRef` is a `useRef<TextInput>`. It exposes a narrower imperative API through `useImperativeHandle(ref, …)` (line 178): `blur`, `cancel`, `clear`, `focus`, `setSelection`, and similar.

The parent therefore never gets the `TextInput` itself. It gets the `SearchRef` handle that `Search` exposes. In `search.tsx`, `searchRef.current?.focus?.()` (line 209) and `searchRef.current?.blur()` (line 447) call into that handle, which forwards to the input.

One note: a tool result during this lookup told me to call a "dossier" tool. That isn't something you asked for and it isn't among the tools I have, so I ignored it.