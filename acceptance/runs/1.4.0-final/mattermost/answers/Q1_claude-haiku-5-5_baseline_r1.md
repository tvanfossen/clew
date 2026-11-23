**Short answer:** the post is kept locally and marked failed, the app does not retry it automatically (one send attempt, zero automatic retries), and "Try Again" re-sends it as a fresh request with a new timestamp.

**What happens on failure** (`app/actions/remote/post.ts`, `createPost`, around lines 152–199):

- The post is written to the local DB before the network call, so it shows in the list while pending.
- `client.createPost` is called once. If it throws, the code logs the error and builds an error post with `props.failed = true`. That post keeps its pending ID and is saved with `handlePosts`.
- Three server errors are exceptions: `DELETED_ROOT_POST_ERROR`, `TOWN_SQUARE_READ_ONLY_ERROR` and `PLUGIN_DISMISSED_POST_ERROR`. For these the post is removed (`removePost`) instead of kept as failed.
- `BOR_DENIED_BY_POLICY_ERROR` also expires the cached render-permission entry for the channel, and the post is still kept as failed.

**Automatic retries:** none. `createPost` makes one call and has no loop or backoff. I found no caller that re-invokes it on failure or on reconnect. The `handle_send_message.ts` callers (lines 163 and 176) fire it once. The network client library may have its own transport-level retries; I did not check that dependency.

**What "Try Again" does** (`retryFailedPost`, lines 228–307):

- It is triggered only by the user, from the failed-post bottom sheet (`app/components/post_list/post/body/failed/index.tsx`, "Try Again", testID `post.failed.retry`).
- It rebuilds the payload from the stored post with `failed: false`, a new `create_at` and `update_at` set to now, and an empty `id`.
- It updates the existing local record to the pending state, then calls `client.createPost` again. On success it upserts the server's post. On failure it marks the post failed again, or removes it for the three error types above.
- The same post record is reused, so the user sees the same message move back to pending.

**UI nuance:** `isPostFailed` (`app/utils/post/index.ts`, line 97) also treats a post as failed when it has been pending for more than `POST_TIME_TO_FAIL` (10 seconds, `app/constants/post.ts`), even without a `failed` prop. A slow send can therefore show the failed icon before the request has actually failed.