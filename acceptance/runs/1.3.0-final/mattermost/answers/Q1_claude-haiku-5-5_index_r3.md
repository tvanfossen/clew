**Short answer:** a failed post stays in the local database, flagged `failed: true`, and the user can tap it to retry. There is no automatic retry, so the send happens once. Retrying does not resend the same record. It re-creates the post on the server under a fresh timestamp and swaps the local copy.

**1. What happens on failure** (`createPost` in `app/actions/remote/post.ts:74-226`)

- The post is written locally first as an optimistic record, with the pending ID `${currentUserId}:${timestamp}`.
- `client.createPost` is called. If it throws, the catch block (`post.ts:156-199`) runs.
- Most errors take the else branch. The post is saved with `props.failed = true` and kept in the local database, so it still shows in the channel with the failed indicator.
- Three server errors take a different path: `DELETED_ROOT_POST_ERROR`, `TOWN_SQUARE_READ_ONLY_ERROR` and `PLUGIN_DISMISSED_POST_ERROR`. For these, the post is removed outright (`removePost`) rather than kept as failed.
- A `BOR_DENIED_BY_POLICY_ERROR` also expires the cached burn-on-read render permission for that channel, but the post is still marked failed.

**2. Automatic retries: none**

- `ClientPosts.createPost` (`app/client/rest/posts.ts:43-48`) passes `noRetry: true`.
- `buildRequestOptions` (`app/client/rest/tracking.ts:383-385`) turns that into `retryPolicyConfiguration = {retryLimit: 0}`.
- So the network layer makes exactly one attempt. The count is zero automatic retries. The only retry is the user's.

I did not find a background job or reconnect hook that re-sends `failed` posts. The `POST_TIME_TO_FAIL` constant (10 s, `app/constants/post.ts:57`) is defined, but I did not trace where it is used, so I can't say whether it drives a timeout-to-failed transition.

**3. What "retry" does** (`retryFailedPost`, `post.ts:228-307`)

It is triggered from the failed post's bottom sheet, "Try Again" (`app/components/post_list/post/body/failed/index.tsx:46-49`). It:

1. Rebuilds the API payload from the existing record, clears `failed`, sets `id: ''`, and sets `create_at` and `update_at` to now.
2. Writes that back locally as pending, keeping the original post ID so the UI doesn't jump.
3. Calls `client.createPost` again. This is a fresh POST, so the server assigns a new post ID.
4. On success, it upserts the returned post and updates the channel's last-post time. The local row is now the server's post, which holds the server ID, not the pending ID.
5. On failure, it sets `failed: true` again, unless the error is one of the three terminal errors above, in which case it removes the post.

**Caveat:** because `retryFailedPost` sends a new POST, a request that timed out but was committed server-side could leave a duplicate. The send path has no idempotency key that I could find.