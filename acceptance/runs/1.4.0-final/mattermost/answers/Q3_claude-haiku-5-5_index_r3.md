**Where NavigationHeader is rendered**

Eight files render `<NavigationHeader>` directly:

- `app/screens/home/search/search.tsx:463`
- `app/screens/home/saved_messages/saved_messages.tsx:213`
- `app/screens/home/recent_mentions/recent_mentions.tsx:176`
- `app/screens/global_drafts/global_drafts.tsx:98`
- `app/screens/global_threads/global_threads.tsx:127`
- `app/screens/channel/header/header.tsx:337`
- `app/products/agents/screens/agent_chat/header.tsx:75`
- `app/products/playbooks/screens/participant_playbooks/participant_playbooks.tsx:132`

`app/hooks/navigation_header.tsx` also renders the header, but it uses the lower-level `Header` from `components/navigation_header/header.tsx`, not `NavigationHeader`.

**Which ones show a search field**

Only `app/screens/home/search/search.tsx` passes `hasSearch={true}`. The other seven either pass `hasSearch={false}` or leave it at its default of `false`. `NavigationHeader` only mounts the search input when `hasSearch` is true (`app/components/navigation_header/index.tsx:128`).

**How the ref reaches the field**

1. `search.tsx` creates `searchRef = useRef<SearchRef>(null)` (line 122) and passes it as `ref={searchRef}` to `<NavigationHeader>` (line 480).
2. `NavigationHeader` is a `forwardRef<SearchRef, Props>` component (`app/components/navigation_header/index.tsx:53`). It forwards that ref unchanged to `<NavigationSearch ref={ref}>` (line 129–136), and the other props, including `placeholder`, `onChangeText`, `onFocus`, `onBlur`, `onClear`, `onCancel` and `defaultValue`, are passed through `...searchProps`.
3. `NavigationSearch` (`app/components/navigation_header/search.tsx:34`) is also `forwardRef`. It wraps the shared `@components/search` input and forwards the ref to `<Search ref={ref}>` (line 89).

So `searchRef.current` ends up as the shared `Search` component's imperative handle. `search.tsx` uses it to call `focus()` (line 209) and `blur()` (line 447). The `?.` on the focus call matters: when `hasSearch` is false, the ref is never attached, so `current` stays `null`.