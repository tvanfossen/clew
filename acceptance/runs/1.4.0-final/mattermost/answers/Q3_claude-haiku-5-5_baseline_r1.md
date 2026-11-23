**Files that render `NavigationHeader`**

The component is defined in `app/components/navigation_header/index.tsx` and imported as a default from `@components/navigation_header`. Eight files render it:

| File | `hasSearch` |
|---|---|
| `app/screens/home/search/search.tsx` | `true` |
| `app/screens/home/saved_messages/saved_messages.tsx` | `false` (explicit) |
| `app/screens/home/recent_mentions/recent_mentions.tsx` | `false` (explicit) |
| `app/screens/global_threads/global_threads.tsx` | unset (defaults to `false`) |
| `app/screens/global_drafts/global_drafts.tsx` | unset |
| `app/screens/channel/header/header.tsx` | unset |
| `app/products/playbooks/screens/participant_playbooks/participant_playbooks.tsx` | unset |
| `app/products/agents/screens/agent_chat/header.tsx` | unset |

Only `search.tsx` shows a search field. The Detox `NavigationHeader` under `detox/e2e/support/ui/component` is a separate test helper, not the app component.

**How the ref reaches the field**

1. `search.tsx:122` creates `const searchRef = useRef<SearchRef>(null)`, and `search.tsx:480` passes it as `ref={searchRef}` to `<NavigationHeader hasSearch={true} …>`.
2. `NavigationHeader` is a `forwardRef<SearchRef, Props>` (`index.tsx:53`). It does not attach the ref to its own view. When `hasSearch` is true, it renders `<NavigationSearch {...searchProps} ref={ref} />` (`index.tsx:128-135`). Props like `onChangeText`, `placeholder` and `defaultValue` travel the same way through the `...searchProps` spread.
3. `NavigationSearch` (`app/components/navigation_header/search.tsx:34`) is also a `forwardRef` and passes the ref straight to `<Search ref={ref} />` (line 89).
4. `Search` (`app/components/search/index.tsx:92`) owns the actual `TextInput` ref internally. It uses `useImperativeHandle(ref, …)` (line 178) to expose a small handle, `{ focus, blur }`, which delegates to its internal input ref.

So `searchRef.current` is the `{focus, blur}` handle, not the `TextInput` itself. `search.tsx` uses it at line 209 (`searchRef.current?.focus?.()`) and line 447 (`searchRef.current?.blur()`).

If `hasSearch` is false, `NavigationSearch` is never rendered, so a ref passed to `NavigationHeader` stays `null`. The other seven call sites pass no ref.