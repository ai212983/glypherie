/****************************************************************************
 *
 * ftmisc.h
 *
 *   Miscellaneous macros for stand-alone rasterizer (specification
 *   only).
 *
 * Copyright (C) 2005-2026 by
 * David Turner, Robert Wilhelm, and Werner Lemberg.
 *
 * This file is part of the FreeType project, and may only be used
 * modified and distributed under the terms of the FreeType project
 * license, LICENSE.TXT.  By continuing to use, modify, or distribute
 * this file you indicate that you have read the license and
 * understand and accept it fully.
 *
 */


  /****************************************************
   *
   * This file is *not* portable!  You have to adapt
   * its definitions to your platform.
   *
   */

#ifndef FTMISC_H_
#define FTMISC_H_


  /* memset */
#include "platform.h"

#define FT_BEGIN_HEADER
#define FT_END_HEADER

#define FT_LOCAL_DEF( x )   static x


  /* from include/freetype/fttypes.h */

  typedef unsigned char  FT_Byte;
  typedef signed int     FT_Int;
  typedef unsigned int   FT_UInt;
  typedef signed long    FT_Long;
  typedef unsigned long  FT_ULong;
  typedef signed long    FT_F26Dot6;
  typedef int            FT_Error;


#define FT_STATIC_BYTE_CAST( type, var )  (type)(FT_Byte)(var)


  /* from include/freetype/ftsystem.h */

  typedef struct FT_MemoryRec_*  FT_Memory;

  typedef void* (*FT_Alloc_Func)( FT_Memory  memory,
                                  long       size );

  typedef void (*FT_Free_Func)( FT_Memory  memory,
                                void*      block );

  typedef void* (*FT_Realloc_Func)( FT_Memory  memory,
                                    long       cur_size,
                                    long       new_size,
                                    void*      block );

  typedef struct FT_MemoryRec_
  {
    void*            user;

    FT_Alloc_Func    alloc;
    FT_Free_Func     free;
    FT_Realloc_Func  realloc;

  } FT_MemoryRec;


  /* from src/ftcalc.c */

#if ( defined _WIN32 || defined _WIN64 )

  typedef __int64  FT_Int64;

#else

#include <stdint.h>

  typedef int64_t  FT_Int64;

#endif


  static FT_Long
  FT_MulDiv_No_Round( FT_Long  a,
                      FT_Long  b,
                      FT_Long  c )
  {
    FT_Int   s;
    FT_Long  d;


    s = 1;
    if ( a < 0 ) { a = -a; s = -1; }
    if ( b < 0 ) { b = -b; s = -s; }
    if ( c < 0 ) { c = -c; s = -s; }

    d = (FT_Long)( c > 0 ? (FT_Int64)a * b / c
                         : 0x7FFFFFFFL );

    return ( s > 0 ) ? d : -d;
  }

/* Standalone allocation hooks required by FreeType 2.15.0.  The adapter
   supplies a bounded, caller-owned arena through FT_Memory; no libc heap. */
#define FT_QNEW_ARRAY( ptr, count ) \
  ( (ptr) = memory->alloc( memory, (long)( (count) * sizeof *(ptr) ) ), \
    error = (ptr) ? 0 : Raster_Err_Raster_Overflow )
#define FT_FREE( ptr ) \
  do { memory->free( memory, (ptr) ); (ptr) = NULL; } while ( 0 )

#endif /* FTMISC_H_ */


/* END */
