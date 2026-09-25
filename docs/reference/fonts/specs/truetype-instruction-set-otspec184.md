---
layout: Conceptual
title: TrueType Instruction Set (OpenType 1.8.4) - Typography | Microsoft Learn
canonicalUrl: https://learn.microsoft.com/en-us/typography/opentype/otspec184/tt_instructions
ms.service: typography
breadcrumb_path: /typography/breadcrumbs/toc.json
uhfHeaderId: MSDocsHeader-MSTypography
feedback_system: OpenSource
author: v-nihar
ms.author: alib
ms.date: 2020-10-28T00:00:00.0000000Z
feedback_product_url: https://github.com/MicrosoftDocs/typography-issues/issues/new?template=opentype-docs-feedback.yml
description: The TrueType Instruction Set (OpenType 1.8.4)
keywords: typography
ms.topic: article
source-file: https://www.microsoft.com/typography/otspec/ttinst1.docx
locale: en-us
document_id: b6c50d79-8630-e5e7-b853-acd6e5f7704e
document_version_independent_id: b6c50d79-8630-e5e7-b853-acd6e5f7704e
updated_at: 2021-12-09T00:01:00.0000000Z
original_content_git_url: https://github.com/MicrosoftDocs/typography/blob/live/typographydocs/opentype/otspec184/tt_instructions.md
gitcommit: https://github.com/MicrosoftDocs/typography/blob/a52fe690ed6551076ab3744b0c2727abbee6aca6/typographydocs/opentype/otspec184/tt_instructions.md
git_commit_id: a52fe690ed6551076ab3744b0c2727abbee6aca6
site_name: Docs
depot_name: Win.typography
page_type: conceptual
toc_rel: ../../toc.json
pdf_url_template: https://learn.microsoft.com/pdfstore/en-us/Win.typography/{branchName}{pdfName}
feedback_help_link_type: ''
feedback_help_link_url: ''
word_count: 17241
asset_id: opentype/otspec184/tt_instructions
moniker_range_name: 
monikers: []
item_type: Content
source_path: typographydocs/opentype/otspec184/tt_instructions.md
cmProducts:
- https://authoring-docs-microsoft.poolparty.biz/devrel/2d774b87-7dcb-40bf-a0b9-5a7a9efff0d1
spProducts:
- https://authoring-docs-microsoft.poolparty.biz/devrel/89dc5f37-0e4e-4b05-ad87-5fcd2b941a8a
platformId: 2132a285-3468-4904-0aec-f309f30d2bd7
---

# TrueType Instruction Set (OpenType 1.8.4) - Typography | Microsoft Learn

TrueType provides instructions for each of the following tasks and a set of general purpose instructions. This chapter describes the TrueType instruction set. Instruction descriptions are organized by category based on their function.

- Pushing data onto the interpreter stack
- Managing the Storage Area
- Managing the Control Value Table
- Modifying Graphics State settings
- Managing outlines
- General purpose instructions

## Anatomy of a TrueType Instruction

TrueType instructions are uniquely specified by their opcodes. For convenience, this book will refer to instructions by their names. Each instruction name is a mnemonic intended to aid in remembering that instruction’s function. For example, the MDAP instruction stands for Move Direct Absolute Point. Similarly, RUTG is short for Round Up To Grid. A brief description of each instruction clarifying the mnemonic marks the start of a new instruction.

One name may actually refer to several different but closely related instructions. A bracketed list of Boolean values follows each name to uniquely specify a particular variant of a given instruction. The Boolean list can be converted to a binary number and that number added to the base opcode for the instruction to obtain the opcode for any instruction variant.

To obtain the opcode for any instruction, take the lower of the two opcode values given in the code range and add the unsigned binary number represented by the list of binary digits. The left most bit is the most significant. For example, given an instruction with the opcode range 0xCO–0xDF and five Boolean flags (a through e) the opcode for a given instruction base can be computed as shown:

Opcode = 0xC0 + a · 2^4^ + b · 2^3^ + c · 2^2^ + d · 2^1^ + e · 2^0^

If these flags were set to 11101 the code would be computed as follows:

0xC0 + 1 · 2^4^ + 1 · 2^3^ + 1 · 2^2^ + 0 · 2^1^ + 1 · 2^0^

- = 0xC0 + 0x10 + 0x8 + 0x4 + 0x1
- = 0xC0 + 0x1D = 0xDD

Instruction opcodes are part of the instruction stream, a sequence of opcodes and data. The instruction stream is not a stack. While the stream of opcodes and data on the instruction stream is gradually used up, no new data is added to the instruction stream by the execution of another instruction (i.e. there is no equivalent of a push instruction that adds data to the instruction stream). It is possible to alter the flow of control through the instruction stream using one of the jump instructions described in a later section.

The instruction stream is shown as a sequence of opcodes and data. Since the instruction stream is 1-byte wide, words will be broken up into high bytes and low bytes with high bytes appearing first in the stream. For added readability, instruction names are used in illustrations instead of opcodes. An arrow will point to the next instruction awaiting execution.
![A sequence has the NPUSHB instruction and following data. A separate sequence has the NPUSHW instruction with following data.](images/ttinst_inset_p1_01.png)Figure 3–1 The instruction stream with a push byte instruction (left) and a push word instruction (right)
A few instructions known collectively as push instructions move data from the instruction stream to the interpreter stack. These instructions are unique in taking their arguments from the instruction stream. All other TrueType instructions take any data needed from the stack at the time they are executed. Any results produced by a TrueType instruction are pushed onto the interpreter stack.

An instruction that expects two arguments and pushes a third would expect the two arguments to be at the top of the stack. Any result pushed by that instruction appears at the top of the stack.
![Representation of a stack with three elements 'a', 'b' and 'c'.](images/ttinst_inset_p1_02.png)The listing a b c denotes a stack consisting of three elements with a being at the top of the stack, b being in the middle, and c at the bottom as shown.
To easily remember the order in which stack values are handled during arithmetic or logical operations, imagine writing the stack values from left to right, starting with the bottom value. Then insert the operator between the two furthest right elements. For example, subtract a,b would be interpreted as (b-a):

c b - a

GT a,b would be interpreted as (b&gt;a):

c b &gt; a

The statement push d, e means push d then push e adding two elements to the stack as shown.
![Representation of a stack of elements 'a', 'b' and 'c', with another element 'd' pushed onto the top, and then another element 'e' subsequently pushed on top.](images/ttinst_inset_p1_03.png)
To indicate that the top two stack elements are to be removed the statement would be pop e, d.
![Representation of a stack with element 'e' popped of the top, then another element 'd' popped off the top, leaving three elements 'a', 'b' and 'c'.](images/ttinst_inset_p1_04.png)
It has already been noted that the bracketed list of binary digits that follows the instruction name uniquely identifies an instruction variant. This is done by having the bits represent a list of Boolean flags that can be set to TRUE with a value of 1 or to FALSE with a value of 0. Binary digits that follow the name can also be grouped to form a larger binary number. In such cases, the documentation specifies the meaning associated with each possible numerical combination.

An instruction specification consists of the instruction name followed by its bracketed Boolean flags. Additional information describing the flags and explaining the stack interaction and any Graphics State dependencies is provided in tabular form:

| Code Range | the range of hexadecimal codes identifying this instruction and its variants |
| --- | --- |
| Flags | an explanation of the meaning of a bracketed binary number |
| --- | --- |
| From IS | any arguments taken from the instruction stream by push instructions |
| --- | --- |
| Pops | any arguments popped from the stack |
| --- | --- |
| Pushes | any arguments pushed onto the stack |
| --- | --- |
| Uses | any state variables whose value this instruction depends upon |
| --- | --- |
| Sets | any state variables set by this instruction |
| --- | --- |

Instruction descriptions include illustrations intended to clarify stack interactions, Graphics State effects, and changes to interpreter tables.

In the case of instructions that move points, an illustration will be provided to clarify the direction and magnitude of the movement. In these illustrations, shades of gray will be used to indicate the sequence in which points have been moved. The darker the fill, the more recently a point has been moved.

## Data types

### The instruction stream

Instruction opcodes are always bytes. Values in the instruction stream are bytes.

### The stack

Values pushed onto the stack or popped from the stack are always 32 bit quantities (int32 or uint32). When values that are less than 32 bits are pushed onto the stack, bytes are expanded to 32 bit quantities by padding the upper bits with zeroes and words are sign extended to 32 bits. In cases where two instruction stream bytes are combined to form a word, the high order bits appear first in the instruction stream.

> 
> *Note:* On a 16-bit system, such as Windows, all stack operations are on 16-bit values (int16 or uint16). Care must be taken to avoid overflow. It is also important to note that F26dot6 values (used for internal scalar math) are represented instead as 10 dot 6 values (i.e. the upper 16 bits are not supported).

![Representation of a hexadecimal byte value FF being zero extended to a 32-bit value 0000 00FF.](images/ttinst_inset_p1_05.png)Figure 3–2 A byte padded to a 32 bit long word (uint32)![Representation of two hexadecimal byte values FF and D2 treated as a word that is extended to a 32-bit value FFFF FFD2.](images/ttinst_inset_p1_06.png)Figure 3–3 A word sign extended to a 32 bit long word (uint32)
All values on the stack are signed. Instructions, however, interpret these 32-bit quantities in a variety of ways. The interpreter variously understands quantities as integers and as fixed point numbers.

Values such as pixel coordinates are represented as 32-bit quantities consisting of 26 bits of whole number and 6 bits of fraction. These are fixed point numbers with the data type name F26Dot6.

The setting of the freedom\_vector and projection\_vector are represented as 2.14 fixed point numbers. The upper 16 bits of the 32 bit quantity are ignored.

A given set of 32 bits will have a different value depending upon how it is interpreted. The following 32 bit value interpreted as an integer has the value 264.
![A 32-bit binary representation of the decimal value 264 (bits 8 and 4 are set).](images/ttinst_inset_p1_07.png)
The same 32 bit quantity interpreted as an F26Dot6 fixed point number has the value 4.125.
![A 32-bit binary value with six fractional bits (bits 0 to 5) and 26 integer bits (bits 6 to 31). Bits 8 and 4 are set, representing the value 4.125.](images/ttinst_inset_p1_08.png)
The figure below gives several examples of expressing pixel values as 26.6 words.
![Binary representations of four 26.6 values.](images/ttinst_inset_p1_09.png)
## Pushing data onto the interpreter stack

Most TrueType instructions take their arguments from the interpreter stack. A few instructions, however, take their arguments from the instruction stream. Their purpose is to move data from the instruction stream to the interpreter stack. Collectively these instructions are known as the push instructions.

### PUSH N Bytes

| NPUSHB[ ] |  |
| --- | --- |
| Code Range | 0x40 |
| --- | --- |
| From IS | n: number of bytes to push (1 byte interpreted as an integer) b1, b2,...bn: sequence of n bytes |
| --- | --- |
| Pushes | b1, b2, bn: sequence of n bytes each padded to 32 bits (uint32) |
| --- | --- |

Takes *n* unsigned bytes from the instruction stream, where n is an unsigned integer in the range (0..255), and pushes them onto the stack. *n* itself is not pushed onto the stack.
![A sequence has the NPUshB instruction followed by an operand value n followed by n bytes of data. Also, data bytes 1 to n are pushed onto the stack.](images/ttinst_inset_p1_10.png)
### PUSH N Words

| NPUSHW[ ] |  |
| --- | --- |
| Code Range | 0x41 |
| --- | --- |
| From IS | n: number of words to push (one byte interpreted as an integer) w1, w2,...wn: sequence of n words formed from pairs of bytes, the high byte appearing first |
| --- | --- |
| Pushes | w1, w2,...wn: sequence of n words each sign extended to 32 bits (int32) |
| --- | --- |

Takes n 16-bit signed words from the instruction stream, where n is an unsigned integer in the range (0..255), and pushes them onto the stack. n itself is not pushed onto the stack.
![A sequence has the NPUSHW instruction followed by an operand value n followed by n words of data. Also, data words 1 to n are pushed onto the stack.](images/ttinst_inset_p1_11.png)
### PUSH Bytes

| PUSHB[abc] |  |
| --- | --- |
| Code Range | 0xB0 – 0xB7 |
| --- | --- |
| abc | number of bytes to be pushed - 1 |
| --- | --- |
| From IS | b0, b1,..bn: sequence of n + 1 bytes |
| --- | --- |
| Pushes | b0, b1, ...,bn: sequence of n + 1 bytes each padded to 32 bits (uint32) |
| --- | --- |

Takes the specified number of bytes from the instruction stream and pushes them onto the interpreter stack.

The variables a, b, and c are binary digits representing numbers from 000 to 111 (0-7 in binary). Because the actual number of bytes (n) is from 1 to 8, 1 is automatically added to the ABC figure to obtain the actual number of bytes pushed.
![A sequence has the PUSHB\[abc\] instruction followed by n bytes of data. Also, data bytes 1 to n are pushed onto the stack.](images/ttinst_inset_p1_12.png)
*Example:*
![A sequence has the PUSHB\[010\] instruction followed by three bytes of data. Also, the three bytes of data are pushed onto the stack.](images/ttinst_inset_p1_13.png)
### PUSH Words

| PUSHW[abc] |  |
| --- | --- |
| Code Range | 0xB8 - 0xBF |
| --- | --- |
| abc | number of words to be pushed - 1. |
| --- | --- |
| From IS | w0,w1,..wn: sequence of n+1 words formed from pairs of bytes, the high byte appearing first |
| --- | --- |
| Pushes | w0, w1,...wn: sequence of n+1 words each sign extended to 32 bits (int32) |
| --- | --- |

Takes the specified number of words from the instruction stream and pushes them onto the interpreter stack.

The variables a, b, and c are binary digits representing numbers from 000 to 111 (0-7 binary). Because the actual number of bytes (n) is from 1 to 8, 1 is automatically added to the abc figure to obtain the actual number of bytes pushed.
![A sequence has the PUSHW\[abc\] instruction followed by n words (byte pairs) of data. Also, data words 1 to n are pushed onto the stack.](images/ttinst_inset_p1_14.png)
*Example:*
![A sequence has the PUSHW\[001\] instruction followed by two words (four bytes) of data. Also, the two words of data are pushed onto the stack.](images/ttinst_inset_p1_15.png)
## Managing the Storage Area

The interpreter Storage Area is a block of memory that can be used to store and later access 32 bit values. Instructions exist for writing values to the Storage Area and retrieving values from the Storage Area. Attempting to read a value from a storage location that has not previously had a value written to it will yield unpredictable results.

### Read Store

| RS[ ] |  |
| --- | --- |
| Code Range | 0x43 |
| --- | --- |
| Pops | location: Storage Area location (uint32) |
| --- | --- |
| Pushes | value: Storage Area value (uint32) |
| --- | --- |
| Gets | Storage Area value |
| --- | --- |

This instruction reads a 32 bit value from the Storage Area location popped from the stack and pushes the value read onto the stack. It pops an address from the stack and pushes the value found in that Storage Area location to the top of the stack. The number of available storage locations is specified in the maxProfile table in the font file.
![A location is popped off the stack, and a value is pushed onto the stack.](images/ttinst_inset_p1_16.png)
*Example:*
![A sequence has the RS\[\] instruction. Also, a storage area holds the value 0x0000 001B at location 2. Also, 2 is popped off the stack, and the value 0x0000 001B is pushed onto the stack.](images/ttinst_inset_p1_17.png)The effect of the RS instruction is to push the value 0x1B of the Storage Area onto the Stack.
### Write Store

| WS[ ] |  |
| --- | --- |
| Code Range | 0x42 |
| --- | --- |
| Pops | value: Storage Area value (uint32) |
| --- | --- |
| - | location: Storage Area location (uint32) |
| --- | --- |
| Pushes | – |
| --- | --- |
| Gets | Storage Area value |
| --- | --- |

This instruction writes a 32 bit value into the storage location indexed by locations. It works by popping a value and then a location from the stack. The value is placed in the Storage Area location specified by that address. The number of storage locations is specified in the maxProfile table in the font file.
![A value and then a location are popped of the stack. Also, the value is stored at that location in a storage area.](images/ttinst_inset_p1_18.png)
*Example:*
![A sequence has the WS\[\] instruction. Also, the value 0x0000 0118 is popped off the stack, then the location 3A is popped off the stack, and the value 0x0000 0118 is stored at location 3A.](images/ttinst_inset_p1_19.png)Write the value 0x0000 0118 to location 3A in the Storage Area.
## Managing the Control Value Table

The Control Value Table stores information that is accessed by the indirect instructions. Values can be written to the CVT in FUnits or pixel units as proves convenient. Values read from the CVT are always in pixels (F26Dot6). This table, unlike the Storage Area, is initialized by the font and is automatically scaled.

### Write Control Value Table in Pixel units

| WCVTP[ ] |  |
| --- | --- |
| Code Range | 0x44 |
| --- | --- |
| Pops | value: number in pixels (F26Dot6 fixed point number) |
| --- | --- |
| - | location: Control Value Table location (uint32) |
| --- | --- |
| Pushes | – |
| --- | --- |
| Sets | Control Value Table entry |
| --- | --- |

Pops a location and a value from the stack and puts that value in the specified location in the Control Value Table. This instruction assumes the value is in pixels and not in FUnits.
![A pixel value and a location are popped off the stack. Tthe value is stored at that location in the Control Value Table.](images/ttinst_inset_p1_20.png)
### Write Control Value Table in FUnits

| WCVTF[ ] |  |
| --- | --- |
| Code Range | 0x70 |
| --- | --- |
| Pops | value: number in FUnits (uint32) |
| --- | --- |
| - | location: Control Value Table location (uint32) |
| --- | --- |
| Pushes | – |
| --- | --- |
| Sets | Control Value Table entry |
| --- | --- |

Pops a location and a value from the stack and puts the specified value in the specified address in the Control Value Table. This instruction assumes the value is expressed in FUnits and not pixels. The value is scaled before being written to the table.
![An FUnit value and a location are popped of the stack. The value is stored at that location in the Control Value Table.](images/ttinst_inset_p1_21.png)
### Read Control Value Table

| RCVT[ ] |  |
| --- | --- |
| Code Range | 0x45 |
| --- | --- |
| Pops | location: CVT entry number (uint32) |
| --- | --- |
| Pushes | value: CVT value (F26Dot6) |
| --- | --- |
| Gets | Control Value Table entry |
| --- | --- |

Pops a location from the stack and pushes the value in the location specified in the Control Value Table onto the stack.
![A location is popped off the stack. The Control Value Table has a certain value at that location. That value is pushed onto the stack.](images/ttinst_inset_p1_22.png)
## Managing the Graphics State

Instructions can be used to set the value of Graphics State variables and, in some cases, to retrieve their current value.

### Getting a value

Instructions that retrieve the value of a state variable have names that begin with the word get. Get instructions will return the value of the state variable in question by placing that value on the top of the stack.

The illustration shows the effect of a GPV or get projection\_vector instruction. It takes the x and y components of the projection\_vector from the Graphics State and places them on the stack.
![A projection vector variable has (x, y) values of (1, 0). 0 is pushed onto the stack, then 1 is pushed onto the stack.](images/ttinst_inset_p1_23.png)
### Setting a value

Instructions that change the value of a Graphics State variable have a name that begins with the word set. Set instructions expect their arguments to be at the top of the interpreter stack
![1 is popped off the stack, then 0 is popped off the stack. (1, 0) are set as the (x, y) values of a projection vector variable.](images/ttinst_inset_p1_24.png)Figure 3–4 Setting the value of the Graphics State variable projection\_vector
In addition to simple sets and gets, some instructions exist to simplify management of the values of state variables. For example, a number of instructions exist to set the direction of the freedom\_vector and the projection\_vector. In setting a vector, it is possible to set it to either of the coordinate axes, to the direction specified by a line, or to a direction specified by values taken from the stack. An instruction exists that directly sets the freedom\_vector to the same value as the projection\_vector.

### Set freedom and projection Vectors To Coordinate Axis

| SVTCA[a] |  |
| --- | --- |
| Code Range | 0x00 - 0x01 |
| --- | --- |
| a | 0: set vectors to the y-axis |
| --- | --- |
| - | 1: set vectors to the x-axis |
| --- | --- |
| Pops | - |
| --- | --- |
| Pushes | - |
| --- | --- |
| Sets | projection\_vector |
| --- | --- |
| - | freedom\_vector |
| --- | --- |

Sets both the projection\_vector and freedom\_vector to the same one of the coordinate axes.

The SVTCA is a shortcut for using both the SFVTCA and SPVTCA instructions. SVTCA[1] is equivalent to SFVTCA[1] followed by SPVTCA[1]. This instruction ensures that both movement and measurement are along the same coordinate axis.

*Example:*

SVTCA[1]
![Projection and freedom vectors are both set in the x direction.](images/ttinst_inset_p1_25.png)Sets both measurement and movement to the x direction.
SVTCA[0]
![Projection and freedom vectors are both set in the y direction.](images/ttinst_inset_p1_26.png)Sets both measurement and movement to the y direction.
### Set Projection\_Vector To Coordinate Axis

| SPVTCA[a] |  |
| --- | --- |
| Code Range | 0x02 - 0x03 |
| --- | --- |
| a | 0: set the projection\_vector to the y-axis |
| --- | --- |
| - | 1: set the projection\_vector to the x-axis |
| --- | --- |
| Pops | - |
| --- | --- |
| Pushes | - |
| --- | --- |
| Sets | projection\_vector |
| --- | --- |

Sets the projection\_vector to one of the coordinate axes depending on the value of the flag a.

*Example:*

SPVTCA[0]
![The projection vector is set in the y direction.](images/ttinst_inset_p1_27.png)Sets the projection\_vector to the y-axis assuring the measurement will be in that direction.
### Set Freedom\_Vector to Coordinate Axis

| SFVTCA[a] |  |
| --- | --- |
| Code Range | 0x04 - 0x05 |
| --- | --- |
| a | 0: set the freedom\_vector to the y-axis |
| --- | --- |
| - | 1: set the freedom\_vector to the x-axis |
| --- | --- |
| Pops | - |
| --- | --- |
| Pushes | - |
| --- | --- |
| Sets | freedom\_vector |
| --- | --- |

Sets the freedom\_vector to one of the coordinate axes depending upon the value of the flag a.

*Example:*

SFVTCA[0]
![The freedom vector is set in the y direction.](images/ttinst_inset_p1_28.png)Sets the freedom\_vector to the y-axis ensuring that movement will be along that axis.
### Set Projection\_Vector To Line

| SPVTL[a] |  |
| --- | --- |
| Code Range | 0x06 - 0x07 |
| --- | --- |
| a | 0: sets projection\_vector to be parallel to line segment from p1 to p2 |
| --- | --- |
| - | 1: sets projection\_vector to be perpendicular to line segment from p1 to p2; the vector is rotated counter clockwise 90 degrees |
| --- | --- |
| Pops | p1: point number (uint32) |
| --- | --- |
| - | p2: point number (uint32) |
| --- | --- |
| Pushes | - |
| --- | --- |
| Uses | point p1 in the zone pointed at by zp2 |
| --- | --- |
| - | point p2 in the zone pointed at by zp1 |
| --- | --- |
| Sets | projection\_vector |
| --- | --- |

Sets the projection\_vector to a unit vector parallel or perpendicular to the line segment from point p1 to point p2.

*Example:*
![A sequence has the SPVTL\[a\] instruction. Value p1, then p2, are popped off the stack. The projection vector is set in the same direction as a line from p1 to p2.](images/ttinst_inset_p1_29.png)If parallel, the projection\_vector points from p1 toward p2 as shown.![The projection vector is set in a direction perpendicular to the direction of the projection vector in the previous figure.](images/ttinst_inset_p1_30.png)If perpendicular the projection\_vector is obtained by rotating the parallel vector in a counter clockwise manner as shown. 
*Case 1:*

SPVTL[1]
![A sequence has the SPVTL\[0\] instruction. The values 7 and 14 are popped off the stack. The projection vector is set in the same direction as a line from point 7 to point 14.](images/ttinst_inset_p1_31.png)Sets the projection\_vector to be parallel to the line from point 7 to point 14.
*Case 2:*

SPVTL[1]
![A sequence has the SPVTL\[1\] instruction. The values 7 and 14 popped off the stack. The projection vector is set in the direction perpendicular to a line from point 7 to point 14.](images/ttinst_inset_p1_32.png)Sets the projection\_vector to be perpendicular to the line from point 7 to point 14.
*Case 3:*

SPVTL[1]
![A sequence has the SPVTL\[1\] instruction. The values 14 and 7 are popped off the stack. The projection vector is set in the direction perpendicular to a line from point 14 to point 7.](images/ttinst_inset_p1_33.png)The order in which the points are specified matters. This instruction sets the projection\_vector to be perpendicular to the line from point 14 to point 7.
### Set Freedom\_Vector To Line

| SFVTL[a] |  |
| --- | --- |
| Code Range | 0x08 - 0x09 |
| --- | --- |
| a | 0: set freedom\_vector to be parallel to the line segment defined by points p1 and p2 |
| --- | --- |
| - | 1: set freedom\_vector perpendicular to the line segment defined by points p1 and p2; the vector is rotated counter clockwise 90 degrees |
| --- | --- |
| Pops | p1: point number (uint32) |
| --- | --- |
| - | p2: point number (uint32) |
| --- | --- |
| Pushes | - |
| --- | --- |
| Sets | freedom\_vector |
| --- | --- |
| Uses | point p1 in the zone pointed at by zp2 |
| --- | --- |
| - | point p2 in the zone pointed at by zp1 |
| --- | --- |

![The values p1 and p2 are popped off the stack. A line is shown from p1 to p2.](images/ttinst_inset_p1_34.png)Sets the freedom\_vector to a unit vector parallel or perpendicular to the line segment defined by points p1 and p2.![The freedom vector is set in the same direction as the line in the previous figure.](images/ttinst_inset_p1_35.png)If parallel the freedom\_vector points from p1 toward p2 as shown.![The freedom vector is set perpendicular to the line in the previous figure.](images/ttinst_inset_p1_36.png)If perpendicular the freedom\_vector is obtained by rotating the parallel vector in a counter clockwise manner as shown.
### Set Freedom\_Vector To Projection Vector

| SFVTPV[ ] |  |
| --- | --- |
| Code | 0x0E |
| --- | --- |
| Pops | - |
| --- | --- |
| Pushes | - |
| --- | --- |
| Sets | freedom\_vector |
| --- | --- |

Sets the freedom\_vector to be the same as the projection\_vector.
![The projection vector and the freedom vector have different directions.](images/ttinst_inset_p1_37.png)Before![The projection vector and the freedom vector have the same direction.](images/ttinst_inset_p1_38.png)After
### Set Dual Projection\_Vector To Line

| SDPVTL[a] |  |
| --- | --- |
| Code Range | 0x86 - 0x87 |
| --- | --- |
| a | 0: Vectors are parallel to line |
| --- | --- |
| - | 1: Vectors are perpendicular to line |
| --- | --- |
| Pops | p1: first point number (uint32) |
| --- | --- |
| - | p2: second point number (uint32) |
| --- | --- |
| Pushes | - |
| --- | --- |
| Sets | dual\_projection\_vector and projection\_vector |
| --- | --- |
| Uses | point p1 in the zone pointed at by zp2 |
| --- | --- |
| - | point p2 in the zone pointed at by zp1 |
| --- | --- |

Pops two point numbers from the stack and uses them to specify a line that defines a second, dual\_projection\_vector. This dual\_projection\_vector uses coordinates from the scaled outline before any grid-fitting took place. It is used only with the IP, GC, MD, MDRP and MIRP instructions. Those instructions will use the dual\_projection\_vector when they measure distances between ungrid-fitted points. The dual\_projection\_vector will disappear when any other instruction that sets the projection\_vector is used.
![A sequence has the SDPVTL\[a\] instruction. The values p1 and p2 are popped from the stack. A projection vector is set in the direction of the line from p1 to p2. A separate line is shown with p1 and p2 in different positions, and a dual projection vector is set in the direction of that line.](images/ttinst_inset_p1_39.png)*NOTE: The dual\_projection\_vector is set parallel to the points as they appeared in the original outline before any grid-fitting took place.*
### Set Projection\_Vector From Stack

| SPVFS[ ] |  |
| --- | --- |
| Code Range | 0x0A |
| --- | --- |
| Pops | y: y component of projection\_vector (2.14 fixed point number padded with zeroes) |
| --- | --- |
| - | x: x component of projection\_vector (2.14 fixed point number padded with zeroes) |
| --- | --- |
| Pushes | - |
| --- | --- |
| Sets | projection\_vector |
| --- | --- |

Sets the direction of the projection\_vector, using values x and y taken from the stack, so that its projections onto the x and y-axes are x and y, which are specified as signed (two’s complement) fixed-point (2.14) numbers. The square root of (x2 + y2) must be equal to 0x4000 (hex).

If values are to be saved and used by a glyph program, font program or preprogram across different resolutions, extreme care must be used. The values taken from or put on the stack are 2.14 fixed-point values for the x and y components of the vector in question. The values are based on the normalized vector lengths. More simply, the values must always be set such that (X\*\*2 + Y\*\*2) is 1.

If a TrueType program uses specific values for X and Y to set the vectors to certain angles, these values will not produce identical results across different aspect ratios. Values that work correctly at 1:1 aspect ratios (such as VGA and 8514) will not necessarily yield the desired results at a ratio of 1.33:1 (e.g. the EGA).

By the same token, if a TrueType program is making use of the values returned by GPV and GFV, the values returned for a specific angle will vary with the aspect ratio in use at the time.
![A sequence has the instructino SPVFS\[\]. The values y, then x, are popped from the stack.](images/ttinst_inset_p1_40.png)
*Example:*

SPVFS[ ]
![The values 0x0000 0000 and 0x0000 4000 are popped from the stack. The projection vector is set in the direction of the x axis.](images/ttinst_inset_p1_41.png)Sets the projection\_vector to a unit vector that points in the direction of the x axis
### Set Freedom\_Vector From Stack

| SFVFS[ ] |  |
| --- | --- |
| Code | 0x0B |
| --- | --- |
| Pops | y: y component of freedom\_vector (2.14 fixed point number padded with zeroes) |
| --- | --- |
| - | x: x component of freedom\_vector (2.14 fixed point number padded with zeroes) |
| --- | --- |
| Pushes | - |
| --- | --- |
| Sets | freedom\_vector |
| --- | --- |

Sets the direction of the freedom\_vector using the values x and y taken from the stack. The vector is set so that its projections onto the x and y -axes are x and y, which are specified as signed (two’s complement) fixed-point (2.14) numbers. The square root of (x2 + y2) must be equal to 0x4000 (hex).

If values are to be saved and used by a glyph program, font program or preprogram across different resolutions, extreme care must be used. The values taken from or put on the stack are 2.14 fixed-point values for the x and y components of the vector in question. The values are based on the normalized vector lengths. More simply, the values must always be set such that (X\*\*2 + Y\*\*2) is 1.

If a TrueType program uses specific values for X and Y to set the vectors to certain angles, these values will not produce identical results across different aspect ratios. Values that work correctly at 1:1 aspect ratios (such as VGA and 8514) will not necessarily yield the desired results at a ratio of 1.33:1 (e.g. the EGA).

By the same token, if a TrueType program is making use of the values returned by GPV and GFV, the values returned for a specific angle will vary with the aspect ratio in use at the time.
![A sequence has the SFVFS\[\] instruction. The values y, then x, are popped from the stack.](images/ttinst_inset_p1_42.png)
*Example:*
![The values 0x0000 4000 and 0x0000 0000 are popped from the stack. The freedom vector is set in the direction of the y axis.](images/ttinst_inset_p1_43.png)Sets the freedom\_vector to a unit vector that points in the direction of the y axis.
### Get Projection\_Vector

| GPV[ ] |  |
| --- | --- |
| Code Range | 0x0C |
| --- | --- |
| Pops | - |
| --- | --- |
| Pushes | x: x component of projection\_vector (2.14 fixed point number padded with zeroes) |
| --- | --- |
| - | y : y component of projection\_vector (2.14 fixed point number padded with zeroes) |
| --- | --- |
| Gets | projection\_vector |
| --- | --- |

Pushes the x and y components of the projection\_vector onto the stack as two 2.14 numbers.

If values are to be saved and used by a glyph program, font program or preprogram across different resolutions, extreme care must be used. The values taken from or put on the stack are 2.14 fixed-point values for the x and y components of the vector in question. The values are based on the normalized vector lengths. More simply, the values must always be set such that (X\*\*2 + Y\*\*2) is 1.

If a TrueType program uses specific values for X and Y to set the vectors to certain angles, these values will not produce identical results across different aspect ratios. Values that work correctly at 1:1 aspect ratios (such as VGA and 8514) will not necessarily yield the desired results at a ratio of 1.33:1 (e.g. the EGA).

By the same token, if a TrueType program is making use of the values returned by GPV and GFV, the values returned for a specific angle will vary with the aspect ratio in use at the time.
![A sequence has the GPV\[\] instruction. A projection vector variable holds (x, y) values. The value x is pushed onto the stack, then y is pushed onto the stack.](images/ttinst_inset_p1_44.png)
*Example:*

*Case 1:*
![The projection vector is in the direction of the x axis.](images/ttinst_inset_p1_45.png)The stack entry 0x4000 which when interpreted as a 2.14 number is simply 1. This command reveals that, in this case, the projection\_vector is a unit vector that points in the x direction.
*Case 2:*
![The projection vector is in the direction of the y axis. A sequence has the GPV\[\] instruction. The values 0x0000 4000 and 0x0000 0000 are pushed onto the stack.](images/ttinst_inset_p1_46.png)Here the projection\_vector is a unit vector that points in the direction of the y axis.
*Case 3:*
![The projection vector points at an angle of 45 degrees. A sequence has the GPV\[\] instruction. The values 0x0000 2D41 and 0x0000 2D41 are pushed onto the stack.](images/ttinst_inset_p1_47.png)*NOTE: 0x2D41 is the hex equivalent of sqrt(2)/2 . As a result of this instruction, the projection\_vector is set to a 45 degree angle relative to the x-axis.*
### Get Freedom\_Vector

| GFV[ ] |  |
| --- | --- |
| Code Range | 0x0D |
| --- | --- |
| Pops | - |
| --- | --- |
| Pushes | x: x-component of freedom\_vector (2.14 number padded with zeroes) |
| --- | --- |
| - | y: y component of freedom\_vector (2.14 number padded with zeroes) |
| --- | --- |
| Gets | freedom\_vector |
| --- | --- |

Puts the x and y components of the freedom\_vector on the stack. The freedom\_vector is put onto the stack as two 2.14 coordinates.

If values are to be saved and used by a glyph program, font program or preprogram across different resolutions, extreme care must be used. The values taken from or put on the stack are 2.14 fixed-point values for the x and y components of the vector in question. The values are based on the normalized vector lengths. More simply, the values must always be set such that (X\*\*2 + Y\*\*2) is 1.

If a TrueType program uses specific values for X and Y to set the vectors to certain angles, these values will not produce identical results across different aspect ratios. Values that work correctly at 1:1 aspect ratios (such as VGA and 8514) will not necessarily yield the desired results at a ratio of 1.33:1 (e.g. the EGA).

By the same token, if a TrueType program is making use of the values returned by GPV and GFV, the values returned for a specific angle will vary with the aspect ratio in use at the time.
![A sequence has the GFV\[\] instruction. A freedom vector variable holds (x, y) values. The value x is pushed onto the stack, then y is pushed onto the stack.](images/ttinst_inset_p1_48.png)
*Example:*

GFV[ ]
![The freedom vector points at a downward angle. The values -11596 and 11565 are pushed onto the stack.](images/ttinst_inset_p1_49.png)
### Set Reference Point 0

| SRP0[ ] |  |
| --- | --- |
| Code Range | 0x10 |
| --- | --- |
| Pops | p: point number (uint32) |
| --- | --- |
| Pushes | - |
| --- | --- |
| Sets | rp0 |
| --- | --- |
| Affects | IP, MDAP, MIAP, MIRP, MSIRP, SHC, SHE, SHP |
| --- | --- |

Pops a point number from the stack and sets rp0 to that point number.
![A value p is popped from the stack. A variable rp0 is set to the value p.](images/ttinst_inset_p1_50.png)
### Set Reference Point 1

| SRP1[ ] |  |
| --- | --- |
| Code Range | 0x11 |
| --- | --- |
| Pops | p: point number (uint32) |
| --- | --- |
| Pushes | - |
| --- | --- |
| Sets | rp1 |
| --- | --- |
| Affects | IP, MDAP, MDRP, MIAP, MSIRP, SHC, SHE, SHP |
| --- | --- |

Pops a point number from the stack and sets rp1 to that point number.
![A value p is popped from the stack. A variable rp1 is set to the value p.](images/ttinst_inset_p1_51.png)
### Set Reference Point 2

| SRP2[ ] |  |
| --- | --- |
| Code Range | 0x12 |
| --- | --- |
| Pops | p: point number (uint32) |
| --- | --- |
| Pushes | - |
| --- | --- |
| Sets | rp2 |
| --- | --- |

Pops a point number from the stack and sets rp2 to that point number.
![A value p is popped from the stack. A variable rp2 is set to the value p.](images/ttinst_inset_p1_52.png)
### Set Zone Pointer 0

| SZP0[ ] |  |
| --- | --- |
| Code Range | 0x13 |
| --- | --- |
| Pops | n: zone number (uint32) |
| --- | --- |
| Pushes | - |
| --- | --- |
| Sets | zp0 |
| --- | --- |
| Affects | ALIGNPTS, ALIGNRP, DELTAP1, DELTAP2, DELTAP3, IP, ISECT, MD, MDAP, MIAP, MIRP, MSIRP, SHC, SHE, SHP, UTP |
| --- | --- |

Pops a zone number, n, from the stack and sets zp0 to the zone with that number. If n is 0, zp0 points to zone 0. If n is 1, zp0 points to zone 1. Any other value for n is an error.
![A value n is popped from the stack. A variable zp0 is set to the enumeration value En.](images/ttinst_inset_p1_53.png)
*Example:*
![A sequence has the SZP0\[\] instruction. The value 1 is popped from the stack. zp0 is set to E1.](images/ttinst_inset_p1_54.png)
### Set Zone Pointer 1

| SZP1[ ] |  |
| --- | --- |
| Code Range | 0x14 |
| --- | --- |
| Pops | n: zone number (uint32) |
| --- | --- |
| Pushes | - |
| --- | --- |
| Sets | zp1 |
| --- | --- |
| Affects | ALIGNRPTS, ALIGNRP, IP, MD, MDRP, MSIRP, SHC, SHE, SHP, SFVTL, SPVTL |
| --- | --- |

Pops a zone number, n, from the stack and sets zp1 to the zone with that number. If n is 0, zp1 points to zone 0. If n is 1, zp1 points to zone 1. Any other value for n is an error.
![A value n is popped from the stack. A variable zp1 is set to the enumeration value En.](images/ttinst_inset_p1_55.png)
*Example:*
![A sequence has the SZP1\[\] instruction. The value 0 is popped from the stack. zp1 is set to E0.](images/ttinst_inset_p1_56.png)
### Set Zone Pointer 2

| SZP2[ ] |  |
| --- | --- |
| Code Range | 0x15 |
| --- | --- |
| Pops | n: zone number (uint32) |
| --- | --- |
| Pushes | - |
| --- | --- |
| Sets | zp2 |
| --- | --- |
| Affects | ISECT, IUP, GC, SHC, SHP, SFVTL, SHPIX, SPVTL, SC |
| --- | --- |

Pops a zone number, n, from the stack and sets zp2 to the zone with that number. If n is 0, zp2 points to zone 0. If n is 1, zp2 points to zone 1. Any other value for n is an error.
![A value n is popped from the stack. A variable zp2 is set to the enumeration value En.](images/ttinst_inset_p1_57.png)
### Set Zone PointerS

| SZPS[ ] |  |
| --- | --- |
| Code Range | 0x16 |
| --- | --- |
| Pops | n: zone number (uint32) |
| --- | --- |
| Pushes | - |
| --- | --- |
| Sets | zp0, zp1, zp2 |
| --- | --- |
| Affects | ALIGNPTS, ALIGNRP, DELTAP1, DELTAP2, DELTAP3, GC, IP, ISECT, IUP, MD, MDAP, MDRP, MIAP, MIRP, MSIRP, SC, SFVTL, SHPIX, SPVTL, SHC, SHE, SHP, SPVTL, UTP |
| --- | --- |

Pops a zone number from the stack and sets all of the zone pointers to point to the zone with that number. If n is 0, all three zone pointers will point to zone 0. If n is 1, all three zone pointers will point to zone 1. Any other value for n is an error.
![A value n is popped from the stack. Variables zp0, zp1 and zp2 are set to the enumeration value En.](images/ttinst_inset_p1_58.png)
### Round To Half Grid

| RTHG[ ] |  |
| --- | --- |
| Code Range | 0x19 |
| --- | --- |
| Pops | - |
| --- | --- |
| Pushes | - |
| --- | --- |
| Sets | round\_state |
| --- | --- |
| Affects | MDAP, MDRP, MIAP, MIRP, ROUND |
| --- | --- |
| Uses | freedom\_vector, projection\_vector |
| --- | --- |

Sets the round\_state variable to state 0 *(hg)*. In this state, the coordinates of a point are rounded to the nearest half grid line.

*Example*
![The instruction is RTHG\[\]. Freedom and project vectors point in the direction of the x axis. On a design space grid, a point n is moved right to a half grid line horizontally halfway between the main grid lines.](images/ttinst_inset_p1_59.png)
### Round To Grid

| RTG[ ] |  |
| --- | --- |
| Code Range | 0x18 |
| --- | --- |
| Pops | - |
| --- | --- |
| Pushes | - |
| --- | --- |
| Sets | round\_state |
| --- | --- |
| Affects | MDAP, MDRP, MIAP, MIRP, ROUND |
| --- | --- |
| Uses | freedom\_vector, projection\_vector |
| --- | --- |

Sets the round\_state variable to state 1 *(g)*. In this state, distances are rounded to the closest grid line.

*Example*
![The instruction is RTG\[\]. Freedom and project vectors point in the direction of the x axis. On a design space grid, a point n to the right of the half grid line is moved right to the main grid line on the right.](images/ttinst_inset_p1_60.png)
### Round To Double Grid

| RTDG[ ] |  |
| --- | --- |
| Code Range | 0x3D |
| --- | --- |
| Pops | - |
| --- | --- |
| Pushes | - |
| --- | --- |
| Sets | round\_state |
| --- | --- |
| Affects | MDAP, MDRP, MIAP, MIRP, ROUND |
| --- | --- |
| Uses | freedom\_vector, projection\_vector |
| --- | --- |

Sets the round\_state variable to state 2 *(dg)*. In this state, distances are rounded to the closest half or integer pixel.

*Example*
![The instruction is RTDG\[\]. Freedom and project vectors point in the direction of the x axis. On a design space grid, a point n to the left of the half grid line is moved right to the half grid line.](images/ttinst_inset_p1_61.png)![The instruction is RTDG\[\]. Freedom and project vectors point in the direction of the x axis. On a design space grid, a point n to the right of the half grid line is moved right to the main grid line on the right.](images/ttinst_inset_p1_62.png)
### Round Down To Grid

| RDTG[ ] |  |
| --- | --- |
| Code Range | 0x7D |
| --- | --- |
| Pops | - |
| --- | --- |
| Pushes | - |
| --- | --- |
| Sets | round\_state |
| --- | --- |
| Affects | MDAP, MDRP, MIAP, MIRP, ROUND |
| --- | --- |
| Uses | freedom\_vector, projection\_vector |
| --- | --- |

Sets the round\_state variable to state 3 *(dtg)*. In this state, distances are rounded down to the closest integer grid line.

*Example*
![The instruction is RDTG\[\]. Freedom and project vectors point in the direction of the x axis. On a design space grid, a point n to the right of the half grid line is moved left to the main grid line on the left.](images/ttinst_inset_p1_63.png)
### Round Up To Grid

| RUTG[ ] |  |
| --- | --- |
| Code Range | 0x7C |
| --- | --- |
| Pops | - |
| --- | --- |
| Pushes | - |
| --- | --- |
| Sets | round\_state |
| --- | --- |
| Affects | MDAP, MDRP, MIAP, MIRP, ROUND |
| --- | --- |
| Uses | freedom\_vector, projection\_vector |
| --- | --- |

Sets the round\_state variable to state 4 *(utg)*. In this state distances are rounded up to the closest integer pixel boundary

*Example*
![The instruction is RUTG\[\]. Freedom and project vectors point in the direction of the x axis. On a design space grid, a point n to the left of the half grid line is moved right to the main grid line on the right.](images/ttinst_inset_p1_64.png)
### Round OFF

| ROFF[ ] |  |
| --- | --- |
| Code Range | 0x7A |
| --- | --- |
| Pops | - |
| --- | --- |
| Pushes | - |
| --- | --- |
| Sets | round\_state |
| --- | --- |
| Affects | MDAP, MDRP, MIAP, MIRP, ROUND |
| --- | --- |
| Uses | freedom\_vector, projection\_vector |
| --- | --- |

Sets the round\_state variable to state 5 *(off)*. In this state rounding is turned off.

*Example*
![The instruction is ROFF\[\]. Freedom and project vectors point in the direction of the x axis. On a design space grid, a point is within the grid but not aligned to any main or half grid line.](images/ttinst_inset_p1_65.png)
### Super ROUND

| SROUND[ ] |  |
| --- | --- |
| Code Range | 0x76 |
| --- | --- |
| Pops | n: number decomposed to obtain period, phase, threshold |
| --- | --- |
| Pushes | - |
| --- | --- |
| Sets | round\_state |
| --- | --- |
| Affects | MDAP, MDRP, MIAP, MIRP, ROUND |
| --- | --- |

SROUND allows you fine control over the effects of the round\_state variable by allowing you to set the values of three components of the round\_state: period, phase, and threshold.

More formally, SROUND maps the domain of 26.6 fixed point numbers into a set of discrete values that are separated by equal distances. SROUND takes one argument from the stack, n, which is decomposed into a period, phase and threshold.

The period specifies the length of the separation or space between rounded values in terms of grid spacing.
![Three lines represent real numbers. On the first line, numbers are indicated from 0 to 2 in increments of 0.5; the period is 0.5. On the second line, numbers 0, 1 and 2 are indicated; the period is 1.0. On the third line, numbers 0 and 2 are indicated; the period is 2.0.](images/ttinst_inset_p1_66.png)![Two lines represent real numbers. On the first line, numbers 0, 1 and 2 are indicated; phase is 0. On the second line, 0 is shown for reference, and numbers 0.25, 1.25 and 2.25 are indicated; phase is 0.25.](images/ttinst_inset_p1_67.png)The phase specifies the offset of the values from multiples of the period.
The threshold specifies the part of the domain that is mapped onto each value. More intuitively, the threshold tells a value when to “fall forward” to the next largest integer.
![Two number lines are shown, one labeled 'RTG' and one labeled 'RUTG'. On the RTG line, numbers from -0.5 to 1 in increments of 0.5 are shown for reference, and the number 0 is indicated; period is 1.0; threshold is period/2, or 0.5. On the second line, 0 and 1 are indicated; period is 1.0; threshold is period minus 1, or 0.](images/ttinst_inset_p1_68.png)
Only the lower 8 bits of the argument n are used. For SROUND gridPeriod is equal to 1.0 pixel. The byte is encoded as follows: bits 7 and 6 encode the period, bits 5 and 4 encode the phase and bits 3, 2, 1 and 0 encode the threshold as shown here.

### period

| 0 | period = gridPeriod/2 |
| --- | --- |
| 1 | period = gridPeriod |
| 2 | period = gridPeriod &ast; 2 |
| 3 | Reserved |

### phase

| 0 | phase = 0 |
| --- | --- |
| 1 | phase = period/4 |
| 2 | phase = period/2 |
| 3 | phase = gridPeriod &ast; 3/4 |

### threshold

| 0 | threshold = period -1 |
| --- | --- |
| 1 | threshold = -3/8 &ast; period |
| 2 | threshold = -2/8 &ast; period |
| 3 | threshold = -1/8 &ast; period |
| 4 | threshold = 0/8 &ast; period |
| 5 | threshold = 1/8 &ast; period |
| 6 | threshold = 2/8 &ast; period |
| 7 | threshold =3/8 &ast; period |
| 8 | threshold = 4/8 &ast; period |
| 9 | threshold = 5/8 &ast; period |
| 10 | threshold = 6/8 &ast; period |
| 11 | threshold = 7/8 &ast; period |
| 12 | threshold = 8/8 &ast; period |
| 13 | threshold = 9/8 &ast; period |
| 14 | threshold = 10/8 &ast; period |
| 15 | threshold = 11/8 &ast; period |

For example, SROUND(01:01:1000) maps numbers into the values 0.25, 1.25, 2.25, The numbers from -0.25 to 0.75 are mapped into 0.25. The range of numbers [0.75, 1.75) map into 1.25. Similarly, the numbers from [1.75, 2.75) map into the number 2.25 and so on.
![On a number line, numbers -0.25, 0, 0.75 are shown for reference. The number 0.25 is indicated; 1.25 is also indicated. Phase is 0.25; period is shown going from 0.25 to 1.25; threshold is shown going from -0.25 to 0.75.](images/ttinst_inset_p1_69.png)
Rounding occurs after compensation for engine characteristics, so the steps in the rounding of a number *n* are:

- add engine compensation to *n*.
- subtract the phase from *n*.
- add the threshold to *n*.
- truncate *n* to the next lowest periodic value (ignore the phase).
- add the phase back to *n*.
- if rounding caused a positive number to become negative, set *n* to the positive round value closest to 0.
- if rounding caused a negative number of become positive, set *n* to the negative round value closest to 0.
- the period parameters can have values of 1/2 pixel, 1 pixel, or 2 pixels.
- the phase parameters can have values of 0 pixels, 1/4 pixel, 1/2 pixel, or 3/4 pixel.
- the threshold parameters can have values of -3/8 period, -2/8 period, 11/8 period. It can also have the special value largest-number-smaller-than-period which causes rounding equivalent to CEILING.

### Super ROUND 45 degrees

| S45ROUND[ ] |  |
| --- | --- |
| Code Range | 0x77 |
| --- | --- |
| Pops | n: uint32 decomposed to obtain period, phase, threshold (uint32) |
| --- | --- |
| Pushes | - |
| --- | --- |
| Sets | round\_state |
| --- | --- |
| Affects | MDAP, MDRP, MIAP, MIRP, ROUND |
| --- | --- |

S45ROUND is analogous to SROUND. The gridPeriod is SQRT(2)/2 pixels rather than 1 pixel. It is useful for measuring at a 45 degree angle with the coordinate axes.

### Set LOOP variable

| SLOOP[ ] |  |
| --- | --- |
| Code Range | 0x17 |
| --- | --- |
| Pops | n: value for loop Graphics State variable (integer) |
| --- | --- |
| Pushes | - |
| --- | --- |
| Sets | loop |
| --- | --- |
| Affects | ALIGNRP, FLIPPT, IP, SHP, SHPIX |
| --- | --- |

Pops a value, n, from the stack and sets the loop variable count to that value. The loop variable works with the SHP[a], SHPIX[ ], IP[ ], FLIPPT[ ], and ALIGNRP[ ]. The value n indicates the number of times the instruction is to be repeated. After the instruction executes, the loop variable is reset to 1.
![A value n is popped from the stack and set as the value for a loop variable.](images/ttinst_inset_p1_70.png)
### Set Minimum\_Distance

| SMD[ ] |  |
| --- | --- |
| Code Range | 0x1A |
| --- | --- |
| Pops | distance: value for minimum\_distance (F26Dot6) |
| --- | --- |
| Pushes | - |
| --- | --- |
| Sets | minimum\_distance |
| --- | --- |

Pops a value from the stack and sets the minimum\_distance variable to that value. The distance is assumed to be expressed in sixty-fourths of a pixel.
![A value is popped from the stack and set as the value for a minimum distance variable.](images/ttinst_inset_p1_71.png)
### INSTRuction execution ConTRoL

| INSTCTRL[ ] |  |
| --- | --- |
| Code Range | 0x8E |
| --- | --- |
| Pops | s: selector flag (int32) |
| --- | --- |
| - | value: USHORT (padded to 32 bits) used to set value of instruction\_control. |
| --- | --- |
| Pushes | - |
| --- | --- |
| Sets | instruction\_control |
| --- | --- |

Sets the instruction control state variable making it possible to turn on or off the execution of instructions and to regulate use of parameters set in the CVT program. INSTCTRL[ ] can only be executed in the CVT program.

This instruction clears and sets various control flags in the rasterizer. The selector flag determines valid values for the value argument. The value determines the new setting of the raterizer control flag. In this version there are three flags in use:

- Selector flag 1 is used to inhibit grid-fitting. If s=1, valid values for the value argument are 0 (FALSE) and 1 (TRUE). If the value argument is set to TRUE (v=1), any instructions associated with glyphs will not be executed. For example, to inhibit grid-fitting when a glyph is being rotated or stretched, use the following sequence on the preprogram:

    ```
    PUSHB[000] 6    /* ask GETINFO to check for stretching or rotation */
    GETINFO[]       /* will push TRUE if glyph is stretched or rotated */
    IF[]            /* tests value at top of stack */
    PUSHB[000] 1    /* value for INSTCTRL */
    PUSHB[000] 1    /* selector for INSTCTRL */
    INSTRCTRL[]     /* based on selector and value will turn grid-fitting off */
    EIF[]
    ```
- Selector flag 2 is used to establish that any parameters set in the CVT program should be ignored when instructions associated with glyphs are executed. These include, for example, the values for scantype and the CVT cut-in. If s=1, valid values for the value argument are 0 (FALSE) and 2 (TRUE). If the value argument is set to TRUE (v=2), the default values of those parameters will be used regardless of any changes that may have been made in those values by the preprogram. If the value argument is set to FALSE (v=0), parameter values changed by the CVT program will be used in glyph instructions.
- Selector flag 3 is used to control some aspects of how some specific instructions are interpreted when ClearType™ is being used. If the selector is enabled, a font will be rendered in native ClearType mode, as opposed to backwards compatibility mode. If the value argument is set to TRUE (v=4) then the interpreter will be in native ClearType mode. If the value argument is set to FALSE (v=0) then the interpreter will be in backwards compatibility mode.

![A selector and a value are popped from the stack. The value is set as the valur for an instruction control variable.](images/ttinst_inset_p1_72.png)
### SCAN conversion ConTRoL

| SCANCTRL[ ] |  |
| --- | --- |
| Code Range | 0x85 |
| --- | --- |
| Pops | n: flags indicating when to turn on dropout control mode (16 bit word padded to 32 bits) |
| --- | --- |
| Pushes | - |
| --- | --- |
| Sets | scan\_control |
| --- | --- |

SCANCTRL is used to set the value of the Graphics State variable scan\_control which in turn determines whether the scan converter will activate dropout control for this glyph. Use of the dropout control mode is determined by three conditions:

1. Is the glyph rotated?
2. Is the glyph stretched?
3. Is the current setting for ppem less than a specified threshold?

The interpreter pops a word from the stack and looks at the lower 16 bits.

Bits 0-7 represent the threshold value for ppem. A value of FF in bits 0-7 means invoke dropout\_control for all sizes. A value of 0 in bits 0-7 means never invoke dropout\_control.

Bits 8-13 are used to turn on dropout\_control in cases where the specified conditions are met. Bits 8, 9 and 10 are used to turn on the dropout\_control mode (assuming other conditions do not block it). Bits 11, 12, and 13 are used to turn off the dropout mode unless other conditions force it. Bits 14 and 15 are reserved for future use.

| Bit | Meaning if set |
| --- | --- |
| 8 | Set dropout\_control to TRUE if other conditions do not block and ppem is less than or equal to the threshold value. |
| 9 | Set dropout\_control to TRUE if other conditions do not block and the glyph is rotated |
| 10 | Set dropout\_control to TRUE if other conditions do not block and the glyph is stretched. |
| 11 | Set dropout\_control to FALSE unless ppem is less than or equal to the threshold value. |
| 12 | Set dropout\_control to FALSE unless the glyph is rotated. |
| 13 | Set dropout\_control to FALSE unless the glyph is stretched. |
| 14 | Reserved for future use. |
| 15 | Reserved for future use. |

*For example:*

| 0x0000 | No dropout control is invoked |
| --- | --- |
| 0x01FF | Always do dropout control |
| 0x0A10 | Do dropout control if the glyph is rotated and has less than 16 pixels per-em |

The scan converter can operate in either a “normal” mode or in a “fix dropout” mode depending on the value of a set of enabling and disabling flags.

### SCANTYPE

| SCANTYPE[ ] |  |
| --- | --- |
| Code Range | 0x8D |
| --- | --- |
| Pops | n: 16 bit integer |
| --- | --- |
| Pushes | - |
| --- | --- |
| Sets | scan\_control |
| --- | --- |

Pops a 16-bit integer whose value is used to determine which rules the scan converter will use. If the value of the argument is 0, the fast scan converter will be used. If the value of the integer is 1 or 2, simple dropout control will be used. If the value of the integer is 4 or 5, smart dropout control will be used. More specifically,

- if n=0 rules 1, 2, and 3 are invoked (simple dropout control scan conversion including stubs)
- if n=1 rules 1, 2, and 4 are invoked (simple dropout control scan conversion excluding stubs)
- if n=2 rules 1 and 2 only are invoked (fast scan conversion; dropout control turned off)
- if n=3 same as n = 2
- if n = 4 rules 1, 2, and 5 are invoked (smart dropout control scan conversion including stubs)
- if n = 5 rules 1, 2, and 6 are invoked (smart dropout control scan conversion excluding stubs)
- if n = 6 same as n = 2
- if n = 7 same as n = 2

The scan conversion rules are shown here:

| Rule 1 | If a pixel’s center falls within the glyph outline, that pixel is turned on. |
| --- | --- |
| Rule 2 | If a contour falls exactly on a pixel’s center, that pixel is turned on. |
| Rule 3 | If a scan line between two adjacent pixel centers (either vertical or horizontal) is intersected by both an on-Transition contour and an off-Transition contour and neither of the pixels was already turned on by rules 1 and 2, turn on the left-most pixel (horizontal scan line) or the bottom-most pixel (vertical scan line). This is “Simple” dropout control. |
| Rule 4 | Apply Rule 3 only if the two contours continue to intersect other scan lines in both directions. That is, do not turn on pixels for ‘stubs.’ The scanline segments that form a square with the intersected scan line segment are examined to verify that they are intersected by two contours. It is possible that these could be different contours than the ones intersecting the dropout scan line segment. This is very unlikely but may have to be controlled with grid-fitting in some exotic glyphs. |
| Rule 5 | If a scan line between two adjacent pixel centers (either vertical or horizontal) is intersected by both an on-Transition contour and an off-Transition contour and neither of the pixels was already turned on by rules 1 and 2, turn on the pixel which is closer to the midpoint between the on-Transition contour and off-Transition contour. This is “Smart” dropout control. |
| Rule 6 | Apply Rule 5 only if the two contours continue to intersect other scan lines in both directions. That is, do not turn on pixels for ‘stubs.’ |

New fonts wishing to use the new modes of the ScanType instruction, but still wishing to work correctly on old rasterizers that don’t recognize the new modes should:

1. First execute a ScanType instruction using an old mode which will give the best approximation to the desired new mode (e.g. Simple Stubs for Smart Stubs), and then
2. Immediately execute another ScanType instruction with the desired new mode.

### Set Control Value Table Cut In

| SCVTCI[ ] |  |
| --- | --- |
| Code Range | 0x1D |
| --- | --- |
| Pops | n: value for cut\_in (F26Dot6) |
| --- | --- |
| Pushes | - |
| --- | --- |
| Sets | control\_value\_cut\_in |
| --- | --- |
| Affects | MIAP, MIRP |
| --- | --- |

Sets the control\_value\_cut\_in in the Graphics State. The value n is expressed in sixty-fourths of a pixel.
![A value is popped from the stack and set as the value for the cut in variable.](images/ttinst_inset_p1_73.png)
Increasing the value of the cut\_in will increase the range of sizes for which CVT values will be used instead of the original outline value.

### Set Single\_Width\_Cut\_In

| SSWCI[ ] |  |
| --- | --- |
| Code Range | 0x1E |
| --- | --- |
| Pops | n: value for single\_width\_cut\_in (F26dot6) |
| --- | --- |
| Pushes | - |
| --- | --- |
| Sets | single\_width\_cut\_in |
| --- | --- |
| Affects | MIAP, MIRP |
| --- | --- |

Sets the single\_width\_cut\_in in the Graphics State. The value n is expressed in sixty-fourths of a pixel.
![A value is popped from the stack and set as the value for the single width cut in variable.](images/ttinst_inset_p1_74.png)
### Set Single-width

| SSW[ ] |  |
| --- | --- |
| Code Range | 0x1F |
| --- | --- |
| Pops | n: value for single\_width\_value (FUnits) |
| --- | --- |
| Pushes | - |
| --- | --- |
| Sets | single\_width\_value |
| --- | --- |

Sets the single\_width\_value in the Graphics State. The single\_width\_value is expressed in FUnits, which the interpreter converts to pixels (F26Dot6).
![A value is popped from the stack and set as the value for the single width value variable.](images/ttinst_inset_p1_75.png)
### Set the auto\_flip Boolean to ON

| FLIPON[ ] |  |
| --- | --- |
| Code Range | 0x4D |
| --- | --- |
| Pops | - |
| --- | --- |
| Pushes | - |
| --- | --- |
| Sets | auto\_flip |
| --- | --- |
| Affects | MIRP |
| --- | --- |

Sets the auto\_flip Boolean in the Graphics State to TRUE causing the MIRP instructions to ignore the sign of Control Value Table entries. The default auto\_flip Boolean value is TRUE.
![An auto flip variable is set to 1.](images/ttinst_inset_p1_76.png)
### Set the auto\_flip Boolean to OFF

| FLIPOFF[ ] |  |
| --- | --- |
| Code Range | 0x4E |
| --- | --- |
| Pops | - |
| --- | --- |
| Pushes | - |
| --- | --- |
| Sets | auto\_flip |
| --- | --- |
| Affects | MIRP |
| --- | --- |

Set the auto\_flip Boolean in the Graphics State to FALSE causing the MIRP instructions to use the sign of Control Value Table entries. The default auto\_flip Boolean value is TRUE.
![An auto flip variable is set to 0.](images/ttinst_inset_p1_77.png)
### Set Angle\_Weight

| SANGW[ ] |  |
| --- | --- |
| Code Range | 0x7E |
| --- | --- |
| Pops | weight: value for angle\_weight |
| --- | --- |
| Pushes | - |
| --- | --- |
| Sets | angle\_weight |
| --- | --- |

SANGW is no longer needed because of dropped support to the AA (Adjust Angle) instruction. AA was the only instruction that used angle\_weight in the global graphics state.

Pops a weight value from the stack and sets the value of the angle\_weight state variable accordingly
![A weight value is popped from the stack and is set as the value of an angle weight variable.](images/ttinst_inset_p1_78.png)
### Set Delta\_Base in the graphics state

| SDB[ ] |  |
| --- | --- |
| Code Range | 0x5E |
| --- | --- |
| Pops | - |
| --- | --- |
| Pushes | - |
| --- | --- |
| Sets | delta\_base |
| --- | --- |
| Affects | DELTAP1, DELTAP2, DELTAP3, DELTAC1, DELTAC2, DELTAC3 |
| --- | --- |

Pops a number, n, and sets delta\_base to the value n. The default for delta\_base is 9.
![A value is popped from the stack and is set as the value of a delta base variable.](images/ttinst_inset_p1_79.png)
### Set Delta\_Shift in the graphics state

| SDS[ ] |  |
| --- | --- |
| Code Range | 0x5F |
| --- | --- |
| Pops | n: value for the delta\_shift (uint32) |
| --- | --- |
| Pushes | - |
| --- | --- |
| Sets | delta\_shift |
| --- | --- |
| Affects | DELTAP1, DELTAP2, DELTAP3, DELTAC1, DELTAC2, DELTAC3 |
| --- | --- |

Sets delta\_shift to the value n. The default for delta\_shift is 3.
![A value is popped from the stack and is set as the value of a delta shift variable.](images/ttinst_inset_p1_80.png)
## Reading and writing data

The following instructions make it possible to get and to set a point coordinate, to measure the distance between two points, and to determine the current settings for pixels per em and point size.

### Get Coordinate projected onto the projection\_vector

| GC[a] |  |
| --- | --- |
| Code Range | 0x46 - 0x47 |
| --- | --- |
| a | 0: use current position of point p |
| --- | --- |
| - | 1: use the position of point p in the original outline |
| --- | --- |
| Pops | p: point number (uint32) |
| --- | --- |
| Pushes | value: coordinate location (F26Dot6) |
| --- | --- |
| Uses | zp2, projection\_vector |
| --- | --- |

Measures the coordinate value of point p on the current projection\_vector and pushes the value onto the stack.

*Example*

The following example shows that the value returned by GC is dependent upon the current position of the projection\_vector. Note that point p is at the position (300,420) in the coordinate grid.
![A point p is shown in an x,y coordinate grid.](images/ttinst_inset_p1_81.png)
GC[1] 9
![First, the projection vector is in the direction of the x axis, and the value 300 is pushed onto the stack. Second, the projection vector is in the direction of the y axis, and the value 420 is pushed onto the stack. Third, the project vector points in the direction of a line from (300,420) to (0,0), and the value -516 is pushed onto the stack.](images/ttinst_inset_p1_82.png)The projection\_vector is parallel to the line from (0,0) to (300,420)
### Sets Coordinate From the Stack using projection\_vector and freedom\_vector

| SCFS[ ] |  |
| --- | --- |
| Code Range | 0x48 |
| --- | --- |
| Pops | value: distance from origin to move point (F26Dot6) |
| --- | --- |
| - | p: point number (uint32) |
| --- | --- |
| Pushes | - |
| --- | --- |
| Uses | zp2, freedom\_vector, projection\_vector |
| --- | --- |

Moves point p from its current position along the freedom\_vector so that its component along the projection\_vector becomes the value popped off the stack.
![A value and a point number p are popped from the stack.](images/ttinst_inset_p1_83.png)
### Measure Distance

| MD[a] |  |
| --- | --- |
| Code Range | 0x49 - 0x4A |
| --- | --- |
| a | 0: measure distance in grid-fitted outline |
| --- | --- |
| - | 1: measure distance in original outline |
| --- | --- |
| Pops | p1: point number (uint32) |
| --- | --- |
| - | p2: point number (uint32) |
| --- | --- |
| Pushes | distance (F26Dot6) |
| --- | --- |
| Uses | zp1 with point p1, zp0 with point p2, projection\_vector |
| --- | --- |

Measures the distance between outline point p1 and outline point p2. The value returned is in pixels (F26Dot6) If distance is negative, it was measured against the projection vector. Reversing the order in which the points are listed will change the sign of the result.
![Point numbers p1 and p2 are popped from the stack, and a distance value is pushed onto the stack. For MD\[0\], the distance is determined from the original positions of p1 and p2. For MD\[1\], the distance is determined for p1 and p2 fitted to the grid.](images/ttinst_inset_p1_84.png)
*Example:*

In the illustration below MD[1] between points 25 and 31 will return a smaller value than MD[0] at 10 pixels per em on a 72 dpi device. The difference is due to the effects of grid-fitting which, at this size, stretches out the counter.
![The projection vector points in the direction of the x axis. The outline for the digit 8 is shown twice: first with original point positions, then with grid-fitted point positions.](images/ttinst_inset_p1_85.png)
### Measure Pixels Per EM

| MPPEM[ ] |  |
| --- | --- |
| Code Range | 0x4B |
| --- | --- |
| Pops | - |
| --- | --- |
| Pushes | ppem: pixels per em (uint32) |
| --- | --- |

This instruction pushes the number of pixels per em onto the stack. Pixels per em is a function of the resolution of the rendering device and the current point size and the current transformation matrix. This instruction looks at the projection\_vector and returns the number of pixels per em in that direction.
![The ppem value is pushed onto the stack.](images/ttinst_inset_p1_86.png)
### Measure Point Size

| MPS[ ] |  |
| --- | --- |
| Code Range | 0x4C |
| --- | --- |
| Pops | - |
| --- | --- |
| Pushes | pointSize: the size in points of the current glyph (F26Dot6) |
| --- | --- |

Pushes the current point size onto the stack.

Measure point size can be used to obtain a value which serves as the basis for choosing whether to branch to an alternative path through the instruction stream. It makes it possible to treat point sizes below or above a certain threshold differently
![The point size value is pushed onto the stack.](images/ttinst_inset_p1_87.png)![The raster bitmaps for lowercase g are shown at three sizes.](images/ttinst_inset_p1_88.png)12, 18, and 36 point Helvetica g at 72 dpi
## Managing outlines

The following set of instructions make it possible to move the points that make up a glyph outline. They are the instructions that accomplish the actual work of grid-fitting. They include instructions to move points, shift points or groups of points, flip points from off to on the curve or vice versa, and to interpolate points

### FLIP PoinT

| FLIPPT[ ] |  |
| --- | --- |
| Code Range | 0x80 |
| --- | --- |
| Pops | p: point number (uint32) |
| --- | --- |
| Pushes | - |
| --- | --- |
| Uses | loop, p is referenced in zp0 |
| --- | --- |

Flips points that are off the curve so that they are on the curve and points that are on the curve so that they are off the curve. The point is not marked as touched. The result of a FLIPPT instruction is that the contour describing part of a glyph outline is redefined
![A point number p is popped from the stack.](images/ttinst_inset_p2_01.png)![A point is located off a convex curve.](images/ttinst_inset_p2_02.png)*Before*![A point is located at the connection of two line segments.](images/ttinst_inset_p2_03.png)*After*
### FLIP RanGe ON

| FLIPRGON[ ] |  |
| --- | --- |
| Code Range | 0x81 |
| --- | --- |
| Pops | highpoint: highest point number in range of points to be flipped (uint32) |
| --- | --- |
| - | lowpoint: lowest point number in range of points to be flipped (uint32) |
| --- | --- |
| Pushes | - |
| --- | --- |

Flips a range of points beginning with lowpoint and ending with highpoint so that any off the curve points become on the curve points. The points are not marked as touched.
![A highpoint value is popped from the stack, then a lowpoint value is popped from the stack.](images/ttinst_inset_p2_04.png)
*Example:*
![Control points 1 to 5 define a convex curve, with points 1, 3 and 5 off the curve.](images/ttinst_inset_p2_05.png)*Before*![Control points 1 to 5 are all on curve points, and define two line segments connected at point 3.](images/ttinst_inset_p2_06.png)*After*
Will make all off curve points between point 0 and point 5 into on curve points as shown.

### FLIP RanGe OFF

| FLIPRGOFF[ ] |  |
| --- | --- |
| Code Range | 0x82 |
| --- | --- |
| Pops | highpoint: highest point number in range of points to be flipped (uint32) |
| --- | --- |
| - | lowpoint: lowest point number in range of points to be flipped (uint32) |
| --- | --- |
| Pushes | - |
| --- | --- |

Flips a range of points beginning with lowpoint and ending with highpoint so that any on the curve points become off the curve points. The points are not marked as touched.

*NOTE: This instruction changes the curve but the position of the points is unaffected. Accordingly, points affected by this instruction are not marked as touched.*
![Two values, highpoint and lowpoint, are popped from the stack.](images/ttinst_inset_p2_07.png)
*Example:*
![Control points 5 to 9 are all on curve points and define connected line segments.](images/ttinst_inset_p2_08.png)*Before*![Control points 5 and 9 are on cur points; points 6 to 8 are off curve. These define a contour passing through points 5 and 9.](images/ttinst_inset_p2_09.png)*After*
### SHift Point by the last point

| SHP[a] |  |
| --- | --- |
| Code Range | 0x32 - 0x33 |
| --- | --- |
| a | 0: uses rp2 in the zone pointed to by zp1 |
| --- | --- |
| - | 1: uses rp1 in the zone pointed to by zp0 |
| --- | --- |
| Pops | p: point to be shifted (uint32) |
| --- | --- |
| Pushes | - |
| --- | --- |
| Uses | zp0 with rp1 or zp1 with rp2 depending on flag |
| --- | --- |
| - | zp2 with point p |
| --- | --- |
| - | loop, freedom\_vector, projection\_vector |
| --- | --- |

Shift point p by the same amount that the reference point has been shifted. Point p is shifted along the freedom\_vector so that the distance between the new position of point p and the current position of point p is the same as the distance between the current position of the reference point and the original position of the reference point.

*NOTE: Point p is shifted from its current position, not its original position. The distance that the reference point has shifted is measured between its current position and the original position.*

In the illustration below rp is the original position of the reference point, rp' is the current position of the reference point, p is the original position of point p, p' is the current position, p" the position after it is shifted by the SHP instruction. (White indicates original position, gray is current position, black is position to which this instruction moves a point
![The freedom and projection vectors point in the direction of the x axis. A reference point rp is shown in its original position and its current position after it was shifted. Another point p is shown in its original position, its current position, and a new position after being shifted by the same amount the reference point was shifted.](images/ttinst_inset_p2_10.png)
### SHift Contour by the last point

| SHC[a] |  |
| --- | --- |
| Code Range | 0x34 - 0x35 |
| --- | --- |
| a | 0: uses rp2 in the zone pointed to by zp1 |
| --- | --- |
| - | 1: uses rp1 in the zone pointed to by zp0 |
| --- | --- |
| Pops | c: contour to be shifted (uint32) |
| --- | --- |
| Pushes | - |
| --- | --- |
| Uses | zp0 with rp1 or zp1 with rp2 depending on flag |
| --- | --- |
| - | zp2 with contour c |
| --- | --- |
| - | freedom\_vector, projection\_vector |
| --- | --- |

Shifts every point on contour c by the same amount that the reference point has been shifted. Each point is shifted along the freedom\_vector so that the distance between the new position of the point and the old position of that point is the same as the distance between the current position of the reference point and the original position of the reference point. The distance is measured along the projection\_vector. If the reference point is one of the points defining the contour, the reference point is not moved by this instruction.

This instruction is similar to SHP, but every point on the contour is shifted.

### SHift Zone by the last pt

| SHZ[a] |  |
| --- | --- |
| Code Range | 0x36 - 0x37 |
| --- | --- |
| a | 0: the reference point rp2 is in the zone pointed to by zp1 |
| --- | --- |
| - | 1: the reference point rp1 is in the zone pointed to by zp0 |
| --- | --- |
| Pops | e: zone to be shifted (uint32) |
| --- | --- |
| Pushes | - |
| --- | --- |
| Uses | zp0 with rp1 or zp1 with rp2 depending on flag |
| --- | --- |
| - | freedom\_vector, projection\_vector |
| --- | --- |

Shift the points in the specified zone (Z1 or Z0) by the same amount that the reference point has been shifted. The points in the zone are shifted along the freedom\_vector so that the distance between the new position of the shifted points and their old position is the same as the distance between the current position of the reference point and the original position of the reference point.

SHZ[a] uses zp0 with rp1 or zp1 with rp2. This instruction is similar to SHC, but all points in the zone are shifted, not just the points on a single contour.

### SHift point by a PIXel amount

| SHPIX[ ] |  |
| --- | --- |
| Code Range | 0x38 |
| --- | --- |
| Pops | amount: magnitude of the shift (F26Dot6) |
| --- | --- |
| - | p1, p2,...pn: points to be shifted (uint32) |
| --- | --- |
| Pushes | - |
| --- | --- |
| Uses | zp2, loop, freedom\_vector |
| --- | --- |

Shifts the points specified by the amount stated. When the loop variable is used, the amount to be shifted is put onto the stack only once. That is, if loop = 3, then the contents of the top of the stack should be point p1, point p2, point p3, amount. The value amount is expressed in sixty-fourths of a pixel.

SHPIX is unique in relying solely on the direction of the freedom\_vector. It makes no use of the projection\_vector. Measurement is made in the direction of the freedom\_vector.

*Example*

The instruction shifts points 27, 28, and 29 by 80/64 or 1.25 pixels in the direction of the freedom vector. The distance is measured in the direction of the freedom\_vector; the projection vector is ignored.

SHPIX[]
![The freedom vector points in the direction of the x axis; the projection vector is ignored. Points 27, 28 and 29 are moved 1.25 pixels in the x direction.](images/ttinst_inset_p2_11.png)
### Move Stack Indirect Relative Point

| MSIRP[a] |  |
| --- | --- |
| Code Range | 0x3A - 0x3B |
| --- | --- |
| a | 0: Do not set rp0 to p |
| --- | --- |
| - | 1: Set rp0 to p |
| --- | --- |
| Pops | d: distance (F26Dot6) |
| --- | --- |
| - | p: point number (uint32) |
| --- | --- |
| Pushes | - |
| --- | --- |
| Uses | zp1 with point p and zp0 with rp0, freedom\_vector, projection\_vector. |
| --- | --- |
| Sets | After it has moved the point this instruction sets rp1 = rp0, rp2 = point p, and if a=1, rp0 is set to point p. |
| --- | --- |

Makes the distance between a point p and rp0 equal to the value specified on the stack. The distance on the stack is in fractional pixels (F26Dot6). An MSIRP has the same effect as a MIRP instruction except that it takes its value from the stack rather than the Control Value Table. As a result, the cut\_in does not affect the results of a MSIRP. Additionally, MSIRP is unaffected by the round\_state.
![The freedom and projection vectors point in the direction of the x axis. A value d and a point number p are popped from the stack. Point p is moved right so that it is distance d along the projection vector from reference point rp0.](images/ttinst_inset_p2_12.png)
### Move Direct Absolute Point

| MDAP[a] |  |
| --- | --- |
| Code Range | 0x2E - 0x2F |
| --- | --- |
| a | 0: do not round the value |
| --- | --- |
| - | 1: round the value |
| --- | --- |
| Pops | p: point number (uint32) |
| --- | --- |
| Pushes | - |
| --- | --- |
| Sets | rp0 = rp1 = point p |
| --- | --- |
| Uses | zp0, round\_state, projection\_vector, freedom\_vector. |
| --- | --- |

Sets the reference points rp0 and rp1 equal to point p. If a=1, this instruction rounds point p to the grid point specified by the state variable round\_state. If a=0, it simply marks the point as touched in the direction(s) specified by the current freedom\_vector. This command is often used to set points in the twilight zone.
![Point number p is popped from the stack.](images/ttinst_inset_p2_13.png)
*Example:*

MDAP[0]

When a=0, the point is simply marked as touched and the values of rp0 and rp1 set to point p.
![The freedom and projection vectors point in the direction of the y axis. A point p is located within a design grid cell, not aligned to the grid. Reference points rp0 and rp1 are set to point p.](images/ttinst_inset_p2_14.png) MDAP[1] assuming that the round\_state is round to grid and the freedom\_vector is a shown. ![The freedom and projection vectors point in the direction of the y axis. A point p has an original position within a design grid cell, not aligned to the grid, but it is shifted down to the grid line. Reference points rp0 and rp1 are set to point p.](images/ttinst_inset_p2_15.png)
### Move Indirect Absolute Point

| MIAP[a] |  |
| --- | --- |
| Code Range | 0x3E - 0x3F |
| --- | --- |
| a | 0: don’t round the distance and don’t look at the control\_value\_cut\_in |
| --- | --- |
| - | 1: round the distance and look at the control\_value\_cut\_in |
| --- | --- |
| Pops | n: CVT entry number (uint32) |
| --- | --- |
| - | p: point number (uint32) |
| --- | --- |
| Pushes | - |
| --- | --- |
| Sets | rp0 = rp1 = point p |
| --- | --- |
| Uses | zp0, round\_state, control\_value\_cut\_in, freedom\_vector, projection\_vector |
| --- | --- |

Moves point p to the absolute coordinate position specified by the nth Control Value Table entry. The coordinate is measured along the current projection\_vector. If a=1, the position will be rounded as specified by round\_state. If a=1, and if the device space difference between the CVT value and the original position is greater than the control\_value\_cut\_in, then the original position will be rounded (instead of the CVT value.)

Rounding is done as if the entire coordinate system has been rotated to be consistent with the projection\_vector. That is, if round\_state is set to 1, and the projection\_vector and freedom\_vector are at a 45° angle to the x-axis, then a MIAP[1] of a point to 2.9 pixels will round to 3.0 pixels along the projection\_vector.

The a Boolean above controls both rounding and the use of the control\_value\_cut\_in. If you would like the meaning of this Boolean to specify only whether or not the MIAP[ ] instruction should look at the control\_value\_cut\_in value, use the ROFF[ ] instruction to turn off rounding.

This instruction can be used to create Twilight Zone points.

*Example:*

MIAP[1] 4 7

*case 1:*

rounding is OFF
![Freedom and projection vectors point in the direction of the y axis.](images/ttinst_inset_p2_16.png)
The point is moved to the position specified in the CVT.
![An entry in the Control Value Table at location 7 has a value of 13.6. A point is moved up so that its y coordinate is 13.6.](images/ttinst_inset_p2_17.png)
*case 2:*

The cut\_in test succeeds and rounding is RTG.

The value in the CVT is subjected to the rounding rule and then the point is moved to the rounded position.
![Freedom and projection vectors point in the direction of the y axis. An entry in the Control Value Table at location 7 has a value of 13.6. A point is moved up to y = 13.6, but then is moved further to y = 14.](images/ttinst_inset_p2_18.png)
*case 3:*

The cut\_in test fails and rounding is OFF.

Here the point is not moved.
![Freedom and projection vectors point in the direction of the y axis. An entry in the Control Value Table at location 7 has a value of 13.6. A point shown in the design grid is not moved.](images/ttinst_inset_p2_19.png)
*case 4:*

The cut\_in test fails and rounding is RTG.

In this case the point is moved to the nearest grid position.
![Freedom and projection vectors point in the direction of the y axis. An entry in the Control Value Table at location 7 has a value of 13.6. A point is moved up to a rounded y coordinate less than 13.6.](images/ttinst_inset_p2_20.png)
### Move Direct Relative Point

| MDRP[abcde] |  |
| --- | --- |
| Code Range | 0xC0 - 0xDF |
| --- | --- |
| a | 0: do not set rp0 to point p after move |
| --- | --- |
| - | 1: do set rp0 to point p after move |
| --- | --- |
| b | 0: do not keep distance greater than or equal to minimum\_distance |
| --- | --- |
| - | 1: keep distance greater than or equal to minimum\_distance |
| --- | --- |
| c | 0: do not round distance |
| --- | --- |
| - | 1: round the distance |
| --- | --- |
| de | distance type for engine characteristic compensation |
| --- | --- |
| Pops | p: point number (uint32) |
| --- | --- |
| Pushes | - |
| --- | --- |
| Sets | after point p is moved, rp1 is set equal to rp0, rp2 is set equal to point p; if the a flag is set to TRUE, rp0 is set equal to point |
| --- | --- |
| Uses | zp0 with rp0 and zp1 with point p, round\_state, single\_width\_value, single\_width\_cut\_in, freedom\_vector, projection\_vector. |
| --- | --- |

MDRP moves point p along the freedom\_vector so that the distance from its new position to the current position of rp0 is the same as the distance between the two points in the original uninstructed outline, and then adjusts it to be consistent with the Boolean settings. Note that it is only the original positions of rp0 and point p and the current position of rp0 that determine the new position of point p along the freedom\_vector.

MDRP is typically used to control the width or height of a glyph feature using a value which comes from the original outline. Since MDRP uses a direct measurement and does not reference the control\_value\_cut\_in, it is used to control measurements that are unique to the glyph being instructed. Where there is a need to coordinate the control of a point with the treatment of points in other glyphs in the font, a MIRP instruction is needed.

Though MDRP does not refer to the CVT, its effect does depend upon the single-width cut-in value. If the device space distance between the measured value taken from the uninstructed outline and the single\_width\_value is less than the single\_width\_cut\_in, the single\_width\_value will be used in preference to the outline distance. In other words, if the two distances are sufficiently close (differ by less than the single\_width\_cut\_in), the single\_width\_value will be used.

The setting of the round\_state Graphics State variable will determine whether and how the distance of point p from point q is rounded. If the round bit is not set, the value will be unrounded. If the round bit is set, the effect will depend upon the choice of rounding state. The value of the minimum distance variable is the smallest possible value the distance between two points can be rounded to.

Distances measured with the MDRP instruction must be either black, white or gray. Indicating this value in Booleans de allows the interpreter to compensate for engine characteristics as needed. The value de specifies the distance type as described in the [Instructing TrueType Glyphs](tt_instructing_glyphs) chapter. Three values are possible: Gray=0, Black=1, White=2.

*Example 1:*

Graphics State Settings
![Freedom and projection vectors point in the direction of the x axis.](images/ttinst_inset_p2_21.png)*Before MDRP*

| rp0 | 7 |
| --- | --- |
| rp1 | ? |
| rp2 | ? |

*Case 1:*
![Freedom and projection vectors point in the direction of the x axis when MDRP\[00001\] is processed.](images/ttinst_inset_p2_22.png)After MDRP[00001] 8

| rp0 | 7 |
| --- | --- |
| rp1 | 7 |
| rp2 | 8 |

*Case 2:*
![Freedom and projection vectors point in the direction of the x axis when MDRP\[10001\] is processed.](images/ttinst_inset_p2_22.png)After MDRP[10001] 8

| rp0 | 8 |
| --- | --- |
| rp1 | 7 |
| rp2 | 8 |

*Example 2:*

Point p is moved so that its distance from rp1 is the same as it was in the original outline.
![For example 2, the freedom and projection vectors point in the direction of the x axis.](images/ttinst_inset_p2_22.png)![Original positions of point p and reference point rp1 are shown. rp1 has been moved before this instruction is processed. Point p is moved so that its distance from rp1 along the x axis is the same as the original distance between p and rp1.](images/ttinst_inset_p2_23.png)
### Move Indirect Relative Point

| MIRP[abcde] |  |
| --- | --- |
| Code Range | 0xE0 - 0xFF |
| --- | --- |
| a | 0: Do not set rp0 to p |
| --- | --- |
| - | 1: Set rp0 to p |
| --- | --- |
| b | 0: Do not keep distance greater than or equal to minimum\_distance |
| --- | --- |
| - | 1: Keep distance greater than or equal to minimum\_distance |
| --- | --- |
| c | 0: Do not round the distance and do not look at the control\_value\_cut\_in |
| --- | --- |
| - | 1: Round the distance and look at the control\_value\_cut\_in value |
| --- | --- |
| de | distance type for engine characteristic compensation |
| --- | --- |
| Pops | n: CVT entry number (uint32) |
| --- | --- |
| - | p: point number (uint32) |
| --- | --- |
| Pushes | - |
| --- | --- |
| Uses | zp0 with rp0 and zp1 with point p. round\_state, control\_value\_cut\_in, single\_width\_value, single\_width\_cut\_in, freedom\_vector, projection\_vector |
| --- | --- |
| Sets | After it has moved the point this instruction sets rp1 = rp0, rp2 = point p, and if a = 1, rp0 is set to point p. |
| --- | --- |

A MIRP instruction makes it possible to preserve the distance between two points subject to a number of qualifications. Depending upon the setting of Boolean flag b, the distance can be kept greater than or equal to the value established by the minimum\_distance state variable. Similarly, the instruction can be set to round the distance according to the round\_state graphics state variable. The value of the minimum distance variable is the smallest possible value the distance between two points can be rounded to. Additionally, if the c Boolean is set, the MIRP instruction acts subject to the control\_value\_cut\_in. If the difference between the actual measurement and the value in the CVT is sufficiently small (less than the cut\_in\_value), the CVT value will be used and not the actual value. If the device space difference between this distance from the CVT and the single\_width\_value is smaller than the single\_width\_cut\_in, then use the single\_width\_value rather than the outline or Control Value Table distance.

MIRP measures distance relative to point rp0. More formally, MIRP moves point p along the freedom\_vector so that the distance from p to rp0 is equal to the distance stated in the reference CVT entry (assuming that the cut\_in test succeeds)

The c Boolean above controls both rounding and the use of Control Value Table entries. If you would like the meaning of this Boolean to specify only whether or not the MIRP[ ] instruction should look at the control\_value\_cut\_in, use the ROFF[ ] instruction to turn off rounding. In this manner, it is possible to specify rounding off and no cut\_in.

The value de specifies the distance type as described in the [Instructing TrueType Glyphs](tt_instructing_glyphs) chapter. Three values are possible: Gray=0, Black=1, White=2.

*Example 1:*

MIRP[00110] 3 17

*case 1:*

The cut\_in test succeeds and rounding is off.

The point is moved so that the distance from RP0 is equal to that given in CVT entry 17.
![Freedom and project vectors point in the direction of the x axis. An entry at location 17 in the Control Value Table has a value of 20.7. Original positions of a point and a reference point rp0 are shown. The other point is moved up so that its distance from rp0 along the y axis is 20.7 pixels.](images/ttinst_inset_p2_24.png)
*case 2:*

The cut\_in test succeeds and rounding is set to RTG.

The distance in the CVT is rounded and the point is moved by the rounded distance.
![Freedom and project vectors point in the direction of the x axis. An entry at location 17 in the Control Value Table has a value of 20.7. Original positions of a point and a reference point rp0 are shown. The other point is moved up so that its distance from rp0 along the y axis is 20.7 pixels, and then is further moved to a distinace of 21 pixels.](images/ttinst_inset_p2_25.png)
*case 3:*

The cut\_in test fails and the round\_state is OFF.

The point is not moved.
![Freedom and project vectors point in the direction of the x axis. An entry at location 17 in the Control Value Table has a value of 13.6. A point shown in the design grid is not moved.](images/ttinst_inset_p2_26.png)
*case 4:*

The cut\_in test fails and the round\_state is RTG.

The current position of the point is rounded to the grid.
![Freedom and project vectors point in the direction of the x axis. An entry at location 17 in the Control Value Table has a value of 13.6. A point is moved up to the next integral y coordinate.](images/ttinst_inset_p2_27.png)
### ALIGN Relative Point

| ALIGNRP[ ] |  |
| --- | --- |
| Code Range | 0x3C |
| --- | --- |
| Pops | p: point number (uint32)) |
| --- | --- |
| Pushes | - |
| --- | --- |
| Uses | zp1 with point p, zp0 with rp0, loop, freedom\_vector, projection\_vector. |
| --- | --- |

Reduces the distance between rp0 and point p to zero. Since distance is measured along the projection\_vector and movement is along the freedom\_vector, the effect of the instruction is to align points.
![A point number p is popped from the grid.](images/ttinst_inset_p2_28.png)
*case 1:*
![The projection and freedom vectors point in the direction of the x axis. A point p is moved right so that its distance from reference point rp0 along the projection vector is 0.](images/ttinst_inset_p2_29.png)
*case 2:*
![The projection and freedom vectors point in the direction of the y axis. A point p is moved down so that its distance from reference point rp0 along the projection vector is 0.](images/ttinst_inset_p2_30.png)
### Adjust Angle

This instruction is no longer supported.

### moves point p to the InterSECTion of two lines

| ISECT[ ] |  |
| --- | --- |
| Code Range | 0x0F |
| --- | --- |
| Pops | b1: end point of line 2 (uint32) |
| --- | --- |
| - | b0: start point of line 2 (uint32) |
| --- | --- |
| - | a1: end point of line 1 (uint32) |
| --- | --- |
| - | a0: start point of line 1 (uint32) |
| --- | --- |
| - | p: point to move (uint32) |
| --- | --- |
| Pushes | - |
| --- | --- |
| Uses | zp2 with point p, zp1 with line A, zp0 with line B |
| --- | --- |

Puts point p at the intersection of the lines A and B. The points a0 and a1 define line A. Similarly, b0 and b1 define line B. ISECT ignores the freedom\_vector in moving point p.
![Values b1, b0, a1 and a0 are popped from the stack, then point number p is popped from the stack.](images/ttinst_inset_p2_31.png)
*Example:*

ISECT[ ] 21 9 5 4 7
![Intersecting lines are shown from point 9 to point 5, and from point 4 to point 7. Point 21 is moved to the position where the two lines intersect.](images/ttinst_inset_p2_32.png)
If lines A and B are parallel, point p is moved to a position in the *middle* of the lines. That is:

px = (a0x + a1x)/4 + (b0x + b1x)/4 py = (a0y + a1y)/4 + (b0y + b1y)/4

*Example:*

ISECT[ ] 21 9 5 4 7
![Parallel lines are shown from point 9 to point 5, and from point 4 to point 7. Point 21 is moved to the position in the middle.](images/ttinst_inset_p2_33.png)
### ALIGN Points

| ALIGNPTS[ ] |  |
| --- | --- |
| Code Range | 0x27 |
| --- | --- |
| Pops | p1: point number (uint32) |
| --- | --- |
| - | p2: point number (uint32) |
| --- | --- |
| Pushes | - |
| --- | --- |
| Uses | zp1 with point p1, zp0 with point p2, freedom\_vector, projection\_vector. |
| --- | --- |

Makes the distance between point 1 and point 2 zero by moving both along the freedom\_vector to the average of both their projections along the projection\_vector.
![Point numberes p1 and p2 are popped from the stack.](images/ttinst_inset_p2_34.png)
*Example:*

ALIGNPTS[] 3 7
![Freedom and projection vectors point in the direction of the y axis. Point 3 is moved down and point 7 is moved up so they have the same y coordinate.](images/ttinst_inset_p2_35.png)
### Interpolate Point by the last relative stretch

| IP[ ] |  |
| --- | --- |
| Code Range | 0x39 |
| --- | --- |
| Pops | p: point number (uint32) |
| --- | --- |
| Pushes | - |
| --- | --- |
| Uses | zp0 with rp1, zp1 with rp2, zp2 with point p, loop, freedom\_vector, projection\_vector |
| --- | --- |

Moves point p so that its relationship to rp1 and rp2 is the same as it was in the original uninstructed outline. Measurements are made along the projection\_vector, and movement to satisfy the interpolation relationship is constrained to be along the freedom\_vector. This instruction is not valid if rp1 and rp2 have the same position on the projection\_vector.
![Freedom and projection vectors point in the direction of the x axis. A point number p is popped from the stack. Reference points rp1 and rp2 are moved right to new positions. Point p is moved right to a new position relative to new positions of rp1 and rp2.](images/ttinst_inset_p2_36.png)
In the example shown, assume that the points referenced by rp1 and rp2 are moved as shown. An IP instruction is then used to preserve their relative relationship with point p. After the IP the following should be true

- D(p, rp1)/D(p',rp1') = D(p,rp2)/D(p', rp2')

In other words, the relative distance is preserved.

### UnTouch Point

| UTP[ ] |  |
| --- | --- |
| Code Range | 0x29 |
| --- | --- |
| Pops | p: point number (uint32) |
| --- | --- |
| Pushes | - |
| --- | --- |
| Uses | zp0 with point p, freedom\_vector |
| --- | --- |

Marks point p as untouched. A point may be touched in the x direction, the y direction, both, or neither. This instruction uses the current freedom\_vector to determine whether to untouch the point in the x-direction, the y direction, or both. Points that are marked as untouched will be moved by an IUP (interpolate untouched points) instruction. Using UTP you can ensure that a point will be affected by IUP even if it was previously touched.

### Interpolate Untouched Points through the outline

| IUP[a] |  |
| --- | --- |
| Code Range | 0x30 - 0x31 |
| --- | --- |
| a | 0: interpolate in the y-direction |
| --- | --- |
| - | 1: interpolate in the x-direction |
| --- | --- |
| Pops | - |
| --- | --- |
| Pushes | - |
| --- | --- |
| Uses | zp2 |
| --- | --- |

Considers a glyph contour by contour, moving any untouched points in each contour that are between a pair of touched points. If the coordinates of an untouched point were originally between those of the touched pair, it is linearly interpolated between the new coordinates, otherwise the untouched point is shifted by the amount the nearest touched point is shifted.

This instruction operates on points in the glyph zone pointed to by zp2. This zone should almost always be zone 1. Applying IUP to zone 0 is an error.

Consider three consecutive points all on the same contour. Two of the three points, p1 and p3 have been touched. Point p2 is untouched. The effect of an IUP in the x-direction is to move point p2 so that is in the same relative position to points p1 and p3 before they were moved.

The IUP instruction does not touch the points it moves. Thus the untouched points affected by an IUP instruction will be affected by subsequent IUP instructions unless they are touched by an intervening instruction. In this case, the first interpolation is ignored and the point is moved based on its original position.
![Freedom and projection vectors point in the direction of the x axis. Points p1 and p3 have been moved to the right. Point p2 is then moved to the right.](images/ttinst_inset_p2_37.png)
## Managing exceptions

DELTA instructions can be used to alter the outline of a glyph at a particular size. They are generally used to turn on or off specific pixels. Delta instructions work by moving points (DELTAP’s) or by changing a value in the Control Value Table (DELTAC’s).

More formally, the DELTA instructions take a variable number of arguments from the stack and allow the use of an exception of the form: at size x apply the movement d to point p (or at size x add or subtract an amount less than or equal to the Control Value Table entry c). DELTAs take a list of exceptions of the form: relative ppem value, the magnitude of the exception and the point number to which the exception is to be applied.

Each DELTA instruction works on a range of sizes as specified below. As a result, sizes are specified in relative pixels per em (ppem), that is relative to the delta\_base. The default value for delta\_base is 9 ppem. To set delta\_base to another value, use the SDB instruction.

The DELTAP1 and DELTAC1 instructions allow values to be changed for glyphs at 9 through 24 ppem, assuming the default value for delta\_base. Lowering the value for delta\_base allows you to invoke exceptions at a smaller number of ppem.

DELTAP2 and DELTAC2 are triggered at 16 ppem higher than the value set for DELTAP1 and DELTAC1, and consequently the formula for the relative ppem is

ppem - 16 - delta\_base.

DELTAP3 and DELTAC3 are triggered at 16 ppem higher than the value set for DELTAP2 and DELTAC2, or 32 ppem higher than the value set for DELTAP1 and DELTAC1, and consequently the formula for the relative ppem is:

ppem - 32 - delta\_base.

| DELTA\*1 | delta\_base through delta\_base + 15 ppem |
| --- | --- |
| DELTA\*2 | delta\_base + 16 ppem through delta\_base + 31 ppem |
| DELTA\*3 | delta\_base + 32 ppem through delta\_base + 47 ppem |

In specifying a DELTA instruction, the high 4 bits of arg1 describe the relative ppem value that will activate the exception.

The low 4 bits of arg1 describe the magnitude of the exception. The amount the point moves is a function of the exception stated and the Graphics State variable delta\_shift. To set delta\_shift, use the SDS instruction
![Bits within a value are divided into to fields: high-order bits contain a relative ppem; the low-order bits contain a magnitude.](images/ttinst_inset_p2_38.png)*NOTE: Always observe that DELTA instructions expect the argument list to be sorted according to ppem. The lowest ppem should be deepest on the stack, and the highest ppem should be topmost on the stack. *
In the descriptions of the instructions that follow, pi is a point number, ci is a Control Value Table entry number and argi is a byte composed of two parts: the relative ppem (ppem - delta\_base) and the magnitude of the exception.

Increasing the delta\_shift will allow for more fine control over pixel movement at the sacrifice of total range of movement. A step is the minimal amount that a delta instruction can move a point. Points can be moved in integral multiples of steps.

The size of a step is 1 divided by 2 to the power delta\_shift. The range of movement produced by a given delta\_shift can be calculated by taking the number of steps allowed (16) and dividing it by 2 to the power delta\_shift. For example, a delta\_shift equal to 2 allows the smallest movement to be ± 1/4 pixel (because 2^2^ equals 4) and the largest movement to be ± 2 pixels (16/4 = 4 pixels of movement). A delta\_shift of 5 allows the smallest movement to be ± 1/32 pixel (because 2^5^ equals 32), but the largest movement is limited to ± 1/4 pixel. (16/32 = 1/2 a pixel of movement).

Internally, the value obtained for the exception is stored as a 4 bit binary number. As a result, the desired output range must be converted to a number between 0 and 15 before being converted to binary. Here is the internal remapping table for the DELTA instructions.

*NOTE: that zero is lacking in the output range.*

| Number of Steps | → Exception |
| --- | --- |
| -8 | 0 |
| -7 | 1 |
| -6 | 2 |
| -5 | 3 |
| -4 | 4 |
| -3 | 5 |
| -2 | 6 |
| -1 | 7 |
| 1 | 8 |
| 2 | 9 |
| 3 | 10 |
| 4 | 11 |
| 5 | 12 |
| 6 | 13 |
| 7 | 14 |
| 8 | 15 |

### DELTA exception P1

| DELTAP1[ ] |  |
| --- | --- |
| Code Range | 0x5D |
| --- | --- |
| Pops | n: number of pairs of exception specifications and points (uint32) |
| --- | --- |
| - | p1, arg1, p2, arg2, ..., pnn argn: n pairs of exception specifications and points (pairs of uint32s) |
| --- | --- |
| Pushes | - |
| --- | --- |
| Uses | zp0, delta\_base, delta\_shift |
| --- | --- |

DELTAP1 moves the specified points at the size and by the amount specified in the paired argument. An arbitrary number of points and arguments can be specified.

The grouping [pi, argi] can be executed n times. The value of argi may vary between iterations.

### DELTA exception P2

| DELTAP2[ ] |  |
| --- | --- |
| Code Range | 0x71 |
| --- | --- |
| Pops | n: number of pairs of exception specifications and points (uint32) |
| --- | --- |
| - | p1, arg1, p2, arg2, ..., pnn argn: n pairs of exception specifications and points (pairs of uint32s) |
| --- | --- |
| Pushes | - |
| --- | --- |
| Uses | zp0, delta\_shift, delta\_base |
| --- | --- |

DELTAP2 moves the specified points at the size and by the amount specified in the paired argument. An arbitrary number of points and arguments can be specified.

The grouping [pi, argi] can be executed n times. The value of argi may vary between iterations.

### DELTA exception P3

| DELTAP3[ ] |  |
| --- | --- |
| Code Range | 0x72 |
| --- | --- |
| Pops | n: number of pairs of exception specifications and points (uint32) |
| --- | --- |
| - | p1, arg1, p2, arg2, ..., pnn argn: n pairs of exception specifications and points (pairs of uint32s) |
| --- | --- |
| Pushes | - |
| --- | --- |
| Uses | zp0, delta\_base, delta\_shift |
| --- | --- |

DELTAP3 moves the specified points at the size and by the amount specified in the paired argument. An arbitrary number of point and arguments can be specified.

The grouping [pi, argi] can be executed n times. The value of argi may vary between iterations.

### DELTA exception C1

| DELTAC1[ ] |  |
| --- | --- |
| Code Range | 0x73 |
| --- | --- |
| Pops | n: number of pairs of exception specifications and CVT entry numbers (uint32) |
| --- | --- |
| - | c1, arg1, c2, arg2,..., cn, argn: (pairs of uint32s) |
| --- | --- |
| Pushes | - |
| --- | --- |

DELTAC1 changes the value in each CVT entry specified at the size and by the amount specified in its paired argument.

The grouping [ci, argi] can be executed n times. The value of argi may vary between iterations.

### DELTA exception C2

| DELTAC2[ ] |  |
| --- | --- |
| Code Range | 0x74 |
| --- | --- |
| Pops | n: number of pairs of exception specifications and CVT entry numbers (uint32) |
| --- | --- |
| - | c1, arg1, c2, arg2,..., cn, argn: (pairs of uint32s) |
| --- | --- |
| Pushes | - |
| --- | --- |

DELTAC2 changes the value in each CVT entry specified at the size and by the amount specified in its paired argument.

The grouping [ci, argi] can be executed n times. The value of argi may vary between iterations.

### DELTA exception C3

| DELTAC3[ ] |  |
| --- | --- |
| Code Range | 0x75 |
| --- | --- |
| Pops | n: number of pairs of exception specifications and CVT entry numbers (uint32) |
| --- | --- |
| - | c1, arg1, c2, arg2,..., cn, argn: (pairs of uint32s) |
| --- | --- |
| Pushes | - |
| --- | --- |

DELTAC3 changes the value in each CVT entry specified at the size and by the amount specified in its paired argument.

The grouping [ci, argi] can be executed n times. The value of argi may vary between iterations.

### Example of DELTA exceptions

Assume that you want to move point 15 of your glyph 1/8 of a pixel along the freedom\_vector at 12 pixels per em. Assume that delta\_base has the default value 9 and delta\_shift the default value 3.

To specify that the exception should be made at 12 ppem, you subtract the delta\_base, which is 9, from 12 and store the result, which is 3, in the high nibble of argi.

To specify that the point is to be moved 1/8 of a pixel, multiply 1/8 by 2 raised to the power delta\_shift. In other words, you multiply 1/8 by 2 raised to the third power (or 8)yielding 1. This value must be mapped to an internal value which using the table shown is 8.

Putting these two results together yields a 3 in the high nibble and an 8 in the low nibble or 56 (00111000, in binary).

To obtain this single exception, the top of the stack is: 56, 15, 1.

```
    (iteration)
    (point number)
    (arg1: ppem and magnitude)
```

Now if the interpreter executes

DELTAP1[ ]

then this instruction will move point 15 of the glyph (at 12 ppem) 1/8 of a pixel along the freedom\_vector.

## Managing the stack

The following set of instructions make it possible to manage elements on the stack. They make it possible to duplicate the element at the top of the stack, remove the top element from the stack, clear the stack, swap the top two stack elements, determine the number of elements currently on the stack, copy a specified element to the top of the stack, move a specified element to the top of the stack, and rearrange the order of the top three elements on the stack.

### Duplicate top stack element

| DUP[ ] |  |
| --- | --- |
| Code Range | 0x20 |
| --- | --- |
| Pops | e: stack element (uint32) |
| --- | --- |
| Pushes | e, e (two uint32s) |
| --- | --- |

Duplicates the element at the top of the stack.
![An element e is popped from the stack, then two instances of the element e are pushed onto the stack.](images/ttinst_inset_p2_39.png)
### POP top stack element

| POP[ ] |  |
| --- | --- |
| Code Range | 0x21 |
| --- | --- |
| Pops | e: stack element (uint32) |
| --- | --- |
| Pushes | - |
| --- | --- |

Pops the top element of the stack.
![An element e is popped from the stack.](images/ttinst_inset_p2_40.png)
### Clear the entire stack

| CLEAR[ ] |  |
| --- | --- |
| Code Range | 0x22 |
| --- | --- |
| Pops | all the items on the stack (uint32s) |
| --- | --- |
| Pushes | - |
| --- | --- |

Clears all elements from the stack.
![Elements en to e1 are popped from the stack.](images/ttinst_inset_p2_41.png)
### SWAP the top two elements on the stack

| SWAP[ ] |  |
| --- | --- |
| Code Range | 0x23 |
| --- | --- |
| Pops | e2: stack element (uint32) |
| --- | --- |
| - | e1: stack element (uint32) |
| --- | --- |
| Pushes | e1, e2 (pair of uint32s) |
| --- | --- |

Swaps the top two elements of the stack making the old top element the second from the top and the old second element the top element.
![Elements e2 then e1 are popped from the stack. Then, element e2 is pushed onto the stack, followed by element e1.](images/ttinst_inset_p2_42.png)
### Returns the DEPTH of the stack

| DEPTH[ ] |  |
| --- | --- |
| Code Range | 0x24 |
| --- | --- |
| Pops | - |
| --- | --- |
| Pushes | n: number of elements (uint32) |
| --- | --- |

Pushes n, the number of elements currently in the stack onto the stack.
![A value n is pushed onto the stack.](images/ttinst_inset_p2_43.png)
*Example:*
![A stack has three elements. The value 3 is then pushed onto the stack.](images/ttinst_inset_p2_44.png)
### Copy the INDEXed element to the top of the stack

| CINDEX[ ] |  |
| --- | --- |
| Code Range | 0x25 |
| --- | --- |
| Pops | k : stack element number |
| --- | --- |
| Pushes | ek: indexed element (uint32) |
| --- | --- |

Puts a copy of the kth stack element on the top of the stack.
![A value k is popped from the stack. Then, an element equal to the kth element is pushed onto the stack.](images/ttinst_inset_p2_45.png)
*Example:*
![The value 3 is popped from the stack, and four elements, e1 to e4, remain on the stack. An element equal to e3 is pushed onto the stack.](images/ttinst_inset_p2_46.png)
### Move the INDEXed element to the top of the stack

| MINDEX[ ] |  |
| --- | --- |
| Code Range | 0x26 |
| --- | --- |
| Pops | k : stack element number |
| --- | --- |
| Pushes | ek: indexed element |
| --- | --- |

Moves the indexed element to the top of the stack.
![A value k is popped from the stack. Then the kth element is pushed onto the stack.](images/ttinst_inset_p2_47.png)
MINDEX[ ]
![The value 3 is popped from the stack, and four elements, e1 to e4 remain on the stack. Then, element is pushed onto a modified stack containing elements e1, e2 and e4.](images/ttinst_inset_p2_48.png)
### ROLL the top three stack elements

| ROLL[ ] |  |
| --- | --- |
| Code Range | 0x8a |
| --- | --- |
| Pops | a, b, c (top three stack elements) |
| --- | --- |
| Pushes | b, a, c (elements reordered) |
| --- | --- |

Performs a circular shift of the top three objects on the stack with the effect being to move the third element to the top of the stack and to move the first two elements down one position. ROLL is equivalent to MINDEX[ ] 3.
![Elements a, b and c are popped from the stack. Then, the elements b, a and c are pushed onto the stack.](images/ttinst_inset_p2_49.png)
## Managing the flow of control

This section describes those instructions that make it possible to alter the sequence in which items in the instruction stream are executed. The IF and JMP instructions and their variants work by testing the value of an element on the stack and changing the value of the instruction pointer accordingly.

### IF test

| IF[ ] |  |
| --- | --- |
| Code Range | 0x58 |
| --- | --- |
| Pops | e: stack element (uint32) |
| --- | --- |
| Pushes | - |
| --- | --- |

Tests the element popped off the stack: if it is zero (FALSE), the instruction pointer is jumped to the next ELSE or EIF instruction in the instruction stream. If the element at the top of the stack is nonzero (TRUE), the next instruction in the instruction stream is executed. Execution continues until an ELSE instruction is encountered or an EIF instruction ends the IF. If an else statement is found before the EIF, the instruction pointer is moved to the EIF statement.

*case 1:*

Element at top of stack is TRUE; instruction pointer is unaffected. IF terminates with EIF.
![The IF\[\] instruction is processed. The value 1 is popped from the stack. The next instruction to be processed is the instruction immediately following the IF\[\] instruction.](images/ttinst_inset_p2_50.png)
*case 2:*

Element at top of stack is TRUE. The instruction stream is sequentially executed until ELSE is encountered whereupon the instruction pointer jumps to the EIF statement that terminates the IF.
![The IF\[\] instruction has been processed, and the value 1 was popped from the stack. Processing continued with instructions following IF\[\]. Then, the ELSE\[\] instruction is encountered. The instruction pointer skips following instructions until the EIF\[\] instruction.](images/ttinst_inset_p2_51.png)
*case 3:*

Element at the top of the stack is FALSE; instruction pointer is moved to the ELSE statement; instructions are then executed sequentially; EIF ends the IF statement.
![The IF\[\] instruction is processed, and the value 0 is popped from the stack. The instruction pointer skips instructions until the ELSE\[\] instruction is encountered. The following instructions are processed until the EIF\[\] instruction is encountered.](images/ttinst_inset_p2_52.png)
### ELSE

| ELSE[ ] |  |
| --- | --- |
| Code Range | 0x1B |
| --- | --- |
| Pops | - |
| --- | --- |
| Pushes | - |
| --- | --- |

Marks the start of the sequence of instructions that are to be executed if an IF instruction encounters a FALSE value on the stack. This sequence of instructions is terminated with an EIF instruction.

### End IF

| EIF[ ] |  |
| --- | --- |
| Code Range | 0x59 |
| --- | --- |
| Pops | - |
| --- | --- |
| Pushes | - |
| --- | --- |

Marks the end of an IF[ ] instruction.

### Jump Relative On True

| JROT[ ] |  |
| --- | --- |
| Code Range | 0x78 |
| --- | --- |
| Pops | e: stack element (uint32) |
| --- | --- |
| - | offset: number of bytes to move instruction pointer (int32) |
| --- | --- |
| Pushes | - |
| --- | --- |

Pops and tests the element value, and then pops the offset. If the element value is non-zero (TRUE), the signed offset will be added to the instruction pointer and execution will be resumed at the address obtained. Otherwise, the jump is not taken and the next instruction in the instruction stream is executed. The jump is relative to the position of the instruction itself. That is, the instruction pointer is still pointing at the JROT[ ] instruction when offset is added to obtain the new address.
![An element e is popped from the stack, then an offset is popped from the stack.](images/ttinst_inset_p2_57.png)
*Example:*

*case 1:*

Boolean is FALSE.
![The JROT\[\] instruction is processed. The values 0 and 4 are popped from the stack. Processing continues with the instruction following the JROT instruction.](images/ttinst_inset_p2_54.png)
*case 2:*

Boolean is TRUE.
![he JROT\[\] instruction is processed. The values 1 and 4 are popped from the stack. The instruction pointer skips to the 4th instruction after the JROT instruction, and processing continues.](images/ttinst_inset_p2_55.png)
### JuMP

| JMPR[ ] |  |
| --- | --- |
| Code Range | 0x1C |
| --- | --- |
| Pops | offset: number of bytes to move instruction pointer (int32) |
| --- | --- |
| Pushes | - |
| --- | --- |

The signed offset is added to the instruction pointer and execution is resumed at the new location in the instruction steam. The jump is relative to the position of the instruction itself. That is, the instruction pointer is still pointing at the JROT[ ] instruction when offset is added to obtain the new address.
![An offset is popped from the stack.](images/ttinst_inset_p2_56.png)
### Jump Relative On False

| JROF[ ] |  |
| --- | --- |
| Code Range | 0x79 |
| --- | --- |
| Pops | e: stack element (uint32) |
| --- | --- |
| - | offset: number of bytes to move instruction pointer (int32) |
| --- | --- |
| Pushes | - |
| --- | --- |

Pops and tests the element value, and then pops the offset. If the element value is zero (FALSE), the signed offset will be added to the instruction pointer and execution will be resumed at the address obtainted. Otherwise, the jump is not taken and the next instruction in the instruction stream is executed. The jump is relative to the position of the instruction itself. That is, the instruction pointer is still pointing at the JROT[ ] instruction when the offset is added to obtain the new address.
![An element e is popped from the stack, then an offset is popped from the stack.](images/ttinst_inset_p2_57.png)
*case 1:*

element is FALSE.
![The instruction JROF\[\] is processed. The values 0 and 4 are popped from the stack. The instruction pointer skips to the 4th instruction after the JROF instruction, and processing continues.](images/ttinst_inset_p2_58.png)
*case 2:*

element is TRUE.
![The JROF\[\] instruction is processed. The values 1 and 4 are popped from the stack. Processing continues with the instruction following the JROF instruction.](images/ttinst_inset_p2_59.png)
## Logical functions

The TrueType instruction set includes a set of logical functions that can be used to test the value of a stack element or to compare the values of two stack elements. The logical functions compare 32 bit values (uint32) and return a Boolean value to the top of the stack.

To easily remember the order in which stack values are handled during logical operations, imagine writing the stack values from left to right, starting with the bottom value. Then insert the operator between the two furthest right elements. For example:
![A stack contains elements a, b and c.](images/ttinst_inset_p2_60.png)
GT a,b would be interpreted as (b&gt;a):

c b &gt; a

### Less Than

| LT[ ] |  |
| --- | --- |
| Code Range | 0x50 |
| --- | --- |
| Pops | e2: stack element (uint32) |
| --- | --- |
| - | e1: stack element (uint32) |
| --- | --- |
| Pushes | Boolean value (uint32 in the range [0,1]) |
| --- | --- |

First pops e2, then pops e1 off the stack and compares them: if e1 is less than e2, 1, signifying TRUE, is pushed onto the stack. If e1 is not less than e2, 0, signifying FALSE, is placed onto the stack.
![Elements e2, then e1, are popped from the stack, then a boolean value is pushed onto the stack.](images/ttinst_inset_p2_61.png)
*Example:*

LT[ ]
![The values 15 and 20 are popped from the stack, then the value 0 (false) is pushed onto the stack.](images/ttinst_inset_p2_62.png)
### Less Than or Equal

| LTEQ[ ] |  |
| --- | --- |
| Code Range | 0x51 |
| --- | --- |
| Pops | e2: stack element (uint32) |
| --- | --- |
| - | e1: stack element (uint32) |
| --- | --- |
| Pushes | Boolean value (uint32 in the range [0,1]) |
| --- | --- |

Pops e2 and e1 off the stack and compares them. If e1 is less than or equal to e2, 1, signifying TRUE, is pushed onto the stack. If e1 is not less than or equal to e2, 0, signifying FALSE, is placed onto the stack.
![Two elements are popped from the stack: e2, then e1. A boolean value is pushed onto the stack.](images/ttinst_inset_p2_63.png)
*Example:*

LTEQ[ ]
![Two values, 20 and 20, are popped from the stack. The value 1 (true) is pushed onto the stack.](images/ttinst_inset_p2_64.png)
### Greater Than

| GT[ ] |  |
| --- | --- |
| Code Range | 0x52 |
| --- | --- |
| Pops | e2: stack element (uint32) |
| --- | --- |
| - | e1: stack element (uint32) |
| --- | --- |
| Pushes | Boolean value (uint32 in the range [0,1]) |
| --- | --- |

**First pops e2 then pops e1 off the stack** and compares them. If e1 is greater than e2, 1, signifying TRUE, is pushed onto the stack. If e1 is not greater than e2, 0, signifying FALSE, is placed onto the stack.
![Elements e2, then e1, are popped from the stack. A boolean value is pushed onto the stack.](images/ttinst_inset_p2_65.png)
*Example:*

GT[ ]
![Two values, 20 and 20, are popped from the stack. The value 0 (false) is pushed onto the stack.](images/ttinst_inset_p2_66.png)
### Greater Than or Equal

| GTEQ[ ] |  |
| --- | --- |
| Code Range | 0x53 |
| --- | --- |
| Pops | e2: stack element (uint32) |
| --- | --- |
| - | e1: stack element (uint32) |
| --- | --- |
| Pushes | Boolean value (uint32 in the range [0,1]) |
| --- | --- |

Pops e1 and e2 off the stack and compares them. If e1 is greater than or equal to e2, 1, signifying TRUE, is pushed onto the stack. If e1 is not greater than or equal to e2, 0, signifying FALSE, is placed onto the stack.
![Elements e2, then e1, are popped from the stack. Then, a boolean value is pushed onto the stack.](images/ttinst_inset_p2_67.png)
*Example:*

GTEQ[ ]
![The values 15 and 20 are popped from the stack. Then the value 1 (true) is pushed onto the stack.](images/ttinst_inset_p2_68.png)
### EQual

| EQ[ ] |  |
| --- | --- |
| Code Range | 0x54 |
| --- | --- |
| Pops | e2: stack element (uint32) |
| --- | --- |
| - | e1: stack element (uint32) |
| --- | --- |
| Pushes | Boolean value (uint32 in the range [0,1]) |
| --- | --- |

Pops e1 and e2 off the stack and compares them. If they are equal, 1, signifying TRUE is pushed onto the stack. If they are not equal, 0, signifying FALSE is placed onto the stack.
![Elements e1 and e2 are popped from the stack. A boolean value is pushed onto the stack.](images/ttinst_inset_p2_69.png)
*Example:*

EQ[ ]
![The values 20 and -12 are popped from the stack. Then the value 0 (false) is pushed onto the stack.](images/ttinst_inset_p2_70.png)
### Not EQual

| NEQ[ ] |  |
| --- | --- |
| Code Range | 0x55 |
| --- | --- |
| Pops | e2: stack element (uint32) |
| --- | --- |
| - | e1: stack element (uint32) |
| --- | --- |
| Pushes | Boolean value (uint32 in the range [0,1]) |
| --- | --- |

Pops e1 and e2 from the stack and compares them. If they are not equal, 1, signifying TRUE, is pushed onto the stack. If they are equal, 0, signifying FALSE, is placed on the stack.
![Elements e1 and e2 are popped from the stack. Then, a boolean value is pushed onto the stack.](images/ttinst_inset_p2_71.png)
*Example:*

NEQ[ ]
![The values 20 and -12 are popped from the stack. Then the value 1 (true) is pushed onto the stack.](images/ttinst_inset_p2_72.png)
### ODD

| ODD[ ] |  |
| --- | --- |
| Code Range | 0x56 |
| --- | --- |
| Pops | e1: stack element (F26Dot6) |
| --- | --- |
| - | Boolean value |
| --- | --- |
| Pushes | Boolean value (uint32 in the range [0,1]) |
| --- | --- |
| Uses | round\_state |
| --- | --- |

Tests whether the number at the top of the stack is odd. Pops e1 from the stack and rounds it as specified by the round\_state before testing it. After the value is rounded, it is shifted from a fixed point value to an integer value (any fractional values are ignored). If the integer value is odd, one, signifying TRUE, is pushed onto the stack. If it is even, zero, signifying FALSE is placed onto the stack.
![An element e1 is popped from the stack. Then a boolean value is pushed onto the stack.](images/ttinst_inset_p2_73.png)
*Example:*

ODD[ ]

This example assumes that round\_state is RTG.
![The value 22.7 is popped from the stack, and the value 1 (true) is pushed onto the stack.](images/ttinst_inset_p2_74.png)
### EVEN

| EVEN[ ] |  |
| --- | --- |
| Code Range | 0x57 |
| --- | --- |
| Pops | e1: stack element (F26Dot6) |
| --- | --- |
| Pushes | Boolean value (uint32 in the range [0,1]) |
| --- | --- |
| Uses | round\_state |
| --- | --- |

Tests whether the number at the top of the stack is even. Pops e1 off the stack and rounds it as specified by the round\_state before testing it. If the rounded number is even, one, signifying TRUE, is pushed onto the stack if it is odd, zero, signifying FALSE, is placed onto the stack.
![An element e1 is popped from the stack, and a boolean value is pushed onto the stack.](images/ttinst_inset_p2_75.png)
*Example:*

EVEN[ ]

This example assumes that round\_state is RTG.
![The value 22.7 is popped from the stack, and the value 0 (false) is pushed onto the stack.](images/ttinst_inset_p2_76.png)
### logical AND

| AND[ ] |  |
| --- | --- |
| Code Range | 0x5A |
| --- | --- |
| Pops | e1: stack element (uint32) |
| --- | --- |
| - | e2: stack element (uint32) |
| --- | --- |
| Pushes | ( e1 and e2 ): logical and of e1 and e2 (uint32) |
| --- | --- |

Pops e1 and e2 off the stack and pushes onto the stack the result of a logical and of the two elements. Zero is returned if either or both of the elements are FALSE (have the value zero). One is returned if both elements are TRUE (have a non zero value).
![Elements e1 and e2 are popped from the stack. A value equal to logical and of e1 and e2 is pushed onto the stack.](images/ttinst_inset_p2_77.png)
*Example:*

*case 1:*

AND[ ]
![The values 1 and 33 are popped from the stack, and the value 1 (true) is pushed onto the stack.](images/ttinst_inset_p2_78.png)
*case 2:*

AND[ ]
![The values 1 and 0 are popped from the stack, and the value 0 (false) is pushed onto the stack.](images/ttinst_inset_p2_79.png)
### logical OR

| OR[ ] |  |
| --- | --- |
| Code Range | 0x5B |
| --- | --- |
| Pops | e1: stack element (uint32) |
| --- | --- |
| - | e2: stack element (uint32) |
| --- | --- |
| Pushes | ( e1 or e2 ): logical or of e1 and e2 (uint32) |
| --- | --- |

Pops e1 and e2 off the stack and pushes onto the stack the result of a logical or operation between the two elements. Zero is returned if both of the elements are FALSE. One is returned if either one or both of the elements are TRUE (has a nonzero value).
![Elements e1 and e2 are popped from the stack. A value equal to logical or of e1 and e2 is pushed onto the stack.](images/ttinst_inset_p2_80.png)
*Example:*

*case 1:*

OR[ ]
![The values 44 and 0 are popped from the stack, and the value 1 (true) is pushed onto the stack.](images/ttinst_inset_p2_81.png)
*case 2:*

OR[ ]
![The values 0 and 0 are popped from the stack, and the value 0 (false) is pushed onto the stack.](images/ttinst_inset_p2_82.png)
### logical NOT

| NOT[ ] |  |
| --- | --- |
| Code Range | 0x5C |
| --- | --- |
| Pops | e: stack element (uint32) |
| --- | --- |
| Pushes | (not e): logical negation of e (uint32) |
| --- | --- |

Pops e off the stack and returns the result of a logical NOT operation performed on e. If originally zero, one is pushed onto the stack if originally nonzero, zero is pushed onto the stack.
![An element e is poppoed from the stack, and a value equal to not e is pushed onto the stack.](images/ttinst_inset_p2_83.png)
*Example:*

*case 1:*
![The value 42.1 is popped from the stack, and the value 0 (false) is pushed onto the stack.](images/ttinst_inset_p2_84.png)
*case 2:*
![The value 0 is popped from the stack, and the value 1 (true) is pushed onto the stack.](images/ttinst_inset_p2_85.png)
## Arithmetic and math instructions

These instructions perform arithmetic on stack values. Values are treated as signed (two’s complement) 26.6 fixed-point numbers (F26Dot6) and give results in the same form. There is no overflow or underflow protection for these instructions.

To easily remember the order in which stack values are handled during arithmetic operations, imagine writing the stack values from left to right, starting with the bottom value. Then insert the operator between the two furthest right elements. For example:
![A stack contains values a, b and c.](images/ttinst_inset_p2_86.png)
*subtract* a,b would be interpreted as (b-a): c b - a

### ADD

| ADD[ ] |  |
| --- | --- |
| Code Range | 0x60 |
| --- | --- |
| Pops | n1, n2 (F26Dot6) |
| --- | --- |
| Pushes | (n2 + n1) |
| --- | --- |

Pops n1 and n2 off the stack and pushes the sum of the two elements onto the stack.
![Values n1 and n2 are popped from the stack, and a value equal to n2 + n1 is pushed onto the stack.](images/ttinst_inset_p2_87.png)
### SUBtract

| SUB[ ] |  |
| --- | --- |
| Code Range | 0x61 |
| --- | --- |
| Pops | n1, n2 (F26Dot6) |
| --- | --- |
| Pushes | (n2 - n1): difference |
| --- | --- |

Pops n1 and n2 off the stack and pushes the difference between the two elements onto the stack.
![Values n1 and n2 are popped from the stack, and a value equal to n2 - n1 is pushed onto the stack.](images/ttinst_inset_p2_88.png)
### DIVide

| DIV[ ] |  |
| --- | --- |
| Code Range | 0x62 |
| --- | --- |
| Pops | n1: divisor (F26Dot6) |
| --- | --- |
| - | n2: dividend (F26Dot6) |
| --- | --- |
| Pushes | n2/n1 (F26Dot6) |
| --- | --- |

Pops n1 and n2 off the stack and pushes onto the stack the quotient obtained by dividing n2 by n1. Note that this truncates rather than rounds the value. The TrueType Rasterizer v.1.7 and later will catch any division-by-zero errors.
![Values n1 and n2 are popped from the stack, and a value equal to n2/n1 is pushed onto the stack.](images/ttinst_inset_p2_89.png)
### MULtiply

| MUL[ ] |  |
| --- | --- |
| Code Range | 0x63 |
| --- | --- |
| Pops | n1, n2: multiplier and multiplicand (F26Dot6) |
| --- | --- |
| Pushes | n1 &ast; n2 (F26Dot6) |
| --- | --- |

Pops n1 and n2 off the stack and pushes onto the stack the product of the two elements.
![Values n1 and n2 are popped from the stack, and a value equal to n2 * n1 is pushed onto the stack.](images/ttinst_inset_p2_90.png)
### ABSolute value

| ABS[ ] |  |
| --- | --- |
| Code Range | 0x64 |
| --- | --- |
| Pops | n |
| --- | --- |
| Pushes | |n|: absolute value of n (F26Dot6) |
| --- | --- |

Pops n off the stack and pushes onto the stack the absolute value of n.
![A value n is popped from the stack, and a value equal to the absolute value of n is pushed onto the stack.](images/ttinst_inset_p2_91.png)
*Example:*

*case 1:*
![The value -21.1 is popped from the stack, and the value 21.1 is pushed onto the stack.](images/ttinst_inset_p2_92.png)
*case 2:*
![The value 14.0 is popped from the stack, and the value 14.0 is pushed onto the stack.](images/ttinst_inset_p2_93.png)
### NEGate

| NEG[ ] |  |
| --- | --- |
| Code Range | 0x65 |
| --- | --- |
| Pops | n1 |
| --- | --- |
| Pushes | -n1: negation of n1 (F26Dot6) |
| --- | --- |

This instruction pops n1 off the stack and pushes onto the stack the negated value of n1.
![A value n is popped from the stack, and a value equal to -n is pushed onto the stack.](images/ttinst_inset_p2_94.png)
NEG[ ]
![The value 44.66 is popped from the stack, and the value -44.66 is pushed onto the stack.](images/ttinst_inset_p2_95.png)
### FLOOR

| FLOOR[ ] |  |
| --- | --- |
| Code Range | 0x66 |
| --- | --- |
| Pops | n1: number whose floor is desired (F26Dot6) |
| --- | --- |
| Pushes | n : floor of n1 (F26Dot6) |
| --- | --- |

Pops n1 and returns n, the greatest integer value less than or equal to n1.
![A value n1 is popped from the stack, and a value n is pushed onto the stack.](images/ttinst_inset_p2_96.png)
*Example:*

FLOOR[ ]

*case 1:*
![The value 15.8 is popped from the stack, and the value 15 is pushed onto the stack.](images/ttinst_inset_p2_97.png)
*case 2:*
![The value 15.3 is popped from the stack, and the value 15 is pushed onto the stack.](images/ttinst_inset_p2_98.png)
*case 3:*
![The value -0.8 is popped from the stack, and the value -1 is pushed onto the stack.](images/ttinst_inset_p2_99.png)
### CEILING

| CEILING[ ] |  |
| --- | --- |
| Code Range | 0x67 |
| --- | --- |
| Pops | n1: number whose ceiling is desired (F26Dot6) |
| --- | --- |
| Pushes | n: ceiling of n1 (F26Dot6) |
| --- | --- |

Pops n1 and returns n, the least integer value greater than or equal to n1. For instance, the ceiling of 15 is 15, but the ceiling of 15.3 is 16. The ceiling of -0.8 is 0. (n is the least integer value greater than or equal to n1)
![A value n1 is popped from the stack. A value n is pushed onto the stack.](images/ttinst_inset_p2_100.png)
*Example:*

CEILING[ ]

*case 1:*
![The value 223.0 is popped from the stack, and the value 223.0 is pushed onto the stack.](images/ttinst_inset_p2_101.png)
*case 2:*
![The value 223.3 is popped from the stack, and the value 224.0 is pushed onto the stack.](images/ttinst_inset_p2_102.png)
### MAXimum of top two stack elements

| MAX[ ] |  |
| --- | --- |
| Code Range | 0x8B |
| --- | --- |
| Pops | e1: stack element (uint32) |
| --- | --- |
| - | e2: stack element (uint32) |
| --- | --- |
| Pushes | maximum of e1 and e2 |
| --- | --- |

Pops two elements, e1 and e2, from the stack and pushes the larger of these two quantities onto the stack.
![Elements e1 and e2 are popped from the stack. A value equal to the maximum of e1 and e2 is pushed onto the stack.](images/ttinst_inset_p2_103.png)
### MINimum of top two stack elements

| MIN[ ] |  |
| --- | --- |
| Code Range | 0x8C |
| --- | --- |
| Pops | e1: stack element (uint32) |
| --- | --- |
| - | e2: stack element (uint32) |
| --- | --- |
| Pushes | minimum of e1 and e2 |
| --- | --- |

Pops two elements, e1 and e2, from the stack and pushes the smaller of these two quantities onto the stack.
![Elements e1 and e2 are popped from the stack. A value equal to the minimum of e1 and e2 is pushed onto the stack.](images/ttinst_inset_p2_104.png)
## Compensating for the engine characteristics

The following two functions make it possible to compensate for the engine characteristic. Each takes value and make the compensation. In addition to the engine compensation, ROUND, rounds the value according to the round\_state. NROUND only compensates for the engine.

### ROUND value

| ROUND[ab] |  |
| --- | --- |
| Flags | ab: distance type for engine characteristic compensation |
| --- | --- |
| Pops | n1 |
| --- | --- |
| Pushes | n2 |
| --- | --- |
| Code | 0x68 - 0x6B |
| --- | --- |

Rounds a value according to the state variable round\_state while compensating for the engine. n1 is popped off the stack and, depending on the engine characteristics, is increased or decreased by a set amount. The number obtained is then rounded and pushed back onto the stack as n2.

The value ab specifies the distance type as described in the [Instructing TrueType Glyphs](tt_instructing_glyphs) chapter. Three values are possible: Gray=0, Black=1, White=2.

### No ROUNDing of value

| NROUND[ab] |  |
| --- | --- |
| Flags | ab: distance type for engine characteristic compensation |
| --- | --- |
| Pops | n1 |
| --- | --- |
| Pushes | n2 |
| --- | --- |
| Code | 0x6C - 0x6F |
| --- | --- |

NROUND[ab] does the same operation as ROUND[ab] (above), except that it does not round the result obtained after compensating for the engine characteristics. n1 is popped off the stack and, depending on the engine characteristics, increases or decreases by a set amount. This figure is then pushed back onto the stack as n2.

The value ab specifies the distance type as described in the [Instructing TrueType Glyphs](tt_instructing_glyphs) chapter. Three values are possible: Gray=0, Black=1, White=2.

## Defining and using functions and instructions

The following instructions make it possible to define and use both functions and new instructions.

In addition to a simple call function, there is a loop and call function.

An IDEF or instruction definition call makes it possible to patch old scalers in order to add newly defined instructions.

### Function DEFinition

| FDEF[ ] |  |
| --- | --- |
| Code Range | 0x2C |
| --- | --- |
| Pops | f: function identifier number (integer in the range 0 to n-1 where n is specified in the 'maxp' table ) |
| --- | --- |
| Pushes | - |
| --- | --- |

Marks the start of a function definition. The argument f is a number that uniquely identifies this function. A function definition can appear only in the Font Program or the CVT program. Functions may not exceed 64K in size
![A function identifier f is popped from the stack.](images/ttinst_inset_p2_105.png)
### END Function definition

| ENDF[ ] |  |
| --- | --- |
| Code Range | 0x2D |
| --- | --- |
| Pops | - |
| --- | --- |
| Pushes | - |
| --- | --- |

Marks the end of a function definition or an instruction definition.

### CALL function

| CALL[ ] |  |
| --- | --- |
| Code Range | 0x2B |
| --- | --- |
| Pops | f: function identifier number (integer in the range 0 to n-1 where n is specified in the 'maxp' table ) |
| --- | --- |
| Pushes | - |
| --- | --- |

Calls the function identified by the number f.
![The function identifier f is popped from the stack.](images/ttinst_inset_p2_105.png)
### LOOP and CALL function

| LOOPCALL[ ] |  |
| --- | --- |
| Code Range | 0x2A |
| --- | --- |
| Pops | f: function number integer in the range 0 to n-1 where n is specified in the 'maxp' table |
| --- | --- |
| - | count: number of times to call the function (signed word) |
| --- | --- |
| Pushes | - |
| --- | --- |

Calls the function f, count number of times.
![A function identifier f and a count are popped from the stack.](images/ttinst_inset_p2_106.png)
*Example:*

Assume the Font Program contains this:

```
PUSHB[000]   17    /* push 17 onto the stack */
FDEF[ ]            /* start defining function 17 */
/*
   contents of function
*/
ENDF[ ]            /* end the function definition */
PUSHB[000]    5    /* push count */
PUSHB[000]   17    /* push function number */
LOOPCALL[ ]        /* call function 17, 5 times */
```

### Instruction DEFinition

| IDEF[ ] |  |
| --- | --- |
| Code Range | 0x89 |
| --- | --- |
| Pops | opcode (8 bit code padded with zeroes to uint32) |
| --- | --- |
| Pushes | - |
| --- | --- |

Begins the definition of an instruction. The instruction definition terminates when at ENDF, which is encountered in the instruction stream. Subsequent executions of the opcode popped will be directed to the contents of this instruction definition (IDEF). IDEFs should be defined in the Font Program or the CVT Program. An IDEF affects only undefined opcodes. If the opcode in question is already defined, the interpreter will ignore the IDEF. This is to be used as a patching mechanism for future instructions. Instructions may not exceed 64K in size.

## Debugging

The TrueType instruction set provides the following instruction as an aid to debugging.

### DEBUG call

| DEBUG[ ] |  |
| --- | --- |
| Code Range | 0x4F |
| --- | --- |
| Pops | number (uint32) |
| --- | --- |
| Pushes | - |
| --- | --- |

This instruction is only for debugging purposes and should not be a part of a finished font. Some implementations may not support this instruction.
![A number is popped from the stack.](images/ttinst_inset_p2_107.png)
## Miscellaneous instructions

The following instruction obtains information about the current glyph and the scaler version.

### GET INFOrmation

| GETINFO[ ] |  |
| --- | --- |
| Code Range | 0x88 |
| --- | --- |
| Pops | selector (integer) |
| --- | --- |
| Pushes | result (integer) |
| --- | --- |

GETINFO is used to obtain data about the font scaler version and the characteristics of the current glyph. The instruction pops a selector used to determine the type of information desired and pushes a result onto the stack.

Selector bit 0 indicates that the scaler version number is the desired information. Selector bit 1 indicates a request for glyph rotation status. Selector bit 2 asks whether the glyph has been stretched. Selector bit 3 asks if OpenType Font Variations are supported. Selector bit 4 asks if vertical phantom points are being used. Selector bit 5 asks whether the glyph is being rasterized for grayscale.

Selector bit 3 indicates a query as to whether or not OpenType Font Variations are supported. The result is returned in bit 10: if bit 10 is set, Font Variations are supported.

Selector bit 4 indicates a query as to whether vertical phantom points are supported. The result is returned in bit 11: if bit 11 is set, vertical phantom points are supported. **Note:** on MS Rasterizer, this method is not supported until MS Rasterizer 2.2 — version number 41 or later. For versions prior to version 41, see the note below.

The following selectors are for ClearType information. Selector bit 6 indicates that ClearType is enabled. Selector bit 7 indicates that “compatible-width” ClearType is enabled. Selector bit 8 indicates that symmetrical smoothing ClearType is enabled. And, selector bit 9 indicates that ClearType is processing the LCD stripes in BGR (Blue, Green, Red) order.

The result pushed onto the stack contains the requested information. More precisely, bits 0 through 7 comprise the Scaler version number. Refer to the table below for the meaning of the version numbers. Version numbers 0, 4 through 32, and 43 through 255 are reserved.

**Note:** On MS Rasterizer, selector bit 4 could not be reliably used to query for support of vertical phantom points prior to MS Rasterizer v.2.2, though support for vertical phantom points was added in MS Rasterizer v.1.7. Before hinting vertical phantom points or asking for grayscale information, use GETINFO to check that the rasterizer in use is version number 35 or later. Before checking if ClearType is enabled, make sure that the rasterizer is version number is 36 or greater. For the other ClearType bits, make sure that the rasterizer is version number 37 or greater.

Bit 8 is set to 1 if the current glyph has been rotated. It is zero otherwise.

Bit 9 is set to 1 if the current glyph has been stretched. It is set to 0 otherwise.

Bit 10 is set to 1 if OpenType Font Variations are supported (for MS Rasterizer v.2.2 and later). It is set to 0 otherwise.

Bit 11 is set to 1 if vertical phantom points are used (for MS Rasterizer v.2.2 and later). It is set to zero otherwise.

Bit 12 is set to 1 if the rasterization is for grayscale using the font smoothing technique (for MS rasterizer v.1.7 and later).

Bit 13 is set to 1 if ClearType is enabled (for MS rasterizer v.1.6+ or MS rasterizer v.1.8 and later). It is set to 0 otherwise.

Bit 14 is set to 1 if ClearType widths are compatible with bi-level and grayscale widths (for MS Rasterizer v.1.8 and later). It is set to 0 if the widths are the natural ClearType widths.

Bit 15 is set to 1 if ClearType symmetrical smoothing is being used (for MS Rasterizer v.1.8 and later). It is set to 0 otherwise.

Bit 16 is set to 1 if ClearType is processing the LCD stripes in BGR (Blue, Green, Red) order (for MS Rasterizer v.1.8 and later). It is set to 0 otherwise.

Bit 17 is set to 1 if ClearType sub-pixel text is being used (for MS Rasterizer 2.0 and later). In this case, any hints on the right side-bearing point are ignored. Hints to sharpen stems may also have minimal effect. It is set to 0 otherwise.

Bit 18 is set to 1 if ClearType symmetric rendering is being used (for MS Rasterizer v.2.0 and later). Depending on the horizontal LCD stripe orientation, this can impact the rendering of horizontal features. It is set to 0 otherwise.

Bit 19 is set to 1 if ClearType gray rendering is being used (for MS Rasterizer v.2.1 and later). It is set to 0 otherwise.

When the selector is set to request more than one piece of information, that information is OR’d together and pushed onto the stack. For example, a selector value of 6 requests both information on rotation and stretching and will result in the setting of both bits 8 and 9.

The following table encapsulates the above information.

| - | **Query Selector Bit** | **Query Selector Bit Mask** | **Result Bits** | **Result Bit Mask** | **Version Requirements** |
| --- | --- | --- | --- | --- | --- |
| Version | 0 | 0x00000001 | 0-7 | 0x000000FF | All |
| Glyph Rotation | 1 | 0x00000002 | 8 | 0x00000100 | All |
| Glyph Stretched | 2 | 0x00000004 | 9 | 0x00000200 | All |
| Font Variations | 3 | 0x00000008 | 10 | 0x00000400 | (&gt;= 5 && &lt;=32) || (&gt;= 41 && &lt;= 64) |
| Vertical Phantom Points | 4 | 0x00000010 | 11 | 0x00000800 | (&gt;= 5 && &lt;=32) || (&gt;= 41 && &lt;= 64) |
| Windows Font Smoothing Grayscale | 5 | 0x00000020 | 12 | 0x00001000 | (&gt;= 34 && &lt;= 64) |
| ClearType enabled | 6 | 0x00000040 | 13 | 0x00002000 | (&gt;= 36 && &lt;= 64) |
| ClearType compatible widths enabled | 7 | 0x00000080 | 14 | 0x00004000 | (&gt;= 37 && &lt;= 64) |
| ClearType Horizontal LCD stripe orientation | 8 | 0x00000100 | 15 | 0x00008000 | (&gt;= 37 && &lt;= 64) |
| ClearType BGR LCD stripe order | 9 | 0x00000200 | 16 | 0x00010000 | (&gt;= 37 && &lt;= 64) |
| ClearType sub-pixel positioned text enabled | 10 | 0x00000400 | 17 | 0x00020000 | (&gt;= 39 && &lt;= 64) |
| ClearType symmetric rendering enabled | 11 | 0x00000800 | 18 | 0x00040000 | (&gt;= 40 && &lt;= 64) |
| ClearType Gray rendering enabled | 12 | 0x00001000 | 19 | 0x00080000 | (&gt;= 40 && &lt;= 64) |

The version information is as follows:

| **GETINFO Version** | **Microsoft Rasterizer Version** | **Notes** |
| --- | --- | --- |
| 1 |  | Macintosh System 6 INIT |
| 2 |  | Macintosh System 7 |
| 3 | 1.0 | 16-bit Windows 3.1. |
| 4 |  | Macintosh System 6.2 |
| 5 |  | Kirin Printer |
| 6 |  | Macintosh System 7.1 |
| 7 |  | Macintosh QuickDraw GX |
| 33 | 1.5 | 32-bit version, new scan-convertor |
| 34 | 1.6 | Font smoothing, new SCANTYPE |
| 35 | 1.7 | Composite scaling changes |
| 36 | 1.6+ | “Classic” ClearType (Windows CE) |
| 37 | 1.8 | ClearType |
| 38 | 1.9 | Subpixel Positioned ClearType |
| 39 | 2.0 | Subpixel Positioned ClearType flag |
| 40 | 2.1 | Symmetric ClearType flag, ClearType Gray (and flag) |
| 41 | 2.2 | OpenType Font Variations |
| 42 | 2.3 | GETVARIATION support |

![A selector value is popped from the stack, and a result is pushed onto the stack.](images/ttinst_inset_p2_108.png)
### GET VARIATION

| GETVARIATION[ ] |  |
| --- | --- |
| Code Range | 0x91 |
| --- | --- |
| Pushes | Normalized axes coordinates, one for each axis in the font. (Values are 2.14 fixed-point numbers padded with zeroes in the upper 16 bits.) |
| --- | --- |

GETVARIATION is used to obtain the current normalized variation coordinates for each axis. The coordinate for the first axis, as defined in the 'fvar' table, is pushed first on the stack, followed by each consecutive axis until the coordinate for the last axis is on the stack.

Since this instruction is not supported in every environment, it is required that an IDEF, in either the 'fpgm' or 'prep' table, be provided for the GETVARIATION OpCode of 145 (0x91). Here is an example:

```
PUSHB[000] 145 /* OpCode 0x91, GetVariation */
IDEF[]
NPUSHW[] 2 /* Number of axes in this font */, 0, 0
ENDF[]
```

This program returns two zeroes on the stack, indicating the default values for each of the two axes. Zeroes will be interpreted as the default values for this font. The 'maxp' table should properly reflect the usage of the IDEF.

Notes:

In order to properly handle an instance font that is generated from a variable font, yet still have the instructions provide the same behavior between the variable font and the instance font, the following setup in the instance font is recommended.

Either identify and modify the existing, active IDEF for OpCode 0x91, or else add a new IDEF for OpCode 0x91 at the end of the 'prep' table. Multiple IDEFs for the same OpCode are valid, and the last one executed will be used. By placing a new IDEF at the end of the 'prep' it is easier to dynamically update, and reduces the likelihood of another IDEF overriding this one.

The default IDEF for OpCode 0x91, as noted above, usually returns zeroes on the stack, indicating the default values. In the case of an instance font generated from a variable font, the values to be returned must match the normalized values for the particular instance, with the coordinate value for the first axis pushed first on the stack followed by each consecutive axis in the order listed in the 'fvar' table. Caution should be made that the 'maxp' table properly reflects the maxInstructionDefs and maxStackElements added by this modification.

The following is an example of a replaced IDEF 145 (0x91) added for an instance:

```
PUSHB[000] 145 /* OpCode 0x91, GetVariation */
IDEF[]
NPUSHW[]   2 /* Number of axes in this font */, -16384, 0
ENDF[]
```

In this case, it provides the equivalent of GETVARIATION returning -1.0 for the first axis and 0.0 for the second axis.