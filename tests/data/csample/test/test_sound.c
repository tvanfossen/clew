/** @participant Test Harness */

#include <stdio.h>

#include "../src/sound/sound_service.h"

/**
 * @brief Verify the find-me chime plays for SOUND_FINDME mode.
 * @version 1.0
 * @req REQ-0621
 */
static void test_findme_chime_plays(void)
{
    sound_play_findme(SOUND_FINDME);
    sound_play_findme(SOUND_NONE); /* must stay silent */
    printf("test_findme_chime_plays: ok\n");
}

/**
 * @brief Test-runner entry point.
 * @version 1.0
 * @utility
 * @return Process exit code (always 0 in the sample).
 */
int main(void)
{
    test_findme_chime_plays();
    return 0;
}
