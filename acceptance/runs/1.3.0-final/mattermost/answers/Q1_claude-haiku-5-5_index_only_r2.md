**Short answer:** a failed new post is kept locally, marked as failed, and the send is never retried automatically. Retrying is a manual "Try Again" action that re-sends the same post.

**What happens on failure.** `createPost` in `app/actions/remote/post.ts` (lines 74–226) writes the post locally first, with a temporary `pending_post_id`, so it appears in the UI before the network call. If `client.createPost` throws, the catch block:

- Logs the error with `logDebug`.
- If the server error is `BOR_DENIED_BY_POLICY_ERROR`, expires the cached render-permission entry for that channel.
- If the server error is `DELETED_ROOT_POST_ERROR`, `TOWN_SQUARE_READ_ONLY_ERROR` or `PLUGIN_DISMISSED_POST_ERROR`, removes the post locally.
- Otherwise, saves the post with `props.failed: true`, creates a thread for it if CRT is enabled, and returns `{data: true}` without an error.

Any other failure, including network errors, leaves the post in the database with `failed: true`.

**How many automatic retries.** None. The POST goes through `ClientPosts.createPost` in `app/client/rest/posts.ts:46`, which passes `noRetry: true`. `buildRequestOptions` in `app/client/rest/tracking.ts:378–393` turns that into `retryPolicyConfiguration = {retryLimit: 0}`. The request is sent once. I found no code that re-sends `failed` posts later, such as on reconnect or channel open, but I checked this only by searching for `props.failed` and `retry`, not by reading every path.

**What retrying does.** The failed post's UI (`app/components/post_list/post/body/failed/index.tsx`) shows an icon. Tapping it opens a bottom sheet with "Try Again" (`post.failed.retry`) and "Delete Message". "Try Again" calls `retryFailedPost` (`app/actions/remote/post.ts:228–307`), which:

1. Clears `failed` and resets `update_at` so the post shows as pending again. The original `create_at` is kept.
2. Calls `client.createPost` again. This call does not set `noRetry`, so the client's default retry policy applies to it.
3. On success, replaces the local record with the server's post, updates the channel's last-post time (unless it is a CRT reply), and saves.
4. On failure, sets `failed: true` again. The same server errors that remove a post in `createPost` also remove it here.