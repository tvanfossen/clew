**Short answer:** the post is kept locally and marked failed, the send is attempted once with no automatic retries, and the user retries by hand with "Try Again."

**1. What happens to the post.** `createPost` in `app/actions/remote/post.ts` (lines 154–199) writes the post to WatermelonDB before the network call, keyed by a pending ID (`${userId}:${timestamp}`). If `client.createPost` throws, it rewrites that record with `props.failed = true` and a fresh `update_at`, and the UI shows the failure indicator. There are three exceptions. For `DELETED_ROOT_POST_ERROR`, `TOWN_SQUARE_READ_ONLY_ERROR`, or `PLUGIN_DISMISSED_POST_ERROR`, the post is removed instead of kept (`removePost`). For `BOR_DENIED_BY_POLICY_ERROR`, the cached render-permission entry for the channel is also expired.

**2. How many automatic retries: zero.**
- The app's network client defaults to `retryLimit: 3` with exponential backoff (`app/managers/network_manager.ts:68-73`).
- But `createPost` in `app/client/rest/posts.ts:43-47` passes `noRetry: true`.
- `buildRequestOptions` in `app/client/rest/tracking.ts:383-385` turns that into `retryPolicyConfiguration: {retryLimit: 0}`, which overrides the default.
- Nothing else in `app/` re-invokes `createPost` on failure.

**3. What retrying does.** Retry is manual, via the "Try Again" item in the failed-post bottom sheet (`app/components/post_list/post/body/failed/index.tsx:46-49`), which calls `retryFailedPost` (`post.ts:228-307`):
- It rebuilds the API payload from the stored post and sets `props.failed = false` plus a new `update_at`, so the UI goes back to pending before the network call.
- It calls `client.createPost` again, still with no retry.
- On success, it writes the server's returned post into the DB and updates the channel's last-post time.
- On failure, it applies the same split: the three server errors above remove the post, anything else sets `failed = true` again.
- "Delete Message" in the same sheet calls `removePost` directly.

**Caveat.** `isPostFailed` (`app/utils/post/index.ts:97-98`) also treats a pending post as failed once it is older than `POST_TIME_TO_FAIL` (10 s, `app/constants/post.ts:57`). That is a UI-side timeout and does not cancel the request. A post can therefore show as failed while its original send is still in flight and may yet succeed. I did not trace what happens to the original request's result in that case.