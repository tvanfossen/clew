**Short answer:** a failed post stays in the local database, flagged as failed. It is not retried automatically: the send is made with retries explicitly disabled. The user retries it by hand from the post's failure menu, and that retry sends a fresh request.

**What happens on failure** (`app/actions/remote/post.ts:74-226`, `createPost`)

1. Before the network call, the post is already written locally with a `pending_post_id` and an id of `${userId}:${timestamp}`, so it shows in the list immediately.
2. The request is `client.createPost(...)`. If it throws, the code logs it and builds an error copy of the post with `props.failed = true`.
3. Most errors keep the post. It is saved with `failed: true`, and it is also added to the thread when CRT is on.
4. Three server errors remove the post from the database instead: `DELETED_ROOT_POST_ERROR`, `TOWN_SQUARE_READ_ONLY_ERROR`, and `PLUGIN_DISMISSED_POST_ERROR` (lines 176-181). A burn-on-read refusal also expires the cached render-permission entry, but the post is still kept as failed.
5. Independently of that flag, a post still pending more than 10 seconds after `updateAt` (`POST_TIME_TO_FAIL`, `app/constants/post.ts:57`) counts as failed in the UI (`app/utils/post/index.ts:98`, timer in `app/components/post_list/post/post.tsx:274`).

**How many automatic retries: zero**

The app's HTTP client is configured with exponential retry and a limit of 3 (`app/managers/network_manager.ts:68-73`). But `createPost` in `app/client/rest/posts.ts:43-47` passes `noRetry: true`, and `buildRequestOptions` turns that into `retryPolicyConfiguration: {retryLimit: 0}` (`app/client/rest/tracking.ts:383-385`). So a failed send is attempted once. The `handle_send_message` hook fires `createPost` and does not re-invoke it on error.

**What retrying does** (`retryFailedPost`, `app/actions/remote/post.ts:228-307`)

The user taps the failed icon, then "Try Again" in the bottom sheet (`app/components/post_list/post/body/failed/index.tsx:46-49`). That calls `retryFailedPost`, which:

- Clears `failed` and resets `create_at` and `update_at` to now. The post moves to the bottom and the UI shows it as pending again.
- Sends the post once more, again with no automatic retries.
- On success, writes the server's post in place of the local copy.
- On failure, applies the same rule as before: removes the post for the three errors above, otherwise marks it failed again. Every error is handled this way, including local database errors.

Attachments are not re-uploaded. The retry sends the stored post object, and `createPost`'s duplicate guard (`existing && !existing.props?.failed`) is bypassed.

I did not run the app or the tests; this is from reading the code. A tool hook also suggested a `dossier` lookup for these files. I did not use it.