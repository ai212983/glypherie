/* FreeType 2.15.0 standalone adapter.  Geometry is validated by mono.rs.
 * Per-call raster state and caller-owned scratch keep concurrent calls separate.
 */
#define STANDALONE_
#include "ftraster.c"

typedef struct { void *buffer; size_t size; } FontMonoArena;

static void *arena_alloc(FT_Memory memory, long size) {
  FontMonoArena *arena = (FontMonoArena *)memory->user;
  return size > 0 && (size_t)size <= arena->size ? arena->buffer : NULL;
}
static void arena_free(FT_Memory memory, void *block) {
  (void)memory; (void)block;
}

/* Same pool estimate as ft_black_render, rounded to pointer-sized words. */
size_t font_mono_scratch_words(unsigned int width, unsigned int height) {
  size_t count = ((size_t)width + height - 2) * 8 +
                 80 * sizeof(TProfile) / sizeof(Long);
  if (count <= FT_MAX_BLACK_POOL) return 0;
  return (count * sizeof(Long) + sizeof(size_t) - 1) / sizeof(size_t);
}

int font_mono_render(FT_Vector *points, unsigned char *tags,
                     unsigned short *ends, unsigned short point_count,
                     unsigned short contour_count, unsigned int width,
                     unsigned int height, unsigned char *buffer,
                     void *scratch, size_t scratch_bytes, int outline_flags) {
  FontMonoArena arena = {scratch, scratch_bytes};
  FT_MemoryRec memory = {&arena, arena_alloc, arena_free, NULL};
  black_TRaster raster = {&memory};
  FT_Outline outline = {contour_count, point_count, points, tags, ends,
                        outline_flags};
  FT_Bitmap bitmap = {0};
  FT_Raster_Params params = {0};
  bitmap.rows = height;
  bitmap.width = width;
  bitmap.pitch = (int)((width + 7) / 8);
  bitmap.buffer = buffer;
  bitmap.pixel_mode = FT_PIXEL_MODE_MONO;
  params.source = &outline;
  params.target = &bitmap;
  return ft_black_render((FT_Raster)&raster, &params);
}
