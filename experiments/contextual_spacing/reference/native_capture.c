/* Native FontForge reference driver, not an implementation of its estimator.
 * This compilation unit includes the unmodified pinned upstream source, whose
 * original copyright/license notice remains in that file and built source tree.
 * Build only with build-native.py at the recorded upstream revision.
 * Input: EM SUBDIVISIONS GLYPH_COUNT, then COMMAND_COUNT and M/L/Q/C/Z commands
 * for each glyph, in design units. Contours must be explicitly closed.
 */
#include "autowidth2.c"
#include "splineorder2.h"
#include <stdio.h>

static void bad(const char *reason) {
    fprintf(stderr, "native_capture: %s\n", reason);
    exit(2);
}

static double coordinate(void) {
    double value;
    if (scanf("%lf", &value) != 1 || !isfinite(value) || fabs(value) > 30000)
        bad("invalid/nonfinite/out-of-range coordinate");
    return value;
}

static SplineSet *read_contours(void) {
    int count;
    if (scanf("%d", &count) != 1 || count < 0 || count > 10000)
        bad("invalid command count");
    SplineSet *head = NULL, *tail = NULL, *current = NULL;
    SplinePoint *last = NULL;
    for (int i = 0; i < count; ++i) {
        char op;
        if (scanf(" %c", &op) != 1) bad("missing command");
        if (op == 'M') {
            if (current != NULL) bad("unclosed contour");
            current = calloc(1, sizeof(SplineSet));
            double x = coordinate(), y = coordinate();
            last = current->first = current->last = SplinePointCreate(x, y);
            if (tail != NULL) tail->next = current;
            else head = current;
            tail = current;
        } else if (op == 'Z') {
            if (current == NULL) bad("close without contour");
            if (last != current->first) SplineMake3(last, current->first);
            current->last = current->first;
            current = NULL;
            last = NULL;
        } else {
            if (current == NULL) bad("segment without contour");
            double x1 = 0, y1 = 0, x2 = 0, y2 = 0;
            if (op == 'Q' || op == 'C') {
                x1 = coordinate(); y1 = coordinate();
            }
            if (op == 'C') {
                x2 = coordinate(); y2 = coordinate();
            }
            if (op != 'L' && op != 'Q' && op != 'C') bad("unknown command");
            double x = coordinate(), y = coordinate();
            SplinePoint *next = SplinePointCreate(x, y);
            if (op == 'Q' || op == 'C') {
                last->nextcp.x = x1; last->nextcp.y = y1;
                next->prevcp.x = op == 'Q' ? x1 : x2;
                next->prevcp.y = op == 'Q' ? y1 : y2;
                last->nonextcp = next->noprevcp = false;
            }
            if (op == 'Q') SplineMake2(last, next);
            else SplineMake3(last, next);
            last = current->last = next;
        }
    }
    if (current != NULL) bad("unclosed contour at end");
    return head;
}

int main(void) {
    int em, subdivisions, count;
    if (scanf("%d %d %d", &em, &subdivisions, &count) != 3 ||
        em < 1 || em > 30000 || subdivisions < 1 || em / subdivisions < 1 ||
        count < 1 || count > 256) bad("invalid em/subdivisions/glyph count");
    AW_Data all = {0};
    all.layer = 1;
    all.sub_height = em / subdivisions;
    all.denom = em / DENOM_FACTOR_OF_EMSIZE;
    AW_Glyph *glyphs = calloc(count, sizeof(AW_Glyph));
    printf("{\"schema_version\":\"fontforge-native-envelope-v1\",\"em_size\":%d,"
        "\"subdivisions\":%d,\"band_height\":%d,\"glyphs\":[", em, subdivisions, all.sub_height);
    for (int i = 0; i < count; ++i) {
        AW_Glyph *glyph = &glyphs[i];
        glyph->sc = calloc(1, sizeof(SplineChar));
        glyph->sc->layer_cnt = 2;
        glyph->sc->layers = calloc(2, sizeof(Layer));
        glyph->sc->layers[1].splines = read_contours();
        SplineCharLayerFindBounds(glyph->sc, all.layer, &glyph->bb);
        if ((glyph->bb.maxy - glyph->bb.miny) / all.sub_height > 20000)
            bad("band budget exceeded");
        aw2_findedges(glyph, &all);
        printf("%s{\"bounds\":{\"minx\":%.17g,\"miny\":%.17g,\"maxx\":%.17g,\"maxy\":%.17g},"
            "\"imin_y\":%d,\"imax_y\":%d,\"bands\":[", i ? "," : "",
            glyph->bb.minx, glyph->bb.miny, glyph->bb.maxx, glyph->bb.maxy, glyph->imin_y, glyph->imax_y);
        for (int band = glyph->imin_y; band <= glyph->imax_y; ++band) {
            int offset = band - glyph->imin_y;
            printf("%s{\"index\":%d,\"left\":%d,\"right\":%d}", offset ? "," : "",
                band, glyph->left[offset], glyph->right[offset]);
        }
        printf("]}");
    }
    printf("],\"pair_estimates\":[");
    for (int left = 0; left < count; ++left) {
        printf("%s[", left ? "," : "");
        for (int right = 0; right < count; ++right)
            printf("%s%d", right ? "," : "", aw2_bbox_separation(&glyphs[left], &glyphs[right], &all));
        printf("]");
    }
    printf("]}\n");
    for (int i = 0; i < count; ++i) {
        SplinePointListFree(glyphs[i].sc->layers[1].splines);
        free(glyphs[i].sc->layers);
        free(glyphs[i].sc);
        free(glyphs[i].left); free(glyphs[i].right);
    }
    free(glyphs);
    return 0;
}
