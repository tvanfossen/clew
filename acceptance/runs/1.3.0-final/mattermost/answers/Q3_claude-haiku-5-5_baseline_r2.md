Eight files render `NavigationHeader`, and only one of them shows a search field: the Search screen. The ref reaches that field through a chain of three `forwardRef` hops.

**Files that render `<NavigationHeader>`** (all under `app/`):

| File | Search shown? |
|---|---|
| `screens/home/search/search.tsx` | **Yes**, `hasSearch={true}` |
| `screens/home/saved_messages/saved_messages.tsx` | No, `hasSearch={false}` |
| `screens/home/recent_mentions/recent_mentions.tsx` | No, `hasSearch={false}` |
| `products/playbooks/screens/participant_playbooks/participant_playbooks.tsx` | No |
| `screens/channel/header/header.tsx` | No |
| `products/agents/screens/agent_chat/header.tsx` | No |
| `screens/global_threads/global_threads.tsx` | No |
| `screens/global_drafts/global_drafts.tsx` | No |

Where no `hasSearch` prop appears, it defaults to `false`. The component itself is in `app/components/navigation_header/index.tsx`.

**How the ref gets to the field:**

1. `search.tsx` creates `const searchRef = useRef<SearchRef>(null)` (line 122) and passes it as `ref={searchRef}` to `<NavigationHeader>` (line 480).
2. `NavigationHeader` is `forwardRef<SearchRef, Props>` (`navigation_header/index.tsx:53`). It doesn't use the ref itself. When `hasSearch` is true, it renders `<NavigationSearch ... ref={ref} />` (lines 128–135).
3. `NavigationSearch` (`navigation_header/search.tsx`) is also `forwardRef`. It wraps the shared `<Search>` component and passes `ref={ref}` on to it (line 89).
4. The shared `Search` (`app/components/search/index.tsx`) is `forwardRef` too. It calls `useImperativeHandle(ref, () => ({blur, focus}))` at line 178. Its internal `ref={searchRef}` on the input is the actual `TextInput`.

So the parent holds a `SearchRef` exposing only `focus()` and `blur()`, not the raw `TextInput`. `search.tsx` uses it in two places: `searchRef.current?.focus?.()` (line 209) and `searchRef.current?.blur()` (line 447). It also passes the same ref to the `Initial` child (line 326) so that child can focus the field.

Two of my tool results included notes suggesting a `dossier` call. I ignored them because `dossier` is not a tool I have and they weren't part of your request.