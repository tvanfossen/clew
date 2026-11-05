**Short answer:** the failed post is kept locally and marked failed. The send is not retried automatically, so the count is zero. Retrying is a manual user action that re-sends the same post through a separate function.

**What happens on failure**

1. `createPost` in `app/actions/remote/post.ts:74` first writes the post to the local database with a temporary `pending_post_id`, so it shows in the UI right away.
2. It calls `client.createPost(...)` (line 155). If that throws, it builds an `errorPost` with `props.failed = true` (lines 164–172) and writes it to the DB (lines 183–195). CRT thread records are also updated when CRT is enabled.
3. Two server errors are exceptions: `DELETED_ROOT_POST_ERROR`, `TOWN_SQUARE_READ_ONLY_ERROR` and `PLUGIN_DISMISSED_POST_ERROR` cause the post to be removed (line 181) rather than kept as failed.
4. `BOR_DENIED_BY_POLICY_ERROR` also expires the cached render-permission entry for the channel (line 161) before the post is handled as above.

**Automatic retries: none**

- `app/client/rest/posts.ts:46` sends the create request with `noRetry: true`.
- `app/client/rest/tracking.ts:383–384` turns that into `retryPolicyConfiguration = {retryLimit: 0}`, so the HTTP client does not retry either.
- I found no retry loop in the send path. The only retry-related code in `app/` for posts is the manual one below and file-upload retry.

**What manual retry does**

The "failed" component (`app/components/post_list/post/body/failed/index.tsx:48`) calls `retryFailedPost` (`post.ts:228`) when the user taps it. That function:

1. Clears `failed` and sets a new timestamp on the existing local post, so the UI shows it as pending again.
2. Calls `client.createPost` with the original content. This call is not `noRetry`, but the `retryLimit: 0` setting above still applies.
3. On success, replaces the local record with the server's post and updates the channel's last-post time.
4. On failure, sets `failed: true` again. The same two server errors remove the post instead.

**One caveat:** a post sent with `pending_post_id` that already exists and is not marked failed is ignored (`post.ts:93`). That stops duplicate sends of an in-flight post. Retry bypasses this check because it works on the existing record directly.