**Short answer:** a failed post is kept locally and marked failed, it is never retried automatically, and retrying it is a manual user action that re-sends the same post under the same pending ID.

**What happens on failure** (`app/actions/remote/post.ts`, `createPost`, around lines 150–225):

- The post is written to the local database first, so it shows in the timeline before the server responds.
- If `client.createPost` throws, the catch block logs the error and saves the post with `props.failed = true`, so the UI shows it as failed.
- Two server errors are exceptions: `DELETED_ROOT_POST_ERROR`, `TOWN_SQUARE_READ_ONLY_ERROR` and `PLUGIN_DISMISSED_POST_ERROR` cause the post to be removed instead of kept as failed.
- If the error is `BOR_DENIED_BY_POLICY_ERROR`, the cached render-permission entry for the channel is also expired.

**How many automatic retries: zero.** The client has a default of 3 exponential-backoff retries (`app/managers/network_manager.ts`, lines 68–71). But `app/client/rest/posts.ts` (line 46) sends `createPost` with `noRetry: true`, and `app/client/rest/tracking.ts` (lines 383–384) turns that into `retryPolicyConfiguration: {retryLimit: 0}`. The `noRetry` flag is there so a request that reached the server is not sent twice and duplicated. The code does not state that reason, so treat it as the likely intent.

**What retrying does** (`retryFailedPost`, `app/actions/remote/post.ts`, around lines 228–305):

- It is called only from the failed-post component (`app/components/post_list/post/body/failed/index.tsx`, line 48), so it runs when the user taps the failed indicator.
- It clears `failed`, sets new create and update timestamps, and writes that to the DB so the post shows as pending again.
- It calls `client.createPost` again with a new request. Its `id` is empty and the server assigns a new one. The local record is then replaced with the server's post on success.
- On failure it sets `failed` back to true, or removes the post for the same three server errors listed above.