MODULE_NAME = mirror
MODULE_OBJS = $(BUILD_DIR)/mirror.o $(BUILD_DIR)/mirror_camera.o $(BUILD_DIR)/mirror_driver.o $(BUILD_DIR)/mirror_settings.o $(BUILD_DIR)/mirror_raw_trace.o $(BUILD_DIR)/mirror_capture_gate.o $(BUILD_DIR)/fx_camera.o $(BUILD_DIR)/fx_mirror.o $(BUILD_DIR)/fx_mirror_raw.o $(BUILD_DIR)/fx_mirror_sensor.o $(BUILD_DIR)/fx_mirror_registered.o $(BUILD_DIR)/fx_pixels.o $(BUILD_DIR)/gl_format.o $(BUILD_DIR)/gl_review.o
MODULE_CFLAGS += -Ishared -Iengine -include shared/fx_namespace.h -DFX_PREFIX=mirror -DMIRROR_RELEASE
ifeq ($(MIRROR_PREVIEW_ONLY),1)
MODULE_OBJS := $(filter-out $(BUILD_DIR)/mirror_raw_trace.o $(BUILD_DIR)/mirror_capture_gate.o,$(MODULE_OBJS)) $(BUILD_DIR)/mirror_native_disabled.o
MODULE_CFLAGS += -DMIRROR_PREVIEW_ONLY
endif
ifeq ($(MIRROR_70D_RESEARCH),1)
MODULE_CFLAGS += -DMIRROR_70D_RESEARCH
endif
TOP_DIR = ../..
include $(TOP_DIR)/modules/Makefile
.DEFAULT_GOAL := $(BUILD_DIR)/module_complete
# Preserve the same linked object before stripping for per-core DWARF audits.
$(BUILD_DIR)/mirror.debug.o: $(MODULE_OBJS) | $(BUILD_DIR)
	$(LD) -r -o $@ $(MODULE_OBJS)
$(BUILD_DIR)/fx_camera.o: shared/fx_camera.c | $(BUILD_DIR)
	$(CC) $(CFLAGS) $(CDEPS_FLAGS) -c -o $@ $<
$(BUILD_DIR)/fx_pixels.o: shared/fx_pixels.c | $(BUILD_DIR)
	$(CC) $(CFLAGS) -O2 $(CDEPS_FLAGS) -c -o $@ $<
$(BUILD_DIR)/gl_format.o: engine/gl_format.c | $(BUILD_DIR)
	$(CC) $(CFLAGS) $(CDEPS_FLAGS) -c -o $@ $<
$(BUILD_DIR)/gl_review.o: engine/gl_review.c | $(BUILD_DIR)
	$(CC) $(CFLAGS) -O2 $(CDEPS_FLAGS) -c -o $@ $<

$(BUILD_DIR)/fx_mirror.o: shared/fx_mirror.c | $(BUILD_DIR)
	$(CC) $(CFLAGS) -O2 $(CDEPS_FLAGS) -c -o $@ $<
$(BUILD_DIR)/fx_mirror_raw.o: shared/fx_mirror_raw.c | $(BUILD_DIR)
	$(CC) $(CFLAGS) -O2 $(CDEPS_FLAGS) -c -o $@ $<
$(BUILD_DIR)/fx_mirror_sensor.o: shared/fx_mirror_sensor.c | $(BUILD_DIR)
	$(CC) $(CFLAGS) -O2 -DFX_SENSOR_AXIAL_ONLY $(CDEPS_FLAGS) -c -o $@ $<
$(BUILD_DIR)/fx_mirror_registered.o: shared/fx_mirror_registered.c | $(BUILD_DIR)
	$(CC) $(CFLAGS) -O2 $(CDEPS_FLAGS) -c -o $@ $<
