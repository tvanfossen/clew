**Short answer:** a failed new post stays in the local database, marked as failed, and is not retried automatically. Retry is manual, from the user's "Try Again" action.

**What happens on failure** (`createPost`, `app/actions/remote/post.ts:74-226`):

1. Before the network call, the post is written locally with a temporary `pending_post_id` and is shown in the UI as pending.
2. The server call is `client.createPost(...)`. If it throws, the code logs the error and builds an error copy of the post with `props.failed = true`.
3. Most errors leave that failed post in the database. Three server errors are different: `DELETED_ROOT_POST_ERROR`, `TOWN_SQUARE_READ_ONLY_ERROR` and `PLUGIN_DISMISSED_POST_ERROR`. For those the post is removed instead of kept as failed. A `BOR_DENIED_BY_POLICY_ERROR` also expires the cached render-permission entry for the channel, and the post is still kept as failed.

**How many automatic retries:** none. I found one attempt per send.
- `ClientPosts.createPost` (`app/client/rest/posts.ts:43-48`) calls `doFetch` with `noRetry: true`. That is the only retry-related setting on the send path.
- I did not read `doFetch`'s body, so I can't say exactly how `noRetry` is handled there. The name strongly suggests it turns off the client's transport-level retry, but that is an inference from the flag name.
- Nothing in the send path loops or reschedules.

**What retrying does** (`retryFailedPost`, `app/actions/remote/post.ts:228-307`):

- It is triggered only from the failed-post bottom sheet, where the user taps "Try Again" (`post.failed.retry`, `app/components/post_list/post/body/failed/index.tsx:38-65`). Tapping "Delete Message" calls `removePost` instead.
- It rebuilds the post with a new timestamp and `failed: false`, updates the local record so the UI shows it as pending again, and then calls `client.createPost` once more.
- On success it stores the server's post in place of the local one and updates the channel's last-post time (unless it is a CRT reply).
- On failure it sets `failed: true` again, or removes the post if the error is one of the three terminal errors above. Each tap is one more attempt; nothing repeats on its own.