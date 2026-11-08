**Short answer:** a failed send is not retried automatically. It is sent exactly once, and "retry" happens only when the user taps it.

**What happens on failure**

- `createPost` in `app/actions/remote/post.ts:74` saves the post locally first, with a `pending_post_id` and `props.failed` unset, so it shows up in the UI immediately.
- It then calls `client.createPost` once. The REST call sends `noRetry: true` (`app/client/rest/posts.ts:43`), which turns off the network layer's retry behaviour for this request.
- If the call throws, the post is kept and re-saved with `props.failed = true`. The post is removed instead of kept only for three server errors: deleted root post, town square read-only, and plugin-dismissed post. For a burn-on-read policy rejection, the render-permissions entry for the channel is also expired.
- A threaded reply also gets its thread record created on failure.

**Retry count**

- Automatic retries: 0.
- Manual retries: unlimited. The user taps the failed indicator (`post.failed.button`) in `app/components/post_list/post/body/failed/index.tsx`, then "Try Again" (`post.failed.retry`).

**What retrying does**

`retryFailedPost` (`app/actions/remote/post.ts:228`) works on the existing local post rather than creating a new one:

1. Reads the stored post back as an API object and resets `props.failed` to `false`.
2. Sets a fresh `create_at` and `update_at` to now. The original `create_at` is not kept, though the code comment says the timestamps should stay the same.
3. Writes the post back to the database as pending, so the UI shows it as sending again.
4. Captures the redaction epoch and calls `client.createPost` again.
5. On success, replaces the local post with the server copy and updates the channel's last-post time (not for CRT replies).
6. On failure, it sets `props.failed = true` again, or removes the post for the same three server errors.

**Caveats**

- The index has no retry constant or loop. The only automatic path I found is the failed-state check `isPostFailed` (`app/utils/post/index.ts:97`). A post that is still pending after `POST_TIME_TO_FAIL` is shown as failed, but that check does not resend it. I could not find the value of `POST_TIME_TO_FAIL` in the index, so I can't say how long that is.
- `retryFailedPost` is called from one place (the `Failed` component). I found no other caller.