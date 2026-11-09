/* Copyright (C) 2009-2012 by George Williams */
/*
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:

 * Redistributions of source code must retain the above copyright notice, this
 * list of conditions and the following disclaimer.

 * Redistributions in binary form must reproduce the above copyright notice,
 * this list of conditions and the following disclaimer in the documentation
 * and/or other materials provided with the distribution.

 * The name of the author may not be used to endorse or promote products
 * derived from this software without specific prior written permission.

 * THIS SOFTWARE IS PROVIDED BY THE AUTHOR ``AS IS'' AND ANY EXPRESS OR IMPLIED
 * WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF
 * MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO
 * EVENT SHALL THE AUTHOR BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
 * SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
 * PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS;
 * OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
 * WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR
 * OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
 * ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */

/* Standalone test harness. The function below is copied without modification
 * from the pinned FontForge source. This validates weighting, not native
 * FontForge spline-to-envelope construction. Build: cc -std=c99 FILE -lm.
 */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#define _NO_PYTHON

typedef double real;
typedef struct { int imin_y, imax_y; short *left, *right; } AW_Glyph;
typedef struct { real denom; } AW_Data;

static int aw2_bbox_separation(AW_Glyph *g1, AW_Glyph *g2, AW_Data *all) {
    int j;
    int imin_y, imax_y;
    real tot, cnt;
    real denom;
    /* the goal is to give a weighted average that expresses the visual */
    /*  separation between two glyphs when they are placed so their bounding */
    /*  boxes are adjacent. The separation between two rectangles would be 0 */
    /*  While the separation between "T" and "o" would be fairly large */
    /* The trick is to guess a good weighting function. My guess is that */
    /*  things that look close are more important than those which look far */
    /*  So "T" and "O" should be dominated by the crossbar of the "T"... */
#if !defined(_NO_PYTHON)

    if ( PyFF_GlyphSeparationHook!=NULL )
return( PyFF_GlyphSeparation(g1,g2,all) );
#endif

    imin_y = g2->imin_y > g1->imin_y ? g2->imin_y : g1->imin_y;
    imax_y = g2->imax_y < g1->imax_y ? g2->imax_y : g1->imax_y;
    if ( imax_y < imin_y )		/* no overlap. ie grave and "a" */
return( 0 );
    denom = all->denom;
    tot = cnt = 0;
    for ( j=imin_y ; j<imax_y; ++j ) {
	if ( g2->left[j-g2->imin_y] < 32767 && g1->right[j-g1->imin_y] > -32767 ) {
	    /* beware of gaps such as those in "i" or "aaccute" */
	    real sep = g2->left[j-g2->imin_y] - g1->right[j-g1->imin_y];
	    real weight = 1.0/(sep + denom);
	    weight *= weight;

	    tot += weight*sep;
	    cnt += weight;
	}
    }
    if ( cnt!=0 )
	tot /= cnt;
return( rint( tot ) );
}


int main(void) {
    AW_Glyph a, b;
    AW_Data all;
    if (scanf("%d %d %d %d %lf", &a.imin_y, &a.imax_y,
              &b.imin_y, &b.imax_y, &all.denom) != 5) return 2;
    int na = a.imax_y-a.imin_y+1, nb = b.imax_y-b.imin_y+1;
    if (na < 0 || nb < 0 || na > 20000 || nb > 20000) return 2;
    a.left = calloc(na ? na : 1, sizeof(short));
    a.right = calloc(na ? na : 1, sizeof(short));
    b.left = calloc(nb ? nb : 1, sizeof(short));
    b.right = calloc(nb ? nb : 1, sizeof(short));
    if (!a.left || !a.right || !b.left || !b.right) return 2;
    for (int i=0; i<na; ++i)
        if (scanf("%hd %hd", &a.left[i], &a.right[i]) != 2) return 2;
    for (int i=0; i<nb; ++i)
        if (scanf("%hd %hd", &b.left[i], &b.right[i]) != 2) return 2;
    printf("%d\n", aw2_bbox_separation(&a, &b, &all));
    free(a.left); free(a.right); free(b.left); free(b.right);
    return 0;
}
