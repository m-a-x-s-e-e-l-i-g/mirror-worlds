# EOS M RAW edge coverage

The owner supplied `IMG_9987.CR2` after confirming dev11 capture. Its SHA256 is `7a50c2877153ce428ad2890072c63e81bd8ff916a1bc19c2734e251beeed5e01`. The card's module matches dev11's SHA256. The source photo is read only and is not redistributed in the candidate.

The embedded JPEG has no thin original-image border. Rendering the full decoder-visible RAW exposes an unmirrored strip. These are distinct rectangles in the same 5280x3528 RAW frame:

| Area | Left | Top | Width | Height | Right/bottom excluded |
|---|---:|---:|---:|---:|---|
| Canon default JPEG crop | 84 | 64 | 5184 | 3456 | 5268, 3520 |
| LibRaw visible RAW | 72 | 52 | 5208 | 3476 | 5280, 3528 |

The Canon MakerNote SensorInfo in the actual file specifies inclusive image borders of 84, 64, 5267, 3519. `rawpy` reports the matching default crop separately from its larger visible RAW area. The latter agrees with [LibRaw's EOS M geometry table](https://github.com/LibRaw/LibRaw/blob/master/src/metadata/identify.cpp), which uses a 72-column and 52-row offset for the 5280x3528 sensor buffer. [ExifTool's Canon SensorInfo documentation](https://exiftool.org/TagNames/Canon.html#SensorInfo) defines the MakerNote border fields.

Dev11 and dev12 used the JPEG crop as the transform rectangle. This left visible strips of 12 pixels at the top, 12 at the left, 8 at the bottom and 12 at the right untouched in RAW converters. The image itself confirms Top/Bottom with Third: 5,961,600 top samples and 5,961,600 bottom samples exactly equal rounded same-phase interpolation from the unchanged center. This comparison excludes seam-neighbor rows that no longer retain their original source values. It has zero mismatches and does not infer the result from saved preferences alone.

Dev13 changes the EOS M transform rectangle to `[52,72,3528,5280]` (top, left, bottom, right excluded). Its buffer bounds, sensor origin, pitch, stage hooks, readout checks and private workspace are unchanged. Pixels above row 52 and left of column 72 remain outside processing. Fold sizes are calculated from the larger visible rectangle, moving nominal fold positions by a few pixels relative to the JPEG crop. The saved file's metadata and Canon crop are not rewritten.

`tests/camera_portability.c` now checks the output rectangle against the independently observed decoder geometry. Compiling that regression against the archived dev12 backend fails at the `decoded_region` assertion. The same capture suite verifies all 44 full-size layouts, every packed pixel against an independent interpolation reference, unchanged data outside the new rectangle, capture refusal and cancellation. This fixes an omitted coverage requirement in the earlier tests, which accepted the backend's smaller rectangle as their boundary.

Local receipts live under `.cache/photo-feedback/IMG_9987/` and `.cache/dev13-before-raw-bounds.log`. They are diagnostic evidence, not proof of a new camera capture. Retest a fresh dev13 CR2 in the same RAW converter, particularly Top/Bottom with Third and All edges, checking the entire visible image. Existing CR2 files are unchanged.
