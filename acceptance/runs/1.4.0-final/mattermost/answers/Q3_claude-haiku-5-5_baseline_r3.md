**Files that render `NavigationHeader`**

The component is defined in `app/components/navigation_header/index.tsx`. Eight screens render it directly:

| File | Search field? |
|---|---|
| `app/screens/home/search/search.tsx` (L463) | Yes, `hasSearch={true}` |
| `app/screens/channel/header/header.tsx` (L337) | No |
| `app/screens/global_threads/global_threads.tsx` (L127) | No |
| `app/screens/global_drafts/global_drafts.tsx` (L98) | No |
| `app/screens/home/saved_messages/saved_messages.tsx` (L213) | No, `hasSearch={false}` |
| `app/screens/home/recent_mentions/recent_mentions.tsx` (L176) | No, `hasSearch={false}` |
| `app/products/playbooks/screens/participant_playbooks/participant_playbooks.tsx` (L132) | No, no `hasSearch` prop |
| `app/products/agents/screens/agent_chat/header.tsx` (L75) | No, no `hasSearch` prop |

The `hooks/navigation_header` route hooks don't render the component. They set Stack header options, so they're not in the table.

Only `search.tsx` shows a search field.

**How the ref reaches the field**

1. `search.tsx` creates `const searchRef = useRef<SearchRef>(null)` (L122) and passes `ref={searchRef}` to `<NavigationHeader>` (L480).
2. `NavigationHeader` is a `forwardRef<SearchRef, Props>`. It forwards the ref to `<NavigationSearch ref={ref}>` (L134), but only when `hasSearch` is true. Without a search field the ref is never attached.
3. `app/components/navigation_header/search.tsx` is another `forwardRef`. It wraps the shared `Search` component and passes the ref through (L89).
4. `app/components/search/index.tsx` is also a `forwardRef`. Its internal `useRef<TextInput>` is attached to the actual `TextInput`. `useImperativeHandle` (L178) then exposes only `{ focus, blur }` to the outer ref, delegating to that internal `TextInput` ref.

So the caller gets a `SearchRef` with `focus()` and `blur()`, not the `TextInput` itself. `search.tsx` uses it for `searchRef.current?.focus?.()` (L209) and `searchRef.current?.blur()` (L447, on Enter via the hardware keyboard).