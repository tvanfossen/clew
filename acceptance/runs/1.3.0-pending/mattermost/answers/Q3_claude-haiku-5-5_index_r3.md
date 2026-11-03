**Files that render `NavigationHeader`:** eight, all importing the default export from `@components/navigation_header`. The index and a grep agree on this list:

| File | Passes `hasSearch` | Passes `ref` |
|---|---|---|
| `app/screens/home/search/search.tsx:463` | `true` | yes (`searchRef`) |
| `app/screens/channel/header/header.tsx:337` | default (false) | no |
| `app/screens/home/saved_messages/saved_messages.tsx:213` | `false` | no |
| `app/screens/home/recent_mentions/recent_mentions.tsx:176` | `false` | no |
| `app/screens/global_drafts/global_drafts.tsx:98` | default (false) | no |
| `app/screens/global_threads/global_threads.tsx:127` | default (false) | no |
| `app/products/playbooks/screens/participant_playbooks/participant_playbooks.tsx:132` | default (false) | no |
| `app/products/agents/screens/agent_chat/header.tsx:75` | default (false) | no |

`app/routes/(authenticated)/thread.tsx` also passes `hasSearch={false}`, but it renders the lower-level `Header` from `app/components/navigation_header/header.tsx`, not `NavigationHeader`, so it is not a caller.

**The only file that shows a search field is `search.tsx`.** It is the only caller with `hasSearch={true}`.

**How the ref reaches the field:**

1. `search.tsx` creates `searchRef = useRef<SearchRef>(null)` (line 122) and passes `ref={searchRef}` to `<NavigationHeader>` (line 480). It also calls `searchRef.current?.focus()` and `.blur()` (lines 209 and 447).
2. `NavigationHeader` is a `forwardRef<SearchRef, Props>` (`app/components/navigation_header/index.tsx:53`). When `hasSearch` is true, it renders `<NavigationSearch {...searchProps} ... ref={ref} />` (lines 128–137). The ref is forwarded as-is, and the other search props (`onChangeText`, `onSubmitEditing`, `placeholder`, `defaultValue`, and so on) travel in through `...searchProps`.
3. `NavigationSearch` (`app/components/navigation_header/search.tsx:34`) is another `forwardRef`. It wraps its `Search` child in an `Animated.View` and passes `ref={ref}` through to `Search`.
4. `Search` (`app/components/search/index.tsx:92`) is the one that owns the `TextInput`. It calls `useImperativeHandle(ref, ...)` (line 178) to expose a `SearchRef` of `{ blur, focus }`, which delegate to its internal input ref.

So the chain is `search.tsx` `searchRef` → `NavigationHeader` → `NavigationSearch` → `Search` → `useImperativeHandle`. The ref never points at the `TextInput` itself. It points at the handle `Search` builds, and that handle is what `focus()` and `blur()` call.

One detail matters for anyone changing this: when `hasSearch` is false, `NavigationHeader` drops the ref entirely, because the `NavigationSearch` branch is skipped. A ref passed alongside `hasSearch={false}` would silently stay `null`.