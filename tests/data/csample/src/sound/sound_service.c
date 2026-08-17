/** @participant Sound Service */

#include "sound_service.h"

#include <stdio.h>

/**
 * @brief Play the find-me locating chime.
 * @version 1.0
 * @req REQ-0621
 * @param mode Sound mode; SOUND_FINDME plays the chime, others are ignored.
 */
void sound_play_findme(uint8_t mode)
{
    if (mode == SOUND_FINDME) {
        printf("sound: find-me chime!\n");
    }
}
