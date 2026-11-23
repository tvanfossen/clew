The `NavigationHeader` component is rendered in eight files, and only one of them, the Search screen, shows a search field. That field gets its ref through a chain of three `forwardRef` hops.

**Files that render `<NavigationHeader>`** (all import the default export from `@components/navigation_header`):

| File | Passes `hasSearch`? |
|---|---|
| `app/screens/home/search/search.tsx:463` | `true` |
| `app/screens/home/saved_messages/saved_messages.tsx:213` | not set (defaults to `false`) |
| `app/screens/global_drafts/global_drafts.tsx:98` | not set |
| `app/screens/global_threads/global_threads.tsx:127` | not set |
| `app/screens/home/recent_mentions/recent_mentions.tsx:176` | not set |
| `app/screens/channel/header/header.tsx:337` | not set |
| `app/products/playbooks/screens/participant_playbooks/participant_playbooks.tsx:132` | not set |
| `app/products/agents/screens/agent_chat/header.tsx:75` | not set |

I checked the `hasSearch` and `ref` props in each file. Only `search.tsx` sets `hasSearch`, and it is the only one that sets `ref` on the header. The `hasSearch` value is an inference from the grep output, not from reading each call site in full. The `<NavigationHeader` grep covered `app/` only.

**How the ref reaches the field:**

1. `search.tsx` creates `searchRef = useRef<SearchRef>(null)` (line 122) and passes `ref={searchRef}` to `<NavigationHeader>` (line 480). It also calls `searchRef.current?.focus()` and `.blur()` from its own handlers.
2. `NavigationHeader` (`app/components/navigation_header/index.tsx:53`) is a `forwardRef<SearchRef, Props>`. It does not use the ref itself. It forwards it as `ref={ref}` to `<NavigationSearch>`, and only when `hasSearch` is true (around line 130).
3. `NavigationSearch` (`app/components/navigation_header/search.tsx:34`) is also a `forwardRef`. It forwards the ref to the `<Search>` component with `ref={ref}` (around line 85).
4. `Search` (`app/components/search/index.tsx:92`) is a `forwardRef` that calls `useImperativeHandle(ref, ...)` at line 178. The handle exposes `focus`, `blur`, `clear`, `cancel`, and `setCaretPosition`, which matches the `SearchRef` type at `app/components/search/index.tsx:47`. The handle delegates to its inner `searchRef`, which is attached to the underlying text input.

So `searchRef.current` is the imperative handle returned by `Search`, not the `TextInput` itself.

One consequence: if `hasSearch` is false, the ref passed to `NavigationHeader` is silently dropped, because the `NavigationSearch` branch is never rendered. The other seven call sites do not pass a ref, so this does not affect them today.