MODULE_NAME = m70raw
MODULE_OBJS = $(BUILD_DIR)/m70raw.o $(BUILD_DIR)/fx_mirror_raw.o $(BUILD_DIR)/fx_mirror_sensor.o $(BUILD_DIR)/gl_format.o
MODULE_CFLAGS += -Ishared -Iengine -include shared/fx_namespace.h -DFX_PREFIX=m70raw -DM70_EMULATOR_RESEARCH -DFX_SENSOR_AXIAL_ONLY
TOP_DIR = ../..
include $(TOP_DIR)/modules/Makefile
.DEFAULT_GOAL := $(BUILD_DIR)/module_complete
$(BUILD_DIR)/m70raw.debug.o: $(MODULE_OBJS) | $(BUILD_DIR)
	$(LD) -r -o $@ $(MODULE_OBJS)
$(BUILD_DIR)/fx_mirror_raw.o: shared/fx_mirror_raw.c | $(BUILD_DIR)
	$(CC) $(CFLAGS) -O2 $(CDEPS_FLAGS) -c -o $@ $<
$(BUILD_DIR)/fx_mirror_sensor.o: shared/fx_mirror_sensor.c | $(BUILD_DIR)
	$(CC) $(CFLAGS) -O2 $(CDEPS_FLAGS) -c -o $@ $<
$(BUILD_DIR)/gl_format.o: engine/gl_format.c | $(BUILD_DIR)
	$(CC) $(CFLAGS) -O2 $(CDEPS_FLAGS) -c -o $@ $<
