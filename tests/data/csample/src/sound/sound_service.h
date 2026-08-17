#ifndef SOUND_SERVICE_H
#define SOUND_SERVICE_H

#include <stdint.h>

/* DM_KEY_DEMOBOT_UX_SOUND_EVENT values */
#define SOUND_NONE 0
#define SOUND_FINDME 1

void sound_play_findme(uint8_t mode);

#endif /* SOUND_SERVICE_H */
