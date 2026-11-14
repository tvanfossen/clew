**Short answer:** a failed send is kept locally and marked failed, the app makes no automatic app-level retry, and the only automatic retry is the native HTTP layer's retry policy of up to 3 retries. "Try Again" re-runs the whole send as a new attempt.

**1. The first failure (`createPost`, `app/actions/remote/post.ts:74-226`)**

- The post is written to the local database before the network call, with a `pendingPostId` as its id.
- `client.createPost` is called once inside a try/catch (line 155). The catch is the only handler; nothing in `createPost` loops or reschedules.
- If the server error is `DELETED_ROOT_POST_ERROR`, `TOWN_SQUARE_READ_ONLY_ERROR` or `PLUGIN_DISMISSED_POST_ERROR`, the post is removed (line 181).
- Any other failure sets `props.failed = true` (line 169) and saves the post locally (lines 183-195). It stays in the channel as a failed post. `BOR_DENIED_BY_POLICY_ERROR` also expires the render-permissions entry (line 161).
- The function returns `{data: true}` even on failure, so callers do not see the error.

**2. Automatic retries**

- The app code does not retry. The `NetworkManager` default config sets `retryPolicyConfiguration` to `EXPONENTIAL_RETRY`, `retryLimit: 3`, base 2, scale 0.5 (`app/managers/network_manager.ts:68-73`). That is up to 3 retries inside the native network client, with exponential backoff, before the request fails back to `createPost`.
- I did not check whether the native library applies this policy to POST requests, or which status codes it retries. That lives in the library, not this repo.
- Tracking requests override this to `retryLimit: 0` (`app/client/rest/tracking.ts:384`). Nothing in the post send path does.

**3. "Try Again" (`retryFailedPost`, `app/actions/remote/post.ts:228-307`)**

- The button is in `app/components/post_list/post/body/failed/index.tsx:48` and calls `retryFailedPost(serverUrl, post)`.
- It sets `failed: false` and a fresh timestamp, and keeps the same local record, so the UI shows the post as pending again.
- It then calls `client.createPost` again. On success it writes the server post and updates the last-post time for the channel. The local record is updated with the server result but keeps the same local id.
- On failure, the same error handling applies: the three "removal" errors delete the post, and everything else sets `failed: true` again. The user can press "Try Again" again.

So the path is: one app-level attempt, then up to 3 native retries if the policy applies, then a persisted failed post. Each "Try Again" starts a new attempt in the same way, and the user, not the app, decides when to retry.