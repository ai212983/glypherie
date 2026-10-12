# Diagonal weight

Heavy Roboto diagonals and thin Literata tails needed coordinated fitting, including short, curved and mixed borders.
The model relates diagonal thickness to the horizontal standard while preserving contrast, terminals and joins.

## Foundation and invariant

[Hersch §6](../../references/papers/1993-hersch/paper.md) grounds coordinated border widths and pixel-grid phase;
[VTT DStroke](../../references/VisualTrueType/doc/VTT%20Language%20Reference/vttlang.md#dstroke) separates diagonal
width selection from the X/Y control direction; [Shamir §3](../../references/papers/2003-shamir/paper.md) grounds
feature classes and relative design dimensions. Preserve source thick/thin contrast, parallel borders, anchors, tangents
and contour ownership. Classification and width transfer are **project hypotheses** adapting these principles.

## Topics

### 01. Diagonal weight and contrast

Scale perpendicular source thickness by the horizontal standard's monochrome fitted/source ratio, then project onto the
dominant control axis. All diagonal classes share this reference independently of movement direction. Straight strokes
use a rounding-safe minimum separation; curved strokes use a signed width correction that permits narrowing.

### 02. Border coverage

Opposing straight borders form a coupled stroke: shared endpoints obey the same width constraint. Source chord length
determines short-border eligibility. Bounded movement along the stroke accommodates attachments to anchored stems;
incompatible constraints retain ordinary fitting.

Curved and mixed borders are paired by tangent roles, opposite directions, overlap and positive-ink evidence. Movement
direction follows their geometry. Curved pairs require an independent interior control; mixed pairs preserve tangents
and longitudinal cap coordinates while transverse caps follow the width constraint. Endpoint order and rounding
separation protect continuity.

### 03. Terminal shape

Eligible terminal curves follow a diagonal endpoint's horizontal movement while their far endpoint stays fixed.
Dependent controls retain their ordinarily hinted offsets. Continuous junctions, single-control quadratics and
independently owned points are protected from this movement.

## Scope and limits

The model applies to automatic 1-bit fitting. Accepted review covers Roboto, Literata and Source Sans 3 at 14/16/18/20
px, weight 400, Roboto width 100 and Literata optical size equal to pixel size, in the configured 1-bit and 3-bit
profiles. Upright stem weight is outside this model.

Curved width is representative rather than uniform. Pure two-control/two-control bows lack independent width freedom and
are unsupported; conservative connectivity guards protect joins.

Topology findings are deferred to broader-corpus assessment: Roboto 20 px W at weight 300; Literata 15 px W at weight
400, optical size 15; Source Sans 3 20 px y at weight 300. Component-count changes have not demonstrated damaged joins;
captures and guards are preserved.
