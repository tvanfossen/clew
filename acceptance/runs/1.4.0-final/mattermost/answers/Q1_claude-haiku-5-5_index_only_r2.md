**Short answer:** a failed send is not retried automatically. The post is kept locally and marked failed, and the user has to tap it to retry.

**What happens on failure**

- `createPost` in `app/actions/remote/post.ts:74` saves the post locally first with a pending ID, then calls `client.createPost`.
- If that call throws, the code builds an error copy of the post with `props.failed: true` and writes it to the database. The post stays visible in the channel in its failed state.
- Three server errors are the exception: `DELETED_ROOT_POST_ERROR`, `TOWN_SQUARE_READ_ONLY_ERROR`, and `PLUGIN_DISMISSED_POST_ERROR`. For these the post is removed instead of kept as failed.
- A `BOR_DENIED_BY_POLICY_ERROR` also expires the cached render-permission entry for that channel.

**How many automatic retries: zero**

- `ClientPosts.createPost` (`app/client/rest/posts.ts:46`) sends `noRetry: true`.
- `buildRequestOptions` (`app/client/rest/tracking.ts:378`) turns that into `retryPolicyConfiguration = {retryLimit: 0}`, so the transport layer makes exactly one attempt.
- I found no other retry loop for new posts in the index.
- `POST_TIME_TO_FAIL` (10 s, `app/constants/post.ts:57`) is a separate UI timer. `isPostFailed` in `app/utils/post/index.ts` treats a still-pending post older than that as failed, even without an error response. It does not resend anything.

**What retrying does**

- The user taps the failed post, which opens a bottom sheet (`app/components/post_list/post/body/failed/index.tsx`). "Try Again" calls `retryFailedPost(serverUrl, post)`. "Delete Message" removes the post.
- `retryFailedPost` (`app/actions/remote/post.ts:228`) does the following:
  1. Clears `props.failed` and sets fresh `create_at`/`update_at` timestamps, so the post shows as pending again.
  2. Calls `client.createPost` once more, with the same single-attempt policy.
  3. On success, writes the server-returned post and updates the channel's last-post time.
  4. On failure, marks the post failed again, or removes it for the same three server errors above.
- Each tap is one attempt. Nothing re-sends in the background.