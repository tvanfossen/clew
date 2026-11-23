**Short answer:** a failed send is never retried automatically. The post is kept locally, marked failed, and the user retries it by hand. The index shows one HTTP attempt per send, with no retry loop anywhere in the send path.

**What happens when `createPost` fails** (`app/actions/remote/post.ts:74`)

1. Before the network call, the post is already written to the local database under a pending ID (`${currentUserId}:${timestamp}`), so it shows in the UI as pending.
2. The request goes through `client.createPost`, which calls `doFetch` with `noRetry: true` (`app/client/rest/posts.ts:43`).
3. `buildRequestOptions` turns `noRetry` into `retryPolicyConfiguration = {retryLimit: 0}` (`app/client/rest/tracking.ts:378`). So the network layer makes no retries either.
4. On error, the code logs the failure and normally rewrites the local post with `props.failed = true`. The post stays in the database and the user sees it as failed.
5. Three server errors are exceptions: `DELETED_ROOT_POST_ERROR`, `TOWN_SQUARE_READ_ONLY_ERROR` and `PLUGIN_DISMISSED_POST_ERROR`. For these the post is removed instead of kept as failed. A `BOR_DENIED_BY_POLICY_ERROR` also expires the cached render-permission entry for the channel.

**Retry count:** the automatic count is zero. There is one attempt, and the transport is told not to retry.

**What retrying does** (`retryFailedPost`, `app/actions/remote/post.ts:228`)

- It is triggered from the failed-post indicator (`app/components/post_list/post/body/failed/index.tsx`, `Failed.onPress`).
- It rebuilds the API post from the stored model, sets `props.failed = false`, and gives it a new `create_at`/`update_at` timestamp. It then writes that to the local record so the UI shows it as pending again.
- It calls `client.createPost` once more. On success it stores the server's post and updates the channel's last-post time. On failure it sets `failed = true` again, or removes the post for the three error IDs above.
- It makes no further attempts after that single retry, so a second failure just leaves the post marked failed for another manual retry.

**Things I could not confirm from the index:**

- The source comment in `retryFailedPost` says the original `create_at` is kept, but the code sets `create_at: timestamp`. The code is what runs, so treat the comment as stale.
- I did not read the body of `Failed.onPress`. The caller graph shows it reaches `retryFailedPost`, which is enough to answer the question.
- I did not check how the server response replaces the pending local record on success. The handler uses `created.id` and the pending ID is not reused explicitly in these functions.