/* Actual module callbacks, with all unrelated sections discarded at link. */
#include <assert.h>
#include <string.h>
#include "mirror_ui_sdk.h"
#include "fx_camera.h"
#include "mirror_camera.h"
#include "mirror_capture_gate.h"
#include "../modules/mirror/mirror.c"
static unsigned presses,releases,full,forwarded,half_state;
void mirror_gate_half_press(unsigned down){if(down)presses++;else releases++;}
void mirror_gate_full_press(void){full++;}
void fx_half(int down){half_state=down!=0;}
int fx_key(unsigned value){forwarded=value;return 1;}
const mirror_native_backend *mirror_camera_native(void){static mirror_native_backend backend;return &backend;}
int main(void)
{
    assert(key(MODULE_KEY_PRESS_HALFSHUTTER)==1&&presses==1&&full==0&&forwarded==MODULE_KEY_PRESS_HALFSHUTTER);
    unsigned data=1;ui_property_PROP_HALF_SHUTTER(&data,2);assert(presses==2&&half_state);
    data=0;ui_property_PROP_HALF_SHUTTER(&data,2);assert(releases==1&&!half_state);
    ui_property_PROP_HALF_SHUTTER(NULL,2);ui_property_PROP_HALF_SHUTTER(&data,0);assert(releases==1);
    assert(key(MODULE_KEY_PRESS_FULLSHUTTER)==1&&full==1&&forwarded==MODULE_KEY_PRESS_FULLSHUTTER);
    assert(key(MODULE_KEY_PRESS_SET)==1&&full==1&&presses==2&&forwarded==MODULE_KEY_PRESS_SET);
    puts("Shutter callback dispatch: half-key/property press/release, full-key passthrough and Canon SET: PASS");
    return 0;
}
