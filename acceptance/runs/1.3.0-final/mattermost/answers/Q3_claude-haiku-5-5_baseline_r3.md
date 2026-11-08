**Files that render `NavigationHeader`** (imported from `@components/navigation_header`): 10 files.

- `app/screens/home/search/search.tsx`
- `app/screens/home/saved_messages/saved_messages.tsx`
- `app/screens/home/recent_mentions/recent_mentions.tsx`
- `app/screens/global_drafts/global_drafts.tsx`
- `app/screens/global_threads/global_threads.tsx`
- `app/screens/channel/header/header.tsx`
- `app/products/playbooks/screens/participant_playbooks/participant_playbooks.tsx`
- `app/products/agents/screens/agent_chat/header.tsx`
- `app/screens/channel/header/header.test.tsx` and `app/screens/global_threads/global_threads.test.tsx` (tests only)

I filtered on the import path, so a file that reaches the component some other way would not appear in this list.

**Which show a search field:** only `screens/home/search/search.tsx`. It passes `hasSearch={true}` (line 467). The other callers either omit `hasSearch` or pass `hasSearch={false}` (for example, `saved_messages.tsx:218` and `recent_mentions.tsx:181`). Those files still pass a `ref`, but to their scroll view, not to a search field.

**How the ref reaches the field:**

1. `search.tsx` creates `const searchRef = useRef<SearchRef>(null)` (line 122) and passes `ref={searchRef}` to `NavigationHeader` (line 480).
2. `components/navigation_header/index.tsx` is a `forwardRef<SearchRef, Props>`. When `hasSearch` is true, it renders `<NavigationSearch {...searchProps} ... ref={ref} />` (lines 128–136). The ref is forwarded as is, and `searchProps` carries the search-related props (`onChangeText`, `placeholder`, `onCancel`, and so on).
3. `components/navigation_header/search.tsx` is also a `forwardRef`. It wraps the shared `Search` component and forwards `ref={ref}` to it (line 89), adding the theme styling and a `hideHeader` call on focus.
4. `components/search/index.tsx` is the shared `Search` component. It does not hand out the `TextInput` ref directly. It calls `useImperativeHandle(ref, …)` (line 178) to expose a `SearchRef` of `{ blur, focus }`, which delegates to its internal `searchRef` (lines 179–190).

So `search.tsx` can call `searchRef.current?.focus()` (line 209) or `.blur()` (line 447), and the call goes through the imperative handle down to the `TextInput`.

I did not run the app, so this comes from reading the code only.