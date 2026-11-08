**Short answer:** a failed post stays in the local database, flagged as failed. It is never retried automatically: the send makes one attempt. The user retries by hand from the failed-post menu, and that retry is also a single attempt.

**What happens on the first failure** (`createPost` in `app/actions/remote/post.ts:74`)

- Before the network call, the post is written locally with `id = pending_post_id` (`${currentUserId}:${timestamp}`), so the user sees it immediately.
- `client.createPost` is called once. `ClientPosts.createPost` in `app/client/rest/posts.ts:43` passes `noRetry: true`, and `app/client/rest/tracking.ts:383` maps that to `retryPolicyConfiguration = {retryLimit: 0}`. So there is no transport-level retry either.
- On error, the post is stored with `props.failed = true` and an updated `update_at`. It shows the error icon (`app/components/post_list/post/body/failed/index.tsx`, `testID='post.failed.button'`).
- Three server errors are exceptions: `DELETED_ROOT_POST_ERROR`, `TOWN_SQUARE_READ_ONLY_ERROR` and `PLUGIN_DISMISSED_POST_ERROR`. For these the post is removed locally rather than marked failed.
- `BOR_DENIED_BY_POLICY_ERROR` also expires the cached render-permission entry for the channel, but the post is still marked failed.
- The function returns `{data: true}` even on failure, so the caller does not treat a failed send as an error.

**What retrying does** (`retryFailedPost` in `app/actions/remote/post.ts:228`)

The user taps the failed icon, then "Try Again" (`post.failed.retry`) in the bottom sheet. `retryFailedPost` then:

1. Rebuilds the post from the stored model with `failed: false`, `id: ''` and fresh `create_at`/`update_at` timestamps. It keeps the original `pending_post_id`.
2. Writes the pending state back to the local record, so the UI shows it as sending again.
3. Calls `client.createPost` once.
4. On success, stores the server post, updates the channel's last-post time (unless it is a CRT reply), and saves the result.
5. On failure, applies the same error handling as the first attempt: removal for the three errors above, otherwise `failed: true` again.

**Things to be aware of**

- The retry does not go through `createPost`'s pre-steps. It does not re-run recent-reaction handling, and it does not re-attach files; it reuses the `file_ids` carried by `toApi()`.
- The comment in `retryFailedPost` says `createAt` stays the same as the first attempt, but the code sets `create_at: timestamp` on the request. The local record keeps its original `create_at`, so the server and local timestamps differ. I did not trace how the server-side record is reconciled with the pending local one, so I have not verified how the pending placeholder is replaced on success.