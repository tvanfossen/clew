**Files that render `NavigationHeader`:** eight, all as JSX:

| File | Shows search field? |
|---|---|
| `app/screens/home/search/search.tsx:463` | **Yes**, `hasSearch={true}` |
| `app/screens/global_threads/global_threads.tsx:127` | No |
| `app/screens/global_drafts/global_drafts.tsx:98` | No |
| `app/screens/channel/header/header.tsx:337` | No |
| `app/screens/home/recent_mentions/recent_mentions.tsx:176` | No, `hasSearch={false}` |
| `app/screens/home/saved_messages/saved_messages.tsx:213` | No, `hasSearch={false}` |
| `app/products/agents/screens/agent_chat/header.tsx:75` | No |
| `app/products/playbooks/screens/participant_playbooks/participant_playbooks.tsx:132` | No |

Only the Search screen passes `hasSearch`. The others either set it to false or leave it at its default of false. The grep for `hasSearch` in these files found nothing else.

**How the ref reaches the field:** there are four hops.

1. `search.tsx:122` creates `searchRef = useRef<SearchRef>(null)`. It is passed as `ref={searchRef}` to `<NavigationHeader>` at line 480. The search screen also calls `searchRef.current?.focus?.()` (line 209) and `searchRef.current?.blur()` (line 447).
2. `NavigationHeader` (`app/components/navigation_header/index.tsx:53`) is a `forwardRef<SearchRef, Props>`. It takes `hasSearch`, `hideHeader` and the rest of the search props (`...searchProps`). When `hasSearch` is true it renders `<NavigationSearch {...searchProps} hideHeader theme topStyle ref={ref} />` at around line 128.
3. `NavigationSearch` (`app/components/navigation_header/search.tsx:34`) is also a `forwardRef`. It wraps the props for the shared `Search` component with themed styles, focus and keyboard handling, and `testID='navigation.header.search_bar'`. It forwards `ref={ref}` to `<Search>`.
4. `Search` (`app/components/search/index.tsx:92`) is the final consumer. It exposes its focus/blur methods through `useImperativeHandle` (line 178), which is what the ref ends up controlling.

Two things to watch:
- `NavigationHeader` also spreads `...searchProps` into `NavigationSearch`, so `onChangeText`, `onSubmitEditing`, `onFocus`, `placeholder` and `defaultValue` from `search.tsx` travel the same route as the ref. `hideHeader` is destructured out and passed explicitly, since `NavigationSearch` needs it for its own focus handler.
- `app/hooks/navigation_header.tsx` (`useAppNavigationHeader`) also takes a `hasSearch` flag, but it renders the `Header` component from `components/navigation_header/header.tsx`, not `NavigationHeader`. It has no ref path, so it is not one of the eight files above.