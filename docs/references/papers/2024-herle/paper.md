---
source_pdf: paper.pdf
source_url: https://infoscience.epfl.ch/server/api/core/bitstreams/bbef8e44-17de-4b0e-aa0b-649fe35f51b5/content
source_sha256: bf4dd0b49ecb975609a4893f1951cfc2ada8c80671d4388865e77e2803d9a5c9
pdf_pages: 34
converter: docling 2.131.0
math_format: latex
review_status: targeted corrections; not a fully proofread transcription
---

Source: [original PDF](paper.pdf). Page markers identify the PDF page and the original printed page. See
[review guidance](../README.md#accuracy-and-review) for review scope and limitations.

<!-- PDF page 1; printed page 020901-1 -->

![Image](figures/figure-01.png)

## Emulating paper: a review of reflective display technologies

Dorian Herle ,a,* Olivier J. F. Martin,b Luis Guillermo Villanueva,a and Niels Quack c,*

aEcole Polytechnique Fédérale de Lausanne, Advanced Nano-Mechanical Systems Laboratory,

Lausanne, Switzerland

bEcole Polytechnique Fédérale de Lausanne, Nanophotonics and Metrology Laboratory,

Lausanne, Switzerland

cThe University of Sydney, Micro- and Nanosystems, Sydney, New South Wales, Australia

ABSTRACT. Reflective displays, which harness ambient light, offer energy-efficient alternatives to traditional emissive
screens in mobile devices. This review provides an overview of various reflective display technologies and their
comparative performance metrics. The review highlights the potential of micro-electromechanical system-based displays,
with metrics including 90% reflectance, a contrast ratio of 30, a frequency of 120 Hz, and a resolution of about 350
pixels per inch. Their applicability to mainstream devices such as e-readers, smartphones, and smartwatches continues to
be a topic of interest and exploration.

© The Authors. Published by SPIE under a Creative Commons Attribution 4.0 International License. Distribution or
reproduction of this work in whole or in part requires full attribution of the original publication, including its DOI.
[DOI: 10.1117/1.JOM.4.2.020901]

Keywords: reflective displays; mobile devices; ambient light; optics; light modulators

Paper 23034V received Oct. 13, 2023; revised Mar. 10, 2024; accepted Mar. 18, 2024; published Apr. 11, 2024.

## 1 Introduction

The swift evolution of the internet, digital data, and entertainment, coupled with the rise in a plethora of
applications, has made electronic displays a crucial daily necessity. Since the introduction of liquid-crystal displays
(LCDs) in 1968 by George Heilmeier of RCA,1 display technologies have shown significant advancements, resulting in
images with exceptional color reproduction and unprecedented sharpness. Recent reviews have focused on emissive display
technologies, including LC, organic light-emitting diode (OLED), mini- and micro-LED emissive displays,2,3 and quantum
dot displays.4

Moreover, a critical review published in 2011 highlighted the present and future prospects of electronic paper,
detailing the performance limitations and possible future breakthroughs.5 Fast forward to the present, a recent book on
E-paper displays underscores the growing importance of this technology, emphasizing its low power consumption and
potential for reducing eye strain.6

As electronic displays have become increasingly portable and widespread, the expectations and demands on their
performance have also grown. In particular, the need for increased battery life and optimal visibility in various
lighting conditions are critical for modern mobile devices. Emissive display technologies need to generate enough light
to adapt to the ambient light levels. As human eyes adjust to the surrounding brightness, these technologies can lead to
a perceived decrease in contrast ratio (CR) in areas with ample lighting. Unfortunately, increasing the emissivity of a
display to align with the lighting conditions also results in increased energy consumption.

*Address all correspondence to Dorian Herle, dorian.herle@epfl.ch; Niels Quack, niels.quack@sydney.edu.au

REVIEW

<!-- PDF page 2; printed page 020901-2 -->

This oxymoron of the emissive display can partly be lessened by the utilization of more efficient light generation, such
as OLED and micro-LED technology, yet it remains an inevitable challenge. Reflective displays on the other hand provide
a more elegant and natural solution. Similar to any printed medium, this technology does not need to emit light.
Instead, ambient light is utilized to show the image. The benefits are directly apparent: perfect readability in bright
environments, while being more energy efficient than their emissive counterparts. Readability in darkness is usually
achieved by an integrated front light.

Throughout the years, a plethora of reflective display technologies have been invented and researched; these include
electrowetting, reflective LC, electrochromic, micro-electromechanical systems (MEMS), tunable photonic crystals, and
electrophoretic displays. Each technology has its own set of benefits and drawbacks in terms of peak reflectivity, CR,
achievable frequency, and resolution, as well as power consumption.

Understanding the fundamental concepts, performance, and prospective uses of these display technologies is becoming
increasingly important as the field advances and diversifies. In this review article, we provide a comprehensive
overview of various reflective display technologies, highlighting their key features, operation mechanisms, and recent
advances in the field. Our aim is to offer a valuable resource for those interested in the current state of the art and
the future direction of electronic display research and development, particularly for low-power mobile devices. To
facilitate a deeper understanding, the review is organized into several sections, each dedicated to a specific
technology. Each section delves into the origin, working principles, commercial applications, and challenges associated
with the respective technology. The aim of this structured approach is to offer a valuable resource for readers
interested in the current state of the art as well as the future direction of electronic display research and
development.

## 2 Print Media as Benchmark for Reflective Displays

A commonly employed benchmark for assessing the static performance of reflective displays is the extent to which they
can emulate the visual characteristics of traditional print media. These characteristics include elements such as
ambient CR, white state reflectivity, color, and bistability. These benchmarks serve to gauge the performance of
reflective displays, while aligning with foundational measurement parameters highlighted in the broader context of
display technologies.7 By focusing on these four key characteristics, this chapter aims to offer a comprehensive
understanding of how reflective displays measure up to print media in terms of readability and visual comfort.

## 2.1 Ambient Contrast Ratio

White paper can be described as a close approximation of a perfectly diffuse, or Lambertian, surface,8 making it appear
bright from any viewing angle. At the same time, black pigments absorb most of the light. The ratio between the
brightest and darkest state is commonly referred to as “contrast” or CR. Although emissive displays frequently exhibit
exceedingly high CRs, it is important to note that these values are typically attained under dark environmental
conditions. Under bright ambient conditions these values usually greatly deteriorate for emissive displays, as can be
seen in Fig. 1.

Fig. 1 Qualitative photographs of a representative emissive display under different ambient conditions. Photographs are
taken in darkness (0 lux), indoor lighting (1k lux), overcast sky (5k lux), and outdoor sunlight (40k lux). Adapted with
permission from Ref. 9, copyright (2021), DisplayMate Technologies.

![Image](figures/figure-02.png)

<!-- PDF page 3; printed page 020901-3 -->

The ambient CR (ACR), as defined in Eq. (1), offers a more accurate approach for evaluating display performance,
particularly for reflective displays, as it takes into consideration the realworld lighting conditions in which these
devices operate:10

$$\mathrm{ACR}=\frac{L_{\mathrm{on}}+L_{\mathrm{Ambient}}R_L}{L_{\mathrm{off}}+L_{\mathrm{Ambient}}R_L}.\tag{1}$$

where Lon and Loff are the display’s “on” and “off” luminance, respectively, LAmbient is the ambient light, and RL is
the display’s luminous reflectance.11 The latter quantifies the amount of visible light reflected by a display panel
under ambient lighting conditions, considering the human eye sensitivity VðλÞ (i.e., CIE 2° Standard Observer), the
spectrum of the incident ambient light SðλÞ (i.e., CIE standard D65 light source), and the spectral reflectance of the
display RðλÞ. Mathematically, it is defined as follows:

$$R_L=\frac{\int_{\lambda_1}^{\lambda_2}V(\lambda)S(\lambda)R(\lambda)\,\mathrm d\lambda}{\int_{\lambda_1}^{\lambda_2}V(\lambda)S(\lambda)\,\mathrm d\lambda}.\tag{2}$$

RL serves as an index for evaluating the undesirable reflection of environmental light, which could compromise the
legibility and visual comfort of the display interface. Using Eq. (1), with an average RL of 4% and a typical portable
display luminance of 1500 lux, the ambient CR drops to below 2 in direct sunlight (40 K lux), which renders the screen
illegible. Table 1 describes human readability within terms of ACR.

## 2.2 White State Reflectivity

Next to ACR, white state reflectivity is important for mimicking the appearance of paper. Figure 2 compares the black
and white reflectance of three different media: high-quality glossy print, standard print, and LCDs. As can be seen,
glossy prints have a white state reflectivity of around 80%, which sets them apart from the average 30% reflectivity
found in reflective LCDs.

## 2.3 Color

Color reflective displays pose another layer of difficulty in obtaining bright vivid colors. Much of it boils down to
the right color system choice, of which a few prominent once are displayed in Fig. 3. Emissive displays predominantly
employ an RGB (red-green-blue) system or an augmented RGBW (red-green-blue-white) system. In the context of reflective
displays, using an RGB system leads to a maximum white-state reflectance of 33%, as each subpixel in an RGB
configuration only contributes 33% of the light. Similarly, an RGBW system can achieve a maximum white-state reflectance
of 50% due to the added white subpixel, which further contributes to the overall reflectance. These values assume fully
saturated color filters and are usually lower in practice.

Subtractive color systems, such as CMY (cyan-magenta-yellow) and CMYK (cyanmagenta-yellow-black), have traditionally
been used in the printing industry and usually employ a stacked architecture that greatly enhances light conversion. An
optimal white state and maximum color fraction, defined as the effective area over which saturated color can be
displayed,5

Table 1 Ambient CR and readability.

| Ambient contrast ratio | Readability                                                                |
| ---------------------- | -------------------------------------------------------------------------- |
| 1-2                    | Illegible under direct sunlight                                            |
| 3-4                    | Sufficient readability in shade; marginal legibility under direct sunlight |
| 5-9                    | Adequate readability in sunlight; satisfactory appearance                  |
| 10                     | Highly legible in sunlight; visually appealing                             |
| 15                     | Exceptional readability; aesthetically pleasing                            |
| 20                     | Superior performance; outstanding readability                              |

<!-- PDF page 4; printed page 020901-4 -->

Fig. 2 Reflectance spectra for white and black states of a high-quality magazine print (National Geographic), standard
print, and a reflective LCD. CRs are indicated on top of the white reflectance lines. Data for Reflective LCD and
National Geographic are sourced from Ref. 12.

![Image](figures/figure-03.png)

Fig. 3 Schematic representation of different color systems. (a) Red-green-blue (RGB) color filters on top of white-black
switching pixels, results in a maximum reflection of 33% and a color fraction (the effective area over which saturated
color can be displayed) of 33%’ (b) red-green-blue-white (RGBW) color filters add an additional white filter, increasing
maximum reflection to 50%, although at the cost of a reduced color fraction of 25%; and (c) three-layer
cyan-magenta-yellow pixels with a white reflector yield an exceptional maximum reflection and a color fraction of 100%.
This configuration is mostly used in print media. Adapted with permission from Ref. 5, copyright (2011), Society for
Information Display.

![Image](figures/figure-04.png)

can be realized through the incorporation of a tri-layered structure featuring CMY (cyanmagenta-yellow) switching layers
in the display system.13,14 At the same time, stacked displays increase costs and complexity because they require more
materials, additional backplanes, and complex driving electronics. In addition, the pixel resolution must be limited to
maintain enough clear aperture, which helps reduce optical losses and parallax problems. To avoid significant parallax
issues, the distance between the front and rear pixels in a multi-layer stack should not be larger than the pixel size
itself. This becomes challenging when dealing with very highresolution displays. It is clear that subpixels capable of
transitioning among multiple color states, surpassing the conventional binary (on/off) color limitation, offer the
potential to develop singlelayered display systems capable of achieving 100% color reproduction.5

## 2.4 Bistability

Once printed on paper, no further energy is required to see the image or text. Ideally, this should be mimicked in
reflective display technology. Bistability, a desirable feature for display devices, refers to the ability to maintain
image persistence in two stable states without requiring continuous energy. This means that once the image or text is
printed, it can be seen without the need for additional energy.

<!-- PDF page 5; printed page 020901-5 -->

Fig. 4 Schematic visualization of the discussed reflective display technologies. Light manipulation principles across
these display technologies: LCDs – polarization, MEMS (IMOD) - interference, electrowetting and electrophoretic -
absorptive media transport, phase-change - refractive index, electrochromic - band-gap adjustment, and photonic
crystals - diffraction.

![Image](figures/figure-05.png)

## 3 Reflective Display Technologies

Reflective displays technologies have been evolving since the 1970s, with the introduction of “Gyricon” at Xerox’s Palo
Alto Research Center [12]. Over the years, numerous e-paper technologies have been developed, and they can be broadly
classified based on their tunability mechanisms. These categories are shown in Fig. 4 and encompass electrophoretic,
LCs, MEMS, electrowetting, phase change, electrochromic, and tunable photonic crystals.

In the following sections, we delve into each actuation mechanism, discussing the fundamental principles,
implementations, and possible outlook. By examining these technologies in detail, we aim to provide a comprehensive
understanding of the diverse e-paper landscape and its ongoing developments.

## 4 Electrophoretic

Electrophoresis describes the motion of charged particles relative to a fluid under the influence of an external
electric field. Although the beginning of electrophoretic displays can be attributed to the printing company Xerox,
which was granted a patent on “color display device” in 1971,15 it was the introduction of microencapsulation of the
charged particles by Comiskey et al.16 from MIT that allowed this technology to mature to commercial readiness,
resulting in the creation of the commercial entity EInk. Despite its progress, the lack of video compatibility in
electrophoretic displays is a significant challenge for widespread adoption in mobile devices. This limitation triggered
the exploration of innovative solutions, one of which has been the employment of total internal reflection (TIR)
modulation, allowing for a much-reduced particle traveling distance. The electrophoretic TIR display has been
commercialized by the company “CLEARink Displays, Inc.” short for “charged liquid electro-active response.” CLEARink
Displays emerged as a separate entity from the University of British Columbia in 2012.17 Both technologies are presented
in the following sections.

## 4.1 Working Principle

In general, an electrophoretic display operates by displacing charged pigments in and out of sight using electrostatic
fields. Equation (3) describes the particle velocity (with initial condition v0 1⁄4 0). The formula is derived by
equating the electric attraction forces acting on a charged particle due to an external electric field with the fluidic
drag forces counteracting the particle mobility, which are given by Stoke’s law as18

$$v=\frac{qE}{6\pi\mu d}\left(1-e^{-\frac{6\pi\mu d}{m}t}\right).\tag{3}$$

where v is the particle velocity, E is the applied electric field, qP is the particle charge, μ is the fluid’s
viscosity, d is the particle’s diameter, and m is the mass of the particle.

<!-- PDF page 6; printed page 020901-6 -->

As can be observed from Eq. (3), the particle velocity, and thus the speed at which a single pixel can switch states, is
influenced by several factors. One of the key determinants is the particle charge. It is most often deduced from the
Zeta potential, which is a measure of the electrostatic potential difference between the fluid and the outer layer of
the electrical double layer surrounding the particle. This parameter provides a nuanced measure of the particle’s
effective charge and its interactions with the fluid. For low-dielectric media, it is proportional to the particle
charge.19 A high absolute value of the Zeta potential ensures better dispersion of the particles, reducing aggregation
and enhancing the display’s long-term reliability. Separately, it is important to note the limitations imposed by the
applied electric field. Research efforts have been focused on reducing the required traveling distance, reducing the
electrode spacing, and improving the chemical properties of the system.

## 4.2 Implementations

Microcapsule electrophoretic displays utilize electric fields to move highly scattering or absorbing microparticles
vertically within a microcapsule. A multitude of these microcapsules forms one pixel, and monochrome or color systems
can be developed.

## 4.2.1 Monochrome system

To this date, vertical dual-particle electrophoretic-based displays have been the most commercially successful
reflective display technology on the market. As can be seen in Fig. 5, depending on the applied electric field,
different colored particles with either positive or negative zeta potential are selectively moved to the surface,
creating the desired image or text. TiO ZrO AlO

White particles often consist of inorganic pigments, such as TiO2, ZrO2, ZnO, or Al2O3, and black particles are often
made from Color Index black pigments, iron oxide, or carbon black.22 These particles are dispersed in a non-polar fluid,
which helps reduce leakage currents within the display. Surfactants are added into the system to prevent particle
agglomeration23 and to aid particle charging.24 To reduce the switching voltage, a specialized coating formulation is

Fig. 5 Microcapsule electrophoretic display. (a) Schematic representation of an electrophoretic microencapsulated black
and white ink, wherein the displayed color is controlled by the polarization of the electric field and the resulting
vertical position of the charged nano-pigments. (b) Microscope image of microcapsules in a working prototype. Image
adapted with permission from Ref. 20, used under a Creative Commons Attribution 2.0 Generic (CC BY 2.0) license. (c) A
photograph of the Amazon Kindle e-reader tablet adapted with permission from Ref. 21, used under a Creative Commons
Attribution 2.0 Generic (CC BY 2.0) license.

![Image](figures/figure-06.png)

<!-- PDF page 7; printed page 020901-7 -->

applied,25 resulting in the microcapsules being arranged in a closely packed monolayer. This arrangement facilitates a
thinner overall packaging of the microcapsules. In addition, it was found that adding an oil-soluble high molecular
weight polymer to the electrophoretic fluid increased image stability to 12 days and, importantly, without increasing
the fluid viscosity.26 In the initial stage of electrophoretic display developments, a “flash reset” was necessary prior
to rendering a new image. This process involved resetting the positions of all particles to a uniform, known state,
allowing for a more predictable and reliable transition to the desired grayscale level in the subsequent image. Using an
algorithm27 that stores the history of each pixel’s switching for a certain amount of time allows for addressing 16
levels of grayscale without flashing. Parasitic polarization in the microcapsule polymeric binding material leads to a
dwell time dependence:28 the impulse required to switch a pixel to a new optical state depends on the time that the
pixel has spent in its previous optical states. This issue has been greatly researched and resolved through careful
selection of the materials used.29,30

## 4.2.2 Color system

Color displays for dual particle systems have been achieved through the addition of a color filter array (CFA), as
visualized in Fig. 6(a), or multi-particle systems, as visualized in Fig. 6(b).

Different methods have been explored to create CFA; these include direct printing35 or photolithography36 of a color
resist and laminated CFA films.37 However, CFAs, such as RGB or RGBW, use area sharing, in which each full-color pixel
consists of three or four sub-pixels, respectively. This method limits the display area for each color, leading to
suboptimal brightness

Fig. 6 Color electrophoretic reflective display technology, based on (a) superimposed color-filter arrays. Adapted with
permission from Ref. 31, copyright (2006), Society for Information Display. (b) A multi-color particle system.32 (c) CFA
based device “Inknote Color Plus” on the left and “Bigme Galy” device on the right with a multi-particle system offering
brighter colors.33 The image is taken at the same location and same illumination, showcasing the increased brightness of
multiparticle systems. Image adapted with permission from Ref. 34, copyright (2023), Good e-reader.

![Image](figures/figure-07.png)

<!-- PDF page 8; printed page 020901-8 -->

levels. Furthermore, the implementation of a color filter to divide monochromatic pixels into three colored pixels
inevitably leads to a reduction in the overall resolution.

To overcome these limitations in filter-based color electrophoretic displays, current research is exploring
multi-particle systems. The key concept behind multi-particle systems is to make use of different electrophoretic
mobilities as well as charge polarity and intensity to separate the particles.38 Using waveforms, these particles are
pushed and pulled to mix colors and produce specific shades. The EInk Spectra system uses black, white, and colored
particles (either red or yellow). For full-color displays, EInk’s Advanced Color ePaper (AceP) combines white with cyan,
magenta, and yellow particles, enabling it to render up to 50,000 colors,32 akin to newspaper prints. Figure 6(c)
compares two commercial displays using CFA (left) and a multi-particle system (right) under the same illumination
condition. The brightness difference is clearly perceived.

## 4.3 Improving Switching Speed of Microencapsulated Electrophoretic Display Device

Various studies have been carried out to improve the response time. One approach is to use low viscosity39 to increase
electrophoretic mobility; however, this deteriorates bistability. Other approaches focus on improving the driving
waveforms40 or on picture drawing algorithms based on the content.41 Yet another suggestion is to use the inverse
electrorheological (IER) effect,42 essentially reducing the viscosity briefly during the switching time. It was found
that such an IER effect can be induced by the rotation of LC molecules,43 briefly leading to some carrying hydrodynamic
motion. Adding LC molecules leads to a 2.8 times reduction of response time while cutting the applied voltage in half.

## 4.4 Total Internal Reflectance Electrophoretic Displays

TIR displays use TIR for bright images and “frustrated” TIR for dark ones, achieving high contrast and fast visual
changes. In TIR, light in one medium reflects internally when hitting a lowerindex medium at a steep angle. Frustrated
TIR happens when a third, higher-index medium is close to the interface, letting some light pass or be absorbed. This
technology was first reported in 1997.44

## 4.4.1 Working principle

For TIR electrophoretic displays, the switching mechanism is achieved through the movement of charged particles in and
out of the evanescent field.45 To optimize the angular response, TIR displays are constructed using hemispheres.46
Charged electrophoretic absorbing particles are hosted inside a liquid below the reflective hemisphere array. As
depicted in Fig. 7(a), absorbing particles are pulled out or into the evanescent field, allowing the light to be
reflected or absorbed, respectively.

The phenomenon of TIR occurs when light is incident upon an interface from a high refractive index material n1 to a low
refractive index n2 at an angle of incidence θ that exceeds the critical angle θc given as

Fig. 7 TIR electrophoretic display concept. (a) Schematic representation43 of the working principle, showing TIR
reflection and frustrated TIR when the polarity of the applied electric field draws the absorptive charged black
particles into the evanescence wave field. (b) SEM image (left) of a fabricated reflection plane consisting of spheres
in an index matching layer, as well as an optical microscope image showing the reflection rings and dark areas of normal
incident light. Image adapted with permission from Ref. 173.

![Image](figures/figure-08.png)

<!-- PDF page 9; printed page 020901-9 -->

![Image](figures/figure-09.png)

Fig. 8 TIR electrophoretic color display. (a) Schematic of TIR display with an RGB CFA; green is in the reflective
state, and red and blue are in the absorptive state. (b) A picture of a tablet implementing this technology. Adapted
with permission from Ref. 48, copyright (2019), Wiley.

![Image](figures/figure-10.png)

$$\theta_c=\arcsin\left(\frac{n_2}{n_1}\right).\tag{4}$$

For angles of incidence less than the critical angle, light is transmitted through the interface. Conversely, for angles
of incidence greater than the critical angle, the light undergoes TIR and is reflected back into the first medium. As
depicted in Fig. 7(b), upon normal incidence light, these hemispheres exhibit a bright reflective ring until the light's
angle of incidence surpasses the critical angle, causing the hemisphere's center to reflect less light. For normal
incidence, the reflection is given as

$$R=1-\left(\frac{n_2}{n_1}\right)^2.\tag{5}$$

In practice, the said hemispheres are formed from high refractive index nano-composite material ðn1 ∼1.9Þ and low-index
adjacent medium, such as fluroniated hydrocarbon ðn2 ∼1.2Þ; normal incidence reflections on the order of ∼60% can then
be expected. 2m

The size of the hemispheres can be made as small as 2 μm in diameter. This reduces the device thickness and thus the
required travel distance for the absorbing nanoparticles, yielding a higher switching time and reducing energy
consumption, as well as easing the material constraints with respect to material attenuation coefficient. Color displays
are achieved incorporating CFA on top of the microsphere array, as depicted in Fig. 8.

CLEARink released a number of working prototypes, for example, at SID 201948 a 9.7′′ diagonal eTIR display demonstrating
video and color capabilities including grayscale [see Fig. 8(b)], showcasing a very small power consumption of merely
0.029 mJ∕cm2.

## 4.5 Outlook

The main challenge of microcapsule electrophoretic displays is the switching speed. The response time is usually as long
as hundreds of milliseconds.49 This limits the application to static or slow-moving images. Current challenges for TIR
electrophoretic are mostly related to commercial scalability, as well as improving the color gamut, increasing video
speeds, reducing ghosting, and improving the general reliability of device. A potential long-term issue for TIR-based
reflective displays is that they cannot operate in transmission by design. Thus, this makes a stacked CMY(K) pixel
design difficult and ultimately limits the potential for achieving high color saturation/brightness.

## 5 Liquid Crystal

Backlight LCDs make up most of commercially available emissive displays, while presenting one of the first reflective
display technologies. LCDs were first suggested for display applications in 1968 at the International Liquid Crystal
Conference in Ohio. The prototype presented by George Heilmeier of RCA1 generated substantial interest and triggered the
start of LCD developments for many industrial companies. The next crucial step toward a robust, “television-ready”

<!-- PDF page 10; printed page 020901-10 -->

LCD was the invention of the twisted nematic display (TN-display) by Martin Schadt and Wolfgang Helfrich in 1970.50 The
TN principle and technologies derived from it remain one of the central foundations of most LCDs to this day. However,
one of the challenges has been their continuous power consumption required to maintain an image. This led to the
exploration of more power-efficient display technologies. A significant breakthrough came in 1994, when Yang et al.51
demonstrated that dispersing a polymer in cholesteric liquid crystals (ChLCD) or using a cell with inhomogeneous surface
anchoring resulted in long-term bistability. This bistable property enables the LC molecules to maintain their original
orientation for a long time even after the electric field is removed, greatly reducing power consumption for static
images. Both TN and cholesteric LCD technologies are presented in the following sections.

## 5.1 Twisted-Nematic Liquid Crystal Displays

## 5.1.1 Working principle

The TN-cell52 is the most basic LCD technology; it consists of an LC sandwiched between two crossed polarizers and a
reflective layer on the backside. The first polarizer in this setup polarizes incoming light in one direction. When
turned off, the LC rotates the polarization of the traversing light by 90 deg, allowing it to pass through the second
polarizer and be reflected on the backside mirror. When the LC is turned on, the incoming light’s polarization is no
longer rotated and is blocked on the second polarizer [see Fig. 9(a)].

Polarizer-based LC technology can attain a maximum reflectivity of 50% because a polarizer filters out half of the
unpolarized ambient light.

## 5.1.2 Implementation

TN-cell based reflective LCD is not bistable by nature. Memory-in-pixel (MIP) technology is often employed to reduce
power consumption.53 MIP designates the technology of integrating static random-access memory circuits into every pixel
unit, effectively holding the voltage until a pixel state needs to change. To further reduce energy consumption, it is
suggested to only refresh the rows and lines of the display that need to display movement.54 As MIP LCDs are fully
digital displays compared with conventional analogue active-matrix LCD, attaining grayscale values is more challenging.
In terms of optical characteristics, light diffusion methods must be included in a reflective LCD to avoid a mirror-like
look. Such diffusion can either be achieved through the addition of scattering back electrodes or top diffuser films.

Fig. 9 Reflective TN display: (a) schematic representation: unpolarized light first passes through polarizer A, where it
is linearly polarized. In the OFF-state, the liquid crystal rotates this polarization by 90 deg, enabling it to pass
through polarizer B and reflect off the back-reflector. In the ON-state, polarization is not rotated; hence it is
blocked by polarizer B. (b) Early TN LCD prototype 1972. Adapted with permission from Ref. 47 under a Creative Commons
Attribution-Share Alike 3.0 license.

![Image](figures/figure-11.png)

<!-- PDF page 11; printed page 020901-11 -->

## 5.1.3 Outlook

TN-cell based reflective LCD has an economic advantage over other technologies as they can directly leverage the decades
of emissive LCD display manufacturing. MIP displays allow for the reduction of power consumption significantly, but they
also limit the range of available colors and grayscale. This is due to the intrinsic limitations in the amount of memory
at each pixel site (bit depth), which in turn determines the number of colors that can be displayed. Currently, 6-bit
color MIP panels and 3-bit and 1-bit black-and-white panels are usually commercially available, restricting these
displays to a smaller color palette (max. 64 here) and fewer grayscale levels. Finally, white state reflectivity is
still limited to within 7% to 18% in commercial displays.55

## 5.2 Zenithal Bistable Display

Zenithal bistable displays (ZBDs), a pioneering advancement in the realm of LC display technology, derive their name
from the term “zenith,” indicative of the viewer’s line of sight in relation to the display surface. This nomenclature
is emblematic of the display’s unique perspective, emphasizing an overhead or top-down viewing angle. The bistability is
a key feature, enabling the display to hold an image with no power consumption until a change is required.

## 5.2.1 Working principle

The functional mechanism intricately controls the orientation of nematic LC molecules using a precisely patterned
grating surface.56 This grating, characterized by its distinct grooves, shapes the energy landscape, leading to the
elastic deformation of the LCs and the formation of disclinations, or irregular alignment points, known as defects.57
These disclinations stabilize the LC molecules in two distinct states: the defect (D) state, in which molecules are
aligned at a low tilt, and the continuous (C) state, characterized by near-vertical alignment.56 Central to the
switching mechanism between these bistable states is the flexoelectric effect, a result of the significant elastic
deformation around the grating grooves.58,59 This effect generates polarization that responds to external electrical
pulses, facilitating the controlled reorientation of the LC molecules between the D and C states. The ability of these
states to remain stable without the need for continuous electrical input highlights the efficiency and low-energy design
of ZBDs.60 This sophisticated interplay of flexoelectric polarization and surface-induced molecular orientations is
fundamental to the unique functionality of ZBDs.

## 5.2.2 Implementation

In ZBDs, the control over nematic LC molecules’ orientations is achieved through the synergistic effects of a patterned
grating surface and a non-altering rubbed polymer surface. The grating, by its design, induces the formation of local
alignment states—either the D state, or the C state. These states are localized responses to the grating’s
microstructure. On a device level, the LC layer is sandwiched between one grating and a rubbed polymer surface. The
molecule orientation on the polymer surface stays constant but can be switched at the grating. The resulting two
bistable states are called the “hybrid aligned nematic” (HAN) state, denoting a state in which the molecules go through
vertical to planar, and the TN state,61 denoting a 90-deg twist between alignments, as visualized in Fig. 10(a).
Furthermore, in general, the typical layers of a ZBD include front and rear polarizers, LC material, alignment layers,
and electrodes.

## 5.2.3 Outlook

In general, ZBDs were among the first LCDs to exploit the flexoelectric effect, previously deemed too weak for practical
applications, and they introduced nano-replication techniques into the LCD manufacturing process.59 The initial
commercial application of ZBD technology manifested in electronic point-of-purchase (ePOPTM) signage within the retail
sector60 (see 10b). It has been demonstrated that ZBD technology facilitates latching at voltages below 20 V and
achieves switching speeds exceeding 80 microseconds per line,62 enabling the update of an entire e-book page in as
little as 10 milliseconds. However, the reflectivity of ZBDs in their white state, approximately 30%—primarily due to
the front polarizer—renders this technology less

<!-- PDF page 12; printed page 020901-12 -->

appealing for e-paper applications compared with the approximate 50-60% white state reflectivity of conventional
newspapers.

Fig. 10 The Zenithal Bistable Display. (a) A schematic depiction of the basic structure consisting of a front polarizer,
grating, liquid crystal (LC) layer, rubbed polymer, and reflector. An electric potential causes the LC layer to switch
between a TN state and a HAN state, both of which are bistable. (b) Photograph illustrating a typical use case of ZBDs
as a shelf label, specifically the ZBD EPOP 900 model. (Datasheet, copyright 2011 ZBD Displays Ltd.).

![Image](figures/figure-12.png)

## 5.3 Cholesteric Liquid Crystal Displays

The terminology “cholesteric” was first introduced in the scientific community by Georges Friedel in 1922,63 recognizing
the initial identification of this particular state of matter within cholesterol esters by Friedrich Reinitzer in
1888.64 Subsequent to this initial discovery, instances of cholesteric liquid-crystalline states have been reported in a
variety of substances that bear no inherent connection to cholesterol.

## 5.3.1 Working principle

Cholesteric refers to a phase of LC in which the molecules are arranged in layers with a helical stacking pattern. For
normal incidence, the reflected wavelength is given as65,66

$$\lambda_0=n_a p\cos(\theta).\tag{6}$$

where na is the average refractive index, p is the helical pitch, and θ is the angle between the helical axis and the
direction of propagation.

As can be seen from Eq. (6), reflectivity is concentrated around a specific central wavelength. Consequently,
wavelengths deviating from these central peaks contribute less to the total reflectivity, leading to an overall
decrease. The bandwidth of the cholesteric reflection is given as

$$\Delta\lambda=\Delta n p.\tag{7}$$

where Δλ is the birefringence of the LC and p is the pitch. The LC molecules have an inherent electric dipole moment. By
applying an electric field, these molecules experience a torque, causing the LC molecules to align along the field
direction. This alignment alters the pitch p, thus tuning the reflected wavelength λ0. The key advantage of cholesteric
LC displays is their bistability, with two textures at zero electric field: the reflective planar and the non-reflective
focal conic. Here, ’texture’ refers to the macroscopic molecular arrangement, as shown in Fig. 11(a).

Upon normal incidence, a cholesteric LC surface reflects the component of the light that is circularly polarized in the
same handedness as the CLC, transmitting the other component, and thus it cannot reflect more than 50% of unpolarized
light.70 At oblique incidence, the reflected or transmitted light becomes elliptically polarized.

The brightness can be significantly increased using a stack of two cells with opposing helical twists. Each cell
reflects light with a specific handedness of circular polarization. The first cell lets through light of one handedness,
which is then reflected by the second cell, enhancing the display’s brightness. Defects in the cholesteric crystal
structure lead to scattering and non-ideal

<!-- PDF page 13; printed page 020901-13 -->

reflection conditions. This can be improved using rubbed contact-surfaces. “Rubbed” refers to surfaces that have been
mechanically treated by rubbing them in a specific direction to align LC molecules. This rubbing process induces an
alignment of the LC molecules along the direction of the rubbing, which helps to minimize defects in the cholesteric
structure. As a result, this treatment has been shown to yield an increase in reflectivity of up to 70%71 [see Fig.
11(c)].

Fig. 11 Bistable cholesteric reflective display design and examples. (a) The schematic design of a bistable cholesteric
reflective display,67 illustrating the layered composition and functional elements. (b) Exemplary reflection spectrum of
said cell showing the reflection bandwidth Δλ and central wavelength λ0 67 and (c) two-layer stacked cell with and
without surface treatment (rubbing) to improve reflection. (d) 7.5-inch full-color ChLCD display. Image adapted with
permission from Ref. 68, copyright (2023), AUO. (e) A flexible cholesteric display, demonstrating the technology’s
adaptability and potential for diverse applications. Image adapted with permission from Ref. 69, copyright (2008),
radtech.

![Image](figures/figure-13.png)

## 5.3.2 Implementations

A single pixel [Fig. 11(a)] in a cholesteric reflective display is made up of a cross-section of multiple layers, each
of which contributes distinct capabilities to the pixel’s overall functioning. The topmost layer is a glass substrate
that provides the pixel with physical structure and protection. Directly behind this is a layer of indium tin oxide
(ITO), which acts as a transparent, conductive layer, allowing electric fields to be applied across the pixel. The
pixel’s core layer is made of cholesteric LCs. This layer’s properties change in reaction to applied electric fields,
allowing it to selectively reflect light with a specified circular polarization, or “handedness” and transition between
various states, resulting in the display’s brilliant and dark appearances.

A spacer separates the cholesteric LC layer from the bottom ITO layer. This spacer guarantees proper layer alignment and
separation, which is crucial for preserving the LC’s orientation and operation because, upon exerting shear stress on a
cholesteric film, such as through substrate pressing, the system readily transitions back to the slightly more
energetically stable planar texture.72 The bottom ITO layer performs the same function as the top ITO layer, completing
the pair of electrodes required to alter the state of the cholesteric LC layer. An absorption layer is often put
directly beneath this, typically with black paint. When the LC is in the focused conic

<!-- PDF page 14; printed page 020901-14 -->

state, this layer absorbs forward diffracted and scattered light, improving the pixel’s contrast and overall display
performance. For display applications, the image needs to be temperature invariant. Because most cholesteric materials
are temperature dependent,73,74 much research has been dedicated to solving this issue, such as using dopants that show
opposite changes in helical twisting behavior with temperature to effectively cancel each other’s influence.75 Another
important technological challenge is the peak wavelength on the incident angle, as can be seen from Eq. (6). This
dependence can be eased by integrating a diffuser film76 and thus broadening the distribution of reflection angles,
albeit at the expense of peak reflectivity. Recently, AU Optronics Corporation (AUO) started to roll-out reflective
colorful ChLCD displays, as shown in Fig. 11(d). Figure 11(e) shows a flexible prototype by Kent Displays.

## 5.3.3 Outlook

Reflecting and bistable cholesteric LC displays have been commercially accessible. These devices have evolved with
features such as increased luminosity, multi-color output via stacked layers, and high-contrast monochrome display from
a single layer. Their current limitation is the switching speed, which usually lies on the order of a second,77 limiting
the potential applications in mobile devices.

## 6 Micro-Electro-Mechanical Systems

MEMS-based systems enable rapid, reversible, and often low-power geometric reconfiguration. These trademarks make them
well suited for reflective display technologies. Digital micro-mirror devices (DMD) have shown wide adoption in
projection systems through the commercialization of micro-mirror arrays that pivot to modulate light.78 Pixtronix’s
digital micro-shutter technology is an experimental emissive direct-view display that uses laterally translating
shutters for light modulation.79 By eliminating inefficient optical components, the Pixtronix MEMS-based shutters
achieve over 50% optical transmission efficiency and reduced power consumption compared with LCDs. However, the
technology has seen limited commercial adoption. MEMS-based direct view displays have not yet hit a wider market despite
significant research efforts, most notably by Qualcomm with their “Mirasol” project, an interferometric modulators
(IMOD) display, originally introduced by Mark Miles in 1997.80 Despite Mirasol not achieving the expected commercial
success, MEMS-based direct-view displays continue to intrigue.

## 6.1 Interferometric Modulator Display

Each sub-pixel of an IMOD consists of a Fabry–Perot etalon composed of a movable metallic mirror and a semitransparent
glass upper layer [see Fig. 12(a)]. When light falls on the glass, it is split into two beams, with one beam reflected
on the glass and one on the metallic surface. The traveled distance difference between the two beams results in a phase
shift that affects the

Fig. 12 Schematic drawing of the IMOD concept. Incoming light strikes a semi-transparent layer, where it is partially
reflected and partially transmitted into a resonant cavity. Within this cavity, the light undergoes multiple reflections
between the layers. Outgoing light of a specific wavelength then constructively interferes with the incoming light,
leading to the color perception of that element. This process allows for precise control over the displayed color by
tuning the gap g between the layers.

![Image](figures/figure-14.png)

<!-- PDF page 15; printed page 020901-15 -->

interference pattern of the reflected light. Tuning the gap between the glass and metallic layer changes the phase shift
and thus the wavelength at which constructive interference occurs. This sets the perceived color of the individual
sub-pixels.

For the most simplistic IMOD, which consists of a single layer with a reflective backplane, the gap (g) to enhance a
specific wavelength λ is given as

$$g=m\frac{\lambda}{\cos(\theta)2n}.\tag{8}$$

where m is an integer ð1;2; 3; : : : Þ, n is the refractive index of the medium between the layers, and θ is the angle
of incidence. For normal incidence θ 1⁄4 0 and considering air n 1⁄4 1 to be a medium, Eq. (8) simplifies to

$$g=m\frac{\lambda}{2}.\tag{9}$$

To create black, the gap g is reduced such that the reflected wavelength maxima is moved outside the visible spectrum
and absorbed within a thin film within the stack. This is accomplished through electrostatic actuation, essentially
collapsing the metal membrane onto the thin film stack. To avoid failure due to stiction in the collapsed state,
stiction bumps are introduced.81 In real devices, multiple layers might be used; in such cases, it is advised to refer
to the transfer matrix method to compute the reflected color.

## 6.1.1 Implementations

Figure 13 shows the concept and full-scale realized tablet prototype of a Mirasol Qualcomm display. Each pixel can
switch between a reflective colored state and an absorptive black state, in which the initial gap of the subpixel cavity
controls the reflected wavelength.

As can be deduced from Eq. (8), IMODs possess by design an inherent property of incidentangle sensitivity, resulting in
observable variations in perceived colors dependent upon the angle of incidence. To mitigate this issue, a diffuser can
be introduced on top of the Imod pixel array,83 as depicted in Fig. 14.

As mentioned in the previous section, the initial height of the Imod sub-pixel defines the reflected wavelength.
However, as in all reflective display technologies, the use of a horizontal RGB leads to suboptimal contrast due to area
sharing, which reduces the white state reflectivity. Thus, an innovative single-mirror continuously tunable pixel design
that uses interferometric absorption,85 instead of reflection was proposed. Single mirror interferometric (SMI) color
regulation is achieved using interferometric absorption [see Fig. 15(a)]. Incoming light, interfering with reflected
light, produces standing waves with varying peaks and nulls based on the light spectrum. By strategically placing a thin
absorber at a null for a specific wavelength, selective non-absorption allows for reflection of that spectral component.
All other wavelengths are absorbed, resulting in a saturated color reflection. Figure 15(a) displays the reflected color
as a function of the absorber-mirror gap. In practice, the mirror is mobile, and the absorber is fixed on the substrate.
This essentially allows each pixel to be modulated over the entire visible

Fig. 13 The IMod architecture and full-sized display prototype. (a) Schematic drawing of a pixel element showing the on
(color) and off (state);82 (b) picture of a prototype tablet utilizing the Qualcomm Mirasol.

![Image](figures/figure-15.png)

<!-- PDF page 16; printed page 020901-16 -->

spectrum, drastically increasing the reflectivity. On the other hand, SMI also suffered from angle dependence. Figure 15
shows an SMI display at different angles of incidence. One can perceive the color shift in Fig. 15(b), when observing
from 10 deg or 40 deg.

Fig. 14 Schematic view of a Qualcomm Mirasol display unit, including, in particular, a front-facing diffuser film to
reduce angle dependence. Adapted with permission from from Ref. 84, copyright (1999), Society of Photo-Optical
Instrumentation Engineers (SPIE).

![Image](figures/figure-16.png)

Fig. 15 Interferometric absorption-based continuous color tuning: (a) schematic illustrating the principle of color
regulation through strategic placement of absorbers in standing light waves. (b) Off-axis viewing examples: camera
directed at 10 deg off surface normal, 20 deg, and 40 deg. Image adapted with permission from Ref. 86, copyright (2015),
Optica.

![Image](figures/figure-17.png)

In recent years, a graphene membrane-based IMOD (GIMOD) was proposed;87 it potentially allowed for refresh speeds of up
to 400 Hz and 5 μm pixel resolution, which translates roughly into a smartphone with a 12K display resolution, a 20
times increase in resolution compared with the typical phone resolution (QHD, 2560 × 1440 pixels). Current designs of
GIMOD are fabricated using graphene-covered micro-holes, essentially creating a voltage-controlled graphene micro-drum,
where the initial cavity and the subsequent deflection of the drum control the reflected wavelength. This allows for
analog control over the pixel’s color, yielding continuous full-spectrum reflective-type pixels. Simulations show a CR
of 1:3 utilizing 29 layers of graphene. For vibrant reflective displays, this number must be increased by at least three
times. Nevertheless, the high frame rate, resolution, and full-spectrum pixel are promising avenues.

## 6.1.2 Outlook

MEMS-based IMOD reflective displays have been developed88 into fully functional prototypes with impressive optical
characteristics, such as 80% white state reflectivity, CRs reaching 1:30,86 and fast switching times of 120 Hz,85 which
allows for full video playback. As with any movable

<!-- PDF page 17; printed page 020901-17 -->

structure in the microscale, hermetic sealing and packaging become very important for the longevity of the device.
Gas-impermeability of graphene might ease the packaging constraints for GIMOD devices; however, their CR of 1:3 needs to
be improved.

## 6.2 Other MEMS-Based Reflective Display Technologies

Hereafter, two further early-stage MEMS-based potential reflective display technologies are briefly introduced. Both
approaches still need substantial developments to move from early-stage demonstrators to large-scale production.

## 6.2.1 Mechanical light shutter

A mechanical light shutter functions by actively introducing an object into and out of the light’s trajectory, casting a
shadow on an absorptive or reflective layer. Such implementations can be observed in Jutzi et al. work.89,90 Figure 16
demonstrates the utilization of micro-flaps to alternate between a reflective state (flaps raised, producing a white
pixel) and an absorptive state (flaps lowered, resulting in a black pixel). To optimize the CR, the anchoring system of
the flaps should take as little visible area as possible; thus a good balance between flap size and anchor needs to be
found. Increasing the size of the flaps comes with drawbacks such as slower switching speeds, reduced pixel density, and
potentially compromised reliability. Nevertheless, this design offers the possibility of excellent CRs.

## 6.2.2 Mechanically tunable metasurface reflectivity modulator

Recently, an MEMS-based actively tunable metasurface was shown to be able to modulate the reflectivity in the visible
spectrum.91 The working principles and a microscope image of a segmented display prototype are shown in Fig. 17. The
idea is to vertically displace a membrane punctuated with a regular pattern of holes, each hosting a stationary
nano-disk, which effectively tunes the surface geometry and subsequently, light absorption and reflectivity.

## 7 Electrowetting

Electrowetting is the act of applying an electric potential to modulate surface wettability. This phenomenon has found
numerous applications in microfluidic devices92 and varioptical lenses.93 In 2002, Robert Hayes and Bokke Feenstra from
Philips Research filed a patent94 and published95 their results one year later, in which they demonstrated a video speed
response time optical switch to be utilized in display systems, highlighting the potential of such systems. As with many
reflective display innovations, the main motivation was to propose a video-capable solution. The key idea behind
electrowetting-based reflective displays is colorant transport in and out of a light path by expanding and retracting
colored liquids within a pixel unit. Similar to the Mirasol display, substantial research efforts by Philip’s spinoff
Liquidvista, later owned by Amazon and then Samsung, never fully substantiated into a commercial product.

Fig. 16 Micro-mechanical light shutter. (a) Schematic of the actuation method and (b) optical microscope image of the
final prototype device.90 The applied voltage was 135 V. Images adapted with permission from Ref. 89, copyright (2010),
SPIE Proceedings.

![Image](figures/figure-18.png)

<!-- PDF page 18; printed page 020901-18 -->

Fig. 17 Mechanically tunable metasurface reflectivity modulator. (a) Schematic drawing of working principle, aligned
surfaces reflect light, whereas displaced surfaces absorb it. (b) An optical microscope image shows the EPFL logo on a
segmented display, visible when switched from idle to actuated states. Image under open access CC-BY 4.0. from Ref. 91,
copyright (2023), ACS Photonics.

![Image](figures/figure-19.png)

## 7.1 Working Principle

The Young–Lippmann’s equation96 captures the electrowetting phenomenon in its most basic form. It describes how the
contact angle of a conductive liquid changes in response to an applied voltage between a liquid and an isolated
substrate, given as

$$\cos(\theta)=\cos(\theta_0)+\frac{CV^2}{2\gamma}.\tag{10}$$

where θ is the contact angle after applying the voltage, V; θ0 is the initial contact angle, and C is the capacitance
between the liquid and substrate, which depends on the insulation material ðε0εr d Þ. Finally, γ is the interfacial
tension.

In most electrowetting-based pixels, two fluids coexist. The first is usually an insulating oil ink. The second is a
conductive transparent liquid electrolyte, such as DI water. At equilibrium, the colored oil film lays between a
hydrophobic insulator coating of an electrode. With the application of a potential, the stack becomes no longer
energetically favorable, resulting in the water displacing the oil while reducing its contact angle from θ0 to θ with
respect to the hydrophobic layer, as can be seen in Fig. 18(a). The colored oil film can essentially be opened and
closed like a curtain.

The oil displacement happens in different stages,98 namely oil film rupture (initiation stage), oil-dewetting, and
finally a slower oil drop rearrangement stage. A threshold voltage is needed for the initial oil rupture. Charges
accumulate at the interface between oil and water when electricity is applied, creating pressure and causing the oil to
undulate due to Rayleigh-Taylor

Fig. 18 Electrowetting display mechanism: (a) schematic of a unit pixel cell demonstrating the transition between
expanded and contracted oil states, indicative of the “curtain-like” movement of the colored oil film modulated by
potential application; (b) Actual device implementation showcasing the technology in practice. Image source from
Ref. 97. Video: The Electrowetting Display IEEE Spectrum YouTube channel.

![Image](figures/figure-20.png)

<!-- PDF page 19; printed page 020901-19 -->

instability.99 As these undulations increase, the water ultimately breaks through to the dielectric substrate, resulting
in a three-phase contact line. Due to the induced change in contact angle by electrowetting, the water then forces the
oil to one side. The reverse mechanism or receding process is more straightforward, with the oil re-wetting the
hydrophobic surface as the water retracts.

## 7.2 Implementations

Electrowetting-driven reflective pixels pose several challenges that need to be addressed for reliable operations and
increased optical performance. For instance, the contrast between covered and uncovered states, often referred to as
“white area fraction” or “aperture,” needs to be maximized. Naturally, the colored oil cannot completely disappear from
the light path. In the retracted state, there will still be some fraction of the pixel that will display the colors of
the oil. This fraction depends on the pixel size and oil film thickness. Figure 19(a) depicts the relation between the
pixel size and aperture for different oil thicknesses. The fraction is computed by assuming a hemispherical sphere oil
droplet in the contracted state hosted in a rectangular pixel. Using volume conservation between expanded and contracted
oil, the surface fractions can be easily computed. 40m 5m

One can observe that, for pixel sizes below 40 μm and 5 μm oil thickness, the aperture drops below 50%. Thus, to
increase the display resolution, thinner oil thicknesses are needed. To minimize light bleeding through, oils with
higher molar extinction coefficients are thus more desirable.

Another challenge to overcome is contact angle hysteresis (CAH). CAH is a well-known physical phenomenon in
electrowetting. It is defined as the difference between the advancing contact angle and the receding contact angle
observed at the same voltage. Figure 19(b) illustrates an example in which there is an aperture discrepancy, albeit with
the same final applied potential. Increasing the voltage from 0 to 20 V yields a smaller aperture than decreasing the
voltage from 30 V to 20 V. CHA makes it more challenging to control precise gray levels in electrowetting displays. CHA
has been attributed to random pinning forces, which are caused by surface heterogeneities at smaller scales.88 These
forces can be successfully reduced utilizing an increasing alternating voltage scheme,101 which leads to sufficient
vibrational energy to overcome the pinning forces.

Finally, it is also important to account for the so-called “backflow problem.” In electrowetting systems, a dielectric
material is used to separate the conducting electrodes from the liquid. When applying a potential to the system, charge
trapping can occur in the dielectric layer. These remaining charges can cause the fluid to flow back, even when a
constant DC voltage is applied. Charge trapping significantly impacts the stability of electrowetting-based devices.
Asymmetric alternative polarity driving schemes102 are said to reduce charge trapping. In essence, any

Fig. 19 Electrowetting challenges. (a) Relationship between pixel size and aperture across different oil film
thicknesses. In smaller pixels, thicker films decrease the visible white/transparent area. However, thinner films let
more light through, which can lower the contrast. (b) Optical microscope images showing contact angle hysteresis.100
Adapted with permission from Ref. 100 under CC BY 4.0 DEED, copyright (2021), Frontiers in Physics.

![Image](figures/figure-21.png)

<!-- PDF page 20; printed page 020901-20 -->

remaining trapped ions are removed by applying a reset pulse, a small voltage drop with opposite polarity at the signal
termination point.

## 7.3 Outlook

Electrowetting-based displays have undergone excessive research and development both in the commercial industry as well
as in academic research. Despite their potential for color and video reflective display technology, this innovation
never ventured beyond proof-of-concept prototypes. Manufacturing difficulties, such as proper sealing and longevity
under varying conditions, might have been the cause. Moreover, with advancements in display technology, particularly in
terms of resolution, electrowetting displays have become less competitive in terms of image quality because oil
thickness and pixel size are tightly linked. Nevertheless, electrowetting technology remains a promising area of
research with potential applications in areas such as e-readers, smart glasses, and flexible displays. Current efforts
are focused on low-power sunlight-readable electronic billboards as this application is less stringent on display
resolution.

## 8 Electrochromic

Electrochromism refers to the phenomenon in which a material’s optical properties – transmittance, absorbance, or
reflectance—can be reversibly and semi-persistently modified under the application of an electrochemical potential
difference. The word “electrochromisn” was first introduced in 1961 by Platt103 upon his findings that the absorption
and emission spectrum of certain dyes could be shifted by applying an electric field. Eight years later, the use of
electrochromic materials for display applications was suggested by Deb.104 By then, the slow switching speed was noted
as a potential challenge. To this day, electrochromism has been utilized in various applications that do not require
fast switching, most notably in smart windows, first reported by Granqvist and Carl M. Lampert Kim in 1984,105,106 as
well as auto-dimming rear-view mirrors.107,108 Further applications are protective eyewear109,110 and adaptive
camouflage.111,112

## 8.1 Working Principle

The core principle of electrochromic materials is their ability to change their absorption bandgap, by adding or
removing electrons through redox reaction. Electrochromic materials can most often be switched between a transparent
(“bleached”) state and a colored state or between two colored states. Polychromic materials may exhibit several
colors.113,114 The primary mechanisms to achieve a change in electron state are redox reactions, either directly induced
or through ion intercalation. The specifics depend on the type of electrochromic material.

## 8.2 Implementations

Electrochromic materials can generally be classified according to their solubility,115 leading to different device
architectures, as depicted in Fig. 20.

Type I EC materials remain soluble in both their reduced and oxidized states. Examples include viologen and heptyl. In
device architectures, these materials often have their electrochromic species dissolved directly within an electrolyte,
which is sandwiched between two

Fig. 20 Electrochromic display. (a) Schematic diagrams of three types of electrochromic devices are shown: (a) type I,
which operates in a solution-phase; (b) type II, a hybrid system; and (c) type III, also known as the “battery-like”
ECD. Kþ represents cations, which could be Liþ or Hþ, and A−represents anions, for instance, ClO− 4, Cl−, BF− 4, or
PF− 6. Images adapted with permission from Ref. 115 under CC BY 4.0 DEED, copyright (2020), Chemistry Europe.

![Image](figures/figure-22.png)

<!-- PDF page 21; printed page 020901-21 -->

transparent conductive oxide substrates. Although the fabrication of such devices is relatively straightforward, a
critical challenge arises in ensuring the sealing of the devices to avert potential electrolyte leakage. Furthermore,
there is an inherent requirement for a continuous supply of current or voltage to uphold their redox states, which could
lead to increased energy consumption.

Type II EC materials remain soluble when in their colorless redox state but transition to form a solid film upon the
electrode surface when subjected to specific conditions. Devices leveraging Type II materials integrate a redox mediator
in the electrolyte, acting as a counterbalance during the redox reactions. This interaction, although promising, does
have its challenges. A significant one is the “loss current,” a consequence of the direct contact between the redox
electrolyte and the EC layer. However, innovations, such as electronic barrier layers116 and catalytic IrOx layers,117
provide potential solutions to this challenge.

Type III EC materials stand apart due to their inherent solidity in both redox states. This means that they consistently
form an insoluble film on the electrode surface. The gamut of Type III materials is extensive, comprising groups IV and
V transition metal oxides, conductive polymers, Prussian blue, and certain metal polymers. In device configurations,
these materials typically feature in thin-film “battery-like” setups. Such a device incorporates two substrates coated
with transparent conductors, an electrochromic layer, and another layer designated for ion storage or as an additional
electrochromic layer. The addition of an ion-storage layer with ample charge capacity ensures a complete and effective
color transition, resulting in a device that boasts impressive electrochemical stability.

In practical applications, particularly when considering reflective displays, Type III often emerges as the preferred
choice due to its inherent stability and enhanced optical properties.

Electrochromic materials transition from a neutral to an “excited” state during redox reactions, challenging the
development of bistable electrochromic devices (ECDs) as they tend to revert to their stable, lower-energy states. This
reversion diminishes the longevity of the desired optical state. To counter this, proton-coupled electron transfer118
and bond-coupled electron transfer119 have been implemented. These methods avoid the formation of high-energy
intermediates, which can destabilize the material, reducing its effective life and performance. Electrode materials are
fundamental in electron transfer processes. They require meticulously designed energy levels (Fermi levels) that
synchronize with those of electrochromic materials. Proper alignment ensures efficient electron transfer and minimizes
reverse transfers.120 Metal dendrites, irregular tree-like structures, can form on electrode surfaces. Their presence
disrupts the uniformity of the electron transfer, leading to inconsistent color transitions. To combat this, copper ions
have been integrated into bismuth-based systems. The copper ions oxidize bismuth atoms, creating a smoother, spherical
morphology. This morphology reduces the chance of dendrite growth, ensuring a consistent electron transfer and uniform
color change.121 For enhanced device responsiveness, multivalent ions, such as Al3þ, are incorporated into tungsten
oxide WOx materials. These ions facilitate rapid and reversible ion insertion/extraction.122 The increased electrostatic
forces between ions lead to an accelerated electron transfer, improving the device response time. To diversify the color
palette and fasten switching, electrochromic materials are paired with metasurfaces, including Fabry–Perot
cavities123,124 and metallic nanoslits.125 These metasurfaces induce structural colors and optimize charge-diffusion
characteristics. The result is a broader color spectrum and reduced switching times.

Innovative pixel designs utilizing both lateral and vertical configurations have emerged.126,127 Examples include Urano
et al.’s three-layered CMY ECD128 and RICOH’s full-color, flexible matrix display (see Fig. 21). These leverage
vertically stacked electrochromatic elements. Such stacking allows for brighter color displays, and their flexibility
enhances the device adaptability.129

## 8.3 Outlook

EC displays offer numerous benefits: they are inexpensive, low-power, insensitive to viewing angle, and capable of
semi-bistability. Although electrochromism has already been commercially successful in smart window and glare-reduction
applications, commercial displays are still limited to simple monochromatic segmented displays. Continued research and
development in electrochromic materials and device architectures are essential to unlocking their full potential and

<!-- PDF page 22; printed page 020901-22 -->

drive advancements, particularly concerning switching speed, which currently lies around 0.8 Hz.77 Innovations, such as
the introduction of PEDOT nanotube arrays, have shown promise in achieving ultrafast switching speeds compatible with
moving-image display technology, suggesting that continued innovation in material science could overcome existing
limitations in switching speeds and pave the way for more versatile electrochromic displays.130

Fig. 21 Multi-layered full-color reflective electrochromic pixel. (a) Schematic representation of a unit and (b) a
photograph depicting a full-color, flexible, active-matrix-based implementation of the display design. Images adapted
with permission from Ref. 129 (permission pending), copyright (2013), Ricoh.

![Image](figures/figure-23.png)

## 9 Phase Change

Phase-change materials exhibit reversible transitions between amorphous and crystalline phases in response to an
external stimulus, such as heat, light, or electrical current. Concurrently, variations in physicochemical attributes,
encompassing alterations in optical absorbance, and electronic conductance, are observed.131 The phases can be switched
very fast, typically 300 ns for GeTe,132 50 ns for Ge2Sb2Te5, 40 ns for GeSb2Te4, and 30 ns for GeSb4Te7.133 Thus,
phasechange materials (particularly the germanium antimony tellurium alloy Ge2Sb2Te5) have been greatly used in
information storage devices since the 1960s,134 for instance, in optically re-writable DVDs (DVD-RAMs)135 and
non-volatile resistive based electronic memories.136 Hosseini et al.136 pioneered the idea of utilizing nanometer-thin
phase-change materials and transparent conductors to generate color-switchable reflective pixels based on an incident
angle-insensitive strong IMOD.137 Due to their solid-state nature based on phase change materials, this type of display
technology has been introduced as solid-state reflective display (SRD). However, due to limitations with electrical
addressing, discussed in the following section, the previously mentioned switching times cannot be obtained with current
display designs. Nevertheless, the fact that this technology does not require any moving parts makes it especially
interesting from a manufacturing point of view as devices could be made using conventional standard vacuum sputtering,
bypassing the requirement for sophisticated encapsulation.

## 9.1 Working Principle

The material science behind phase change is complex. It has been shown that the switching from crystalline to amorphous
states when directly applying current occurs due to rapid heat-induced dislocation nucleation, electrical wind force
transport, and eventual jamming in the crystal, which leads to amorphization.138 By contrast, the
amorphous-to-crystalline transition occurs by heating the material above its crystallization temperature. Upon cooling
down, the atoms reorganize into a crystalline lattice, resulting in a lower resistance state. The variations in optical
properties arising from these structural modifications can be further understood by examining the corresponding changes
in bonding strengths. It was found that the crystalline phase exhibits resonant bonding, whereas the amorphous phase
shows covalent bonding.138 The greater degree of electron delocalization in resonant bonding materials, as opposed to
covalent bonding, can have a significant impact on the optical characteristics of the material. The higher level of
interaction between delocalized electrons and incident electromagnetic waves produces specific absorption, transmission,
and reflection characteristics, resulting in optical performances that differ significantly from materials having
localized covalent bonding. On a broader scale, individual phase-change based pixel designs differ. However, the primary
objective is to engineer

<!-- PDF page 23; printed page 020901-23 -->

a wavelength-dependent tunable resonance that is then tuned by the phase-change material, inherently altering the
resonance conditions due to a change of optical properties when switching from an amorphous to a crystalline state.

Fig. 22 Microheater-based phase change display system (Fig. 21). (a) Schematic of the SRD pixel structure (b)
microheater array, (c) the assembly comprising a mirror and thin-film interference stack, and (d) a microscope
photograph demonstrating a 24 × 24 pixel region being dynamically updated with a sequence of letter. Images adapted with
permission from Ref. 140 (permission pending), copyright (2019), Society for Information Display.

![Image](figures/figure-24.png)

## 9.2 Implementations

When directly applying current to the switch state, the material undergoes a partial phase change until a low-resistance
pathway is established.139 This pathway subsequently functions as a channel for the residual current, impeding a
full-phase transition. This phenomenon is referred to as the “filamentary switching issue.”139 Utilizing nanoscale
pixels can effectively reduce this issue. However, addressing such a vast number of pixels individually and
simultaneously presents a challenge. As the number of pixels in a display grows, the amount of computing power and
energy needed by the circuits that control each pixel also rises significantly.140 Thus, alternative more homogenous
switching methods need to be envisioned. To avoid the filamentary switching issue, much effort has been devoted to the
design of decoupled micro-heaters as a means to uniformly fully switch the phase-change material,140 as shown in
Fig. 22. A typical phasechange-based pixel structure is depicted in Fig. 22(a). The SRD pixel consists of three primary
layers: an electronic substrate directing drive signals to specific pixels, a microheater that converts electrical
signals to uniform thermal pulses, and finally an optical layer reflecting specific colors in stable phase-change
material states via strong interference effects.

## 9.3 Outlook

Efforts to increase color saturation can be achieved by a higher refractive index and lower loss materials than GST or
GeTe, such as antimox trisulphide ðSb2S3Þ and antimony triselenide ðSb2Se3Þ.141 Although noticeable switchable color
changes are possible, little has been demonstrated of producing a black state, which is needed for a fully functional
display. When switching phases, the real part of the refractive index GST material usually exhibits a change of roughly
1.5 to 2, whereas the absorption coefficient can be altered by more than 3.142 Essentially, for a given pixel design,
the resonance sensitivity to a variation in optical constants needs to be increased for a black state to exist. In such
a state, the resonance would need to be shifted outside the visible domain. So far this remains a challenge.
Furthermore, the use of microheaters severely limits the switching times. Frequencies of mere 2 Hz are reported.140 With
approximately 100 mJ∕cm2142 microheaters also consume more energy per frame than electrostatic-driven systems.

## 10 Tunable Photonic Crystal

The theoretical work of Yablonovitch143 and John144 serves as the foundation for the idea of photonic crystal materials.
Materials can be created to alter photon properties in a manner comparable to how conventional semiconductor crystals
alter electron properties. The propagation of light waves through the substance can be controlled by periodically
structuring the material. This makes it possible to produce photonic band gaps, which are wavelength bands that cannot
pass through the substance. Since its early days, photonic crystals have been successfully applied in

<!-- PDF page 24; printed page 020901-24 -->

various examples, such as filters, sensors, solar cells, and recently smart windows to regulate building energy
consumption.145 Photonic crystals have emerged as an interesting technology for reflective displays due to their
continuous color tunability, essentially avoiding the need for sub-pixelation for display colors. This can lead to
higher color purity and increased resolution.

## 10.1 Working Principle

1D photonic crystals’ colorful appearances result from interference and reflection. The wavelength that is coherently
scattered is centered on λ and is estimated by the Bragg-Snell equation:146

$$\lambda=2D\left(n_{\mathrm{eff}}^2-\cos^2(\theta)\right)^{1/2}.\tag{11}$$

where λ is the wavelength of the reflected light, neff is the average refractive index of the photonic materials, D is
the diffractive plane spacing, and θ is the Bragg angle of incidence.

Based on Eq. (11), the different ways to alter the reflected wavelength can be inferred, namely by modifying three
variables: the diffractive plane spacing, the average refractive index, or the Bragg incidence angle.

## 10.2 Implementations

Most photonic crystal-based reflective pixels are based on acting on the inter-plane distance to modulate the reflected
wavelength. The key challenges are to find fast-switching methods as well as ways to respond to the inherent angle
incidence dependence of such photonic crystals, which can be seen in Eq. (11).

For the most part, inter-plane distance variations are achieved in electrochemical swellingdriven color change
displays147 and electrokinetic-driven reflective displays.148 Although crystalline structures have shown excellent color
tunability, their practical application has been severely impeded by their intrinsic angle dependency. It has been
demonstrated149,150 that colloidal structures that are made up of particles with sizes similar to optical wavelengths
and exhibit short-range order but lack lattice periodicity, exhibit independence of the incident angle. These
systems148,151 have therefore been seen as promising candidates for color-tunable reflective displays, albeit with lower
peak reflectivity values of generally around 25% to 30% [see Fig. 23(c)].

Fig. 23 Photonic display pixel. (a) Schematic design of the photonic display pixel. (b) Photographs at varying bias
voltages: 1.0 V, 2.5 V, and 4.0 V. (c) Reflection spectra recorded at increasing bias voltage levels. (d) The 165 nm
shift of the photonic band position from 655 to 490 nm, governed by the applied voltage. Images adapted with permission
from Ref. 148, copyright (2010), Advanced Materials.

![Image](figures/figure-25.png)

<!-- PDF page 25; printed page 020901-25 -->

## 10.3 Outlook

Switching times of approximately 50 ms148 have been documented in tunable photonic crystals, which, although not yet
suitable for video applications, demonstrate potential for improvement. One possible approach to enhancing the switching
speed is through the employment of lowerviscosity liquids, which may facilitate a faster response time. Furthermore, the
trade-off between angle independence and color intensity presents another challenge. Although amorphous photonic
structures have shown reduced angle independence, they also exhibit reduced peak reflectivity and less vibrant colors.
This is due to the incoherent scattering events caused by their disordered arrangement, resulting in weaker constructive
interference and diminished color intensity. Hierarchical photonic structures152,153 have been proposed to produce both
angleindependent and bright colors, but further investigations and optimization are required to address these
limitations and fully realize the potential of tunable photonic crystals in display technologies. Finally, it is worth
mentioning that, although continuous color can be produced, producing white without resorting back to an area-sharing
subpixel layout, such as RGB, has yet to be shown. Commercially, two companies are pioneering modulation approaches
using photonic crystals. Opalux focuses on color-tunable Photonic Ink, and Nanobrick works on full-spectrum tuning using
SiOx-coated nanoparticles.

## 11 Discussion

A comparative performance map is depicted in Fig. 24, and used hereafter for the discussion. Microcapsule
electrophoretic displays, featuring reflectance up to 44%,154 CRs of 23,155 and a frequency of 2.1 Hz,156 have achieved
commercial success. They offer an optimal blend of readability and energy efficiency with a refresh energy density of
0.58 mJ∕cm2.157 The modulation of TIR using electrophoretic mechanisms further enhances these displays, achieving
reflectance up to 83%,158 maintaining a contrast of 20,158 and reaching frequencies of around 30 Hz,48 while maintaining
an impressively low refresh energy density of 0.029 mJ∕cm2.48

ChLCDs, utilizing cholesteric LCs, present reflectance around 35%,77 and CRs close to 10.159 Their limited response time
of 0.8 Hz,77 however, restricts their utility in mobile devices, reserving them for specific applications, such as
shelf-labels, in which high refresh rates are not essential. Similarly, electrochromic displays, offering reflectance
between 40%160 and 47%161 and contrasts up to 12,160 operate at a frequency of approximately 1 Hz;160 thus they too face
challenges for integration into mainstream mobile devices.

Electrowetting displays, although nascent, exhibit promising metrics with reflectance peaking at 65%,162 though they
have a modest contrast of 1.7.162 Their highlight is a frequency that reaches 62 Hz,162 indicating a potential for fluid
video playback.

Phase change displays, characterized by their non-volatile solid-state pixels, present a reflectance of 44%,142
comparable to commercial electrophoretic displays. Despite this notable similarity in reflectance, other metrics such as
a contrast of 2.5,142 a frequency of 2 Hz,142 and a high refresh energy density of 104 mJ∕cm2142 underline areas that
need improvement for this technology to achieve a competitive standing. Additionally, producing a black state by the
sole use of SRD pixels has not yet been demonstrated.

Tunable photonic crystals stand out for their potential to display continuous colors within individual pixels. Their
current implementations, achieving white state reflections between 30% and 60%151 and reported 20 Hz frequency,5 could
be an interesting venue to explore further. The switching speed needs to be improved to yield video playback
possibilities, as well as further reduction of the angle dependence and the ability to show white.

Concluding, MEMS-based reflective displays, especially the interferometric absorptionbased design by Qualcomm, are
exemplary. They manifest a 90% reflectance,86 a contrast of 30,84 and an impressive frequency of 120 Hz,86 complemented
by a PPI of 36386 and a minimal refresh energy density of 0.004 mJ∕cm2.86

In evaluating the appropriateness of display technologies for various application sectors, it is imperative to first
consider the key performance metrics that are critical for each sector. This approach ensures a more targeted and
effective application of emerging display technologies. In the following, we assess the suitability of the reflective
display technologies discussed in this review for selected applications.

<!-- PDF page 26; printed page 020901-26 -->

Fig. 24 Performance map for reflective display technologies: this representation compares diverse reflective display
technologies based on their essential performance parameters. Microcapsule electrophoretic displays (reflectance:
44%,154 contrast: 23,155 and frequency: 2.1 Hz156) and their ChLCD (reflectance: 35%,77 contrast: 10,159 and frequency:
0.8 Hz77) and electrochromic counterparts (reflectance: 47%,112 contrast: 12, frequency: 1 Hz162) find their niche in
applications demanding static images given their constrained refresh rates. Conversely, emerging electrowetting
displays, exhibiting up to 65% reflectance and a remarkable 62 Hz frequency,155 signal promise for dynamic video
renditions. Phase change displays, with a reflectance mirroring that of electrophoretic at 44%,160 however, are marked
by a considerable refresh energy density of 104 mJ∕cm2.160 Albeit discontinued commercially, MEMS-based Qualcomm designs
achieve a stellar 90% reflectance,81 contrast-ratio of 1∶30,84 and a swift 120 Hz,84 while being impressively efficient
at 0.004 mJ∕cm2.84 Numeric values can be found in Appendix A, Table 2.

![Image](figures/figure-26.png)

## 11.1 Signage

Signage applications prioritize low power consumption, long-term image stability, and moderate refresh rates. ChLCDs are
particularly well suited for this domain, offering image maintenance without continuous power and a modest reflectance
of around 35%. Phase change displays, still in the emerging phase, also show promise for static signage due to their low
power requirements and non-volatile nature, although their current slower switching speeds make them less ideal for
dynamic content.

## 11.2 E-Readers

In the e-book and e-reader sector, key considerations include medium refresh rates, optional color, and high energy
efficiency. Microcapsule electrophoretic displays, commonly known as E Ink, stand out in this category. They balance
high readability, with reflectance up to 44%, and energy efficiency, with a refresh energy density of 0.58 mJ∕cm2,
making them a preferred choice for devices used extensively over long periods.

## 11.3 Smartwatches and Mobiles

For smartwatches and mobile applications, in which high refresh rates, superior pixel density, and full-color
capabilities are paramount, MEMS-based reflective displays take the lead. These emerging technologies boast superior
performance metrics, including high reflectance

<!-- PDF page 27; printed page 020901-27 -->

(up to 90%), impressive contrast (with a ratio of 30:1), and high-frequency operation (up to 120 Hz), making them
increasingly relevant. With a pixel density of 363 PPI, these displays are especially suitable for devices that demand
high-resolution visuals, ranging from advanced e-writers to premium consumer electronics. Smartwatches emerge as an
especially ideal candidate for MEMS-based reflective displays due to their small display footprint (facilitating the
packaging) and essential need for low-power operation as well as outdoor visibility.

## 11.4 Billboards and Large-Format Displays

For billboards and large-format displays, the focus is on sunlight readability and less stringent resolution
requirements. Here, electrowetting displays, an emerging technology, presents a viable option. They offer low power
consumption and effective sunlight readability, making them suitable for large-scale outdoor displays such as electronic
billboards, for which high resolution is not the primary concern.

Beyond core metrics, the mitigation of inadvertent internal reflections is paramount in e-paper technology. Although
these displays capitalize on ambient light reflection, undesirable internal reflections—often from thin-film
interfaces—can compromise performance. Advanced techniques, such as index matching and multilayer destructive
interference, have been employed to counteract these challenges. Notably, antireflective coatings inspired by nocturnal
moth corneal patterns163 have achieved reductions in spurious reflectivity to a mere 0.1% within the visible
spectrum.164 Raut et al. provided a thorough discussion on this reflection management.165

## 12 Conclusion

This review has covered a variety of reflective display technologies. Despite significant research efforts, reflective
displays are generally absent in typical mobile devices such as smartphones and smartwatches. This is particularly
critical given the inherent benefits of these displays, such as longer battery life and improved visibility in bright
outdoor environments. The primary obstacles hindering their widespread integration into mobile devices are the current
limitation of refresh speed and the compromised color vibrancy that many of these technologies exhibit. For example,
although reflective LCDs are capable of video playback, their white state reflectivity is constrained to approximately
9%,166 thereby affecting the saturation of displayed colors. By contrast, microcapsule electrophoretic displays showcase
a considerably higher reflectance, reaching up to 44%,165 but suffer from restricted refresh capabilities.

Within the realm of emerging technologies, ClearInk’s TIR display technology offers a promising avenue for augmenting
the update speed of electrophoretic-based displays. Concurrently, MEMS-based technologies are gaining prominence due to
their inherent rapid switching times, high CRs, and relative energy efficiency. Recent developments in this field are
particularly encouraging. For instance, preliminary research into tunable metasurfaces has revealed potential pathways
for achieving broadband tunability in the visible spectrum with displacements of a mere 150 nm.91 Furthermore,
graphene-based IMODs have demonstrated remarkable capabilities, achieving refresh rates of up to 400 Hz and ultra-high
resolution.87

The landscape of reflective display technologies, diverse and evolving, stands out for its unique advantages in the
broader spectrum of display technologies. Quantum dot light emitting diode (QLED),167 renowned for delivering impressive
visuals in emissive displays, sets a high standard with its vibrant color reproduction and deep CRs. This technology
excels in providing dynamic visual experiences, making it a top choice in settings for which image quality is paramount.
By contrast, reflective displays carve their own niche. Their strength lies in their energy efficiency and superior
visibility under bright ambient light conditions, aspects for which emissive displays such as QLED are less effective.
Reflective technology, therefore, emerges as a practical alternative in environments where power consumption and outdoor
readability are critical considerations. As ongoing research and development in reflective display technologies
progress, the prospect of integrating these energy-efficient, high-performance display systems into conventional mobile
devices is becoming increasingly feasible. The line between a static printed medium and a dynamic digital display could
become remarkably indistinct.

<!-- PDF page 28; printed page 020901-28 -->

## 13. Appendix A: Data for Comparison Graph

The refresh energy density is usually not directly given in the references cited but is computed from given power
consumption, active area, and frame refresh time. Because some technologies are more experimental, not all data is
available.

Table 2 Comparative study of performance metrics of reflective display technologies.

| Type                                      | Reflectance (%)      | Contrast             | Frequency (Hz)       | Dots per inch (DPI) | Refresh energy density (mJ∕cm 2 ) |
| ----------------------------------------- | -------------------- | -------------------- | -------------------- | ------------------- | --------------------------------- |
| Electrophoretic microcapsule              | 35 155 44 154 43 157 | 23 155 15 154 14 157 | 2.1 156              | 226 157             | 0.58 157                          |
| Electrophoretic total internal reflection | 55 46 83 158 40 48   | 20 158 16 48         | 28 46 30 158         | 212 158 227 48      | 0.029 48                          |
| LCD reflective                            | 9 166                | 25 166               | 60 166               | 69 166              | 0.03 166                          |
| LCD cholesteric                           | 30 159 35 77         | 10 159 25 77         | 0.8 77               | 100 77              | 4.7 77                            |
| Electrowetting                            | 40 168 65 162 55 169 | 1.7 162 3.3 13       | 62 162 56 13         | N/A                 | 0.013 168                         |
| MEMS interferometric modulator            | 17 88                | 80% 88               | 40 Hz 170            | 224 88              | 0.05 88                           |
| MEMS continuous color reflective          | 90 86                | 30 85                | 120 85               | 364 85              | 0.004 85                          |
| Phase change                              | 44 142               | 2.5 142              | 2 22                 | N/A                 | 104 142                           |
| Electrochromic                            | 40 160 47 161        | 12 160 10 161        | 1 160                | 200 171             | 1.1 161                           |
| Tunable photonic crystals                 | 60-30 151            | N/A                  | 1 151 0.125 172 20 5 | N/A                 | N/A                               |

## Disclosures

The authors declare that they have no relevant financial interests in this manuscript and no other potential conflicts
of interest to disclose.

## Code and Data Availability

All data are given in Table 2.

## Acknowledgments

The authors acknowledge the financial support by InnoSuisse (Grant No. 44027.1 IP-ENG).

## References

1. H. Kawamoto, “The history of liquid-crystal displays,” Proc. IEEE 90(4), 460–500 (2002).
2. Y.-J. Huang et al., “Mini-LED, micro-LED and OLED displays: present status and future perspectives,” Light Sci. Appl.
   9(1), 1–26 (2020).
3. S. Chen and S.-L. Lee, “Liquid crystal display and organic light-emitting diode display: present status and future
   perspectives,” Light Sci. Appl. 6(1), e17035 (2017).
4. Y. Shirasaki et al., “Emergence of colloidal quantum-dot light-emitting technologies,” Nat. Photonics 7(1), 13–23
   (2013).
5. J. Heikenfeld et al., “Review paper: a critical review of the present and future prospects for electronic paper,” J.
   Soc. Inf. Disp. 19(2), 129 (2011).
6. B.-R. Yang, E-paper Displays, John Wiley &amp; Sons (2022).
7. T. Goodman, Overview of the Photometric Characterization of Visual Displays, pp. 337–350, Springer International
   Publishing, Cham (2016).
8. Hertel, “Evaluating display reflections in reflective displays and beyond,” Inf. Disp. 36(2), 14–24 (2020).

<!-- PDF page 29; printed page 020901-29 -->

9. DisplayMate, “Tablet and smartphone displays under bright ambient lighting shoot-out,” (2023). (accessed 5 June
   2023).
10. H. Chen, G. Tan, and S.-T. Wu, “Ambient contrast ratio of LCDs and OLED displays,” Opt. Express 25, 33643–33656
    (2017).
11. R. Singh et al., “Improving the contrast ratio of OLED displays: an analysis of various techniques,” Opt. Mater. 34,
    716–723 (2012).
12. M. Miles et al., “Digital paperTMfor reflective displays,” J. Soc. Inf. Disp. 11, 209–215 (2003).
13. G. Yang et al., “Design, fabrication and measurement of full-color reflective electrowetting displays,”
    Micromachines 13, 2034 (2022).
14. M. E. Howard et al., “Gyricon electric paper,” J. Soc. Inf. Disp. 6(4), 215 (1998).
15. D. K. Deshmukh, J. Nirmalkar, and M. Haque, Tb3 Activated High-Color-Rendering Green Light Yttrium Oxyorthosilicates
    Phosphors for Display Device Application, pp. 1–12, CRC Press (2020).
16. B. Comiskey et al., “An electrophoretic ink for all-printed reflective electronic displays,” Nature 394, 253–255
    (1998).
17. R. J. Fleming, Fast-Switching Mode with CLEARInk Structure, Ch. 4, pp. 75–98, John Wiley Sons, Ltd. (2022).
18. H.-L. Kang et al., “Analysis of particle movement by dielectrophoretic force for reflective electronic display,” J.
    Disp. Technol. 12, 747–752 (2016).
19. T. Whitesides et al., “10.2: towards video-rate microencapsulated dual-particle electrophoretic displays,” in SID
    Symp. Digest of Tech. Pap., Wiley Online Library, Vol. 35, pp. 133–135 (2004).
20. Wikipedia Contributors, “E ink — wikipedia, the free encyclopedia,” (2023). https://en.wikipedia.org/w/
    index.php?title=E\_Inkoldid=1157073256 (accessed 22 September 2023).
21. [bfishadow, “Kindle voyage with origami cover,” (2014). https://commons.wikimedia.org/wiki/File: Kindle\_Voyage\_with\_cover.jpg (accessed 23 December 2023).](https://commons.wikimedia.org/wiki/File:Kindle_Voyage_with_cover.jpg)
22. M. Wang et al., “Electrophoretic display device,” US Patent 9,557,623 (2017).
23. H. Du, H. Gu, and X. Wang, “Silane-containing pigment particles for electrophoretic display,” US Patent 9,382,427
    (2012).
24. G. S. Roberts et al., “Electrostatic charging of nonpolar colloids by reverse micelles,” Langmuir 24, 6530– 6541
    (2008).
25. J. Albert et al., “Encapsulated electrophoretic displays having a monolayer of capsules and materials and methods
    for making the same,” (2003).
26. R. M. Webber, “10.4: image stability in active-matrix microencapsulated electrophoretic displays,” in SID Symp.
    Digest of Tech. Pap., Vol. 33, p. 126 (2002).
27. M. T. Johnson et al., “High-quality images on electrophoretic displays,” J. Soc. Inf. Disp. 14(2), 175 (2006).
28. T. A. Sjodin, “Methods for driving electro-optic displays,” US Patent 8,289,250 (2017).
29. L. Cao et al., “Electrophoretic media with improved binder,” US Patent Application 11/552,210 (2007).
30. R. J. Wilcox et al., “Electro-optic displays with reduced remnant voltage,” US Patent 8,558,783 (2013).
31. A. Bouchard et al., “68.5l: Late-news paper: advances in active-matrix color displays using electrophoretic ink and
    color filters,” in SID Symp. Digest of Tech. Pap., Vol. 37, p. 1934 (2006).
32. E. Huitema and I. French, “E ink’s technicolor moment: the road to color e-paper took two decades,” IEEE Spectrum
    59, 30–35 (2022).
33. D. Hertel et al., “39-1: idistinguished paper:/i gamut rings of reflective ePaper displays with combined frontlight
    and ambient illumination,” in SID Symp. Digest of Tech. Pap., Vol. 53, pp. 485–488 (2022).
34. [M. Kozlowski, “E INK gallery 3 vs e INK kaleido 3 color e-paper - good e-reader,” https://goodereader.com/ blog/e-paper/e-ink-gallery-3-vs-e-ink-kaleido-3?doing\_wp\_cron=1712047210.0039799213409423828125 (accessed 2 April 2024).](https://goodereader.com/blog/e-paper/e-ink-gallery-3-vs-e-ink-kaleido-3?doing_wp_cron=1712047210.0039799213409423828125)
35. C.-M. Chang, C.-H. Chiu, and Y.-Z. Lee, “P-117: direct printed plastic color filter for color electrophoretic
    displays,” in SID Symp. Digest of Tech. Pap., Vol. 42, pp. 1545–1547 (2011).
36. Y.-H. Lai et al., “P-148l:ilate-news poster/i: direct photolithographic color filter for 14.1-inch flexible color
    electrophoretic displays,” in SID Symp. Digest of Tech. Pap., Vol. 43, pp. 1365–1367 (2012).
37. K. Akamatsu et al., “16.3: a 13-inch flexible color EPD driven by low-temperature a-si TFTs,” in SID Symp. Digest of
    Tech. Pap., Vol. 42, pp. 198–201 (2011).
38. H. Du and H. Zang, “Color display device,” US Patent 9,285,649 (2016).
39. T. Hao, “Chapter 3 - The positive, negative, photo-ER, and electromagnetorheological (EMR),” Stud. Interface Sci.
    22, 83–113 (2005).
40. P. Bai, Z. Yi, and G. Zhou, “An improved driving scheme in an electrophoretic display,” WO/2004/104977 (2004).
41. Z. Wang and Z. Liu, “The key technology of ereader based on electrophoretic display,” in 2nd Int. Conf. Softw.
    Technol. and Eng. (2010).
42. T. Hao, “Physics of electrorheological fluids,” Stud. Interface Sci. 22, 235–340 (2005).

<!-- PDF page 30; printed page 020901-30 -->

43. Y.-D. Zhang et al., “Backflow effect enabling fast response and low driving voltage of electrophoretic e-ink
    dispersion by liquid crystal additives,” Sci. Rep. 9, 13981 (2019).
44. R. Laughlin and T. Hazelton, “Frustrated total internal reflection an alternative for optical cross-connect
    architectures,” in Conf. Proc. LEOS’98. 11th Annu. Meet. IEEE Lasers and Electro-Opt. Soc. 1998 Annu. Meet. (Cat.
    No.98CH36243), IEEE (1998).
45. M. A. Mossman, L. A. Whitehead, and S. P. Rao, “P-83: grey scale control of TIR using electrophoresis of sub-optical
    pigment particles,” in SID Symp. Digest of Tech. Pap., Vol. 33, p. 522 (2002).
46. M. A. Mossman, V. H. Kwong, and L. A. Whitehead, “A novel reflective image display using total internal reflection,”
    Displays 25, 215–221 (2004).
47. [Wikimedia Commons contributors, “TN-LCD prototype image,” https://commons.wikimedia.org/wiki/File: TN-LCD-schematic-MS-208kB.png (accessed 2 April 2024).](https://commons.wikimedia.org/wiki/File:TN-LCD-schematic-MS-208kB.png)
48. R. Fleming et al., “36-3: tablet-size eTIR display for low-power ePaper applications with color video capability,”
    in SID Symp. Digest of Tech. Pap., Vol. 50, pp. 505–508 (2019).
49. W. He et al., “Driving waveform design of electrophoretic display based on optimized particle activation for a rapid
    response speed,” Micromachines 11, 498 (2020).
50. W. D. Helfrich and M. D. Schadt, “Lichtsteuerzelle,” 1793770A, filed (31 December 1972).
51. D.-K. Yang et al., “Control of reflectivity and bistability in displays using cholesteric liquid crystals,” J. Appl.
    Phys. 76, 1331–1333 (1994).
52. M. Schadt and W. Helfrich, “Voltage-dependent optical activity of a twisted nematic liquid crystal,” Appl. Phys.
    Lett. 18, 127–128 (1971).
53. Y. Nakajima et al., “22.4: invited paper: ultra-low-power LTPS TFT-LCD technology using a multi-bit pixel memory
    circuit,” in SID Symp. Digest of Tech. Pap., Vol. 37, p. 1185 (2006).
54. M. Tamaki et al., “A memory-in-pixel reflective-type LCD using newly designed system and pixel structure,” J. Soc.
    Inf. Disp. 22, 251–259 (2014).
55. S. K. Kaisha, “Thin-film electroluminescent panel,” Displays 15, 194 (1994).
56. A. Bezrukov and Y. Galyametdinov, “Orientation behavior of nematic liquid crystals at flow-wall interfaces in
    microfluidic channels,” Coatings 13(1), 169 (2023).
57. R. James et al., “Twist walls, disclinations and the in-plane switching structure,” in 2nd Int. Workshop on Liquid
    Crystals for Photon (LCP-2008), pp. 66–67 (2008).
58. A. Buka and N. Éber, Flexoelectricity in Liquid Crystals: Theory, Experiments and Applications, World Scientific
    (2013).
59. J. Jones, “Defects, flexoelectricity and RF communications: the ZBD story,” Liq. Cryst. 44(12–13), 2133–2160 (2017).
60. J. Cliff Jones, “The zenithal bistable display: from concept to consumer,” J. Soc. Inf. Disp. 16(1), 143–154 (2016).
61. J. Chen, W. Cranton, and M. Fihn, Handbook of Visual Display Technology, Springer Publishing Company, Inc. (2011).
62. J. C. Jones et al., “26.3: low voltage zenithal bistable devices with wide operating windows,” in SID Symp. Digest
    of Tech. Pap., Wiley Online Library, Vol. 34, pp. 954–957 (2003).
63. G. Friedel, “Les états mésomorphes de la matière,” Ann. Phys. 9(18), 273–474 (1922).
64. H. Kelker, “History of liquid crystals,” Mol. Cryst. Liq. Cryst. 21, 1–48 (1973).
65. M. Mitov, “Cholesteric liquid crystals in living matter,” Soft Matter 13(23), 4176–4209 (2017).
66. M. Mitov, “Cholesteric liquid crystals with a broad light reflection band,” Adv. Mater. 24, 6260–6276 (2012).
67. D.-K. Yang, X.-Y. Huang, and Y.-M. Zhu, “Bistable cholesteric reflective displays: materials and drive schemes,”
    Annu. Rev. Mater. Sci. 27, 117–146 (1997).
68. AUO Corporation, “Eye care technologies at AUO,” https://www.auo.com/en-global/technologies/index/ Display/Eye\_Care
    (accessed 2 April 2023).
69. T. Schneider et al., “UV cured flexible cholesteric liquid crystal displays,” in Radtech UV&amp;EB Curing Technol.,
    Tech. Conf. Proc., May, pp. 4–7 (2008).
70. P.-G. De Gennes and J. Prost, The Physics of Liquid Crystals, Vol. 83, Oxford University Press (1993).
71. A. Khan et al., “27.4: super high brightness reflective cholesteric display,” in SID Symp. Digest of Tech. Pap.,
    Vol. 32, p. 460 (2001).
72. D. Coates, “Cholesteric reflective displays,” in Handbook of Visual Display Technology, pp. 2199–2222, Springer
    International Publishing (2016).
73. A. A. F. Froyen et al., “Electrothermal color tuning of cholesteric liquid crystals using interdigitated electrode
    patterns,” Adv. Electron. Mater. 7(2), 2000958 (2020).
74. Y. Huang et al., “Tuning the photonic band gap in cholesteric liquid crystals by temperature-dependent dopant
    solubility,” Opt. Express 14(3), 1236 (2006).
75. M. Schadt, “Liquid crystal materials and liquid crystal displays,” Annu. Rev. Mater. Sci. 27, 305–379 (1997).

<!-- PDF page 31; printed page 020901-31 -->

76. T. Uchida and T. Ishinabe, “Reflective liquid-crystal displays,” MRS Bull. 27, 876–879 (2002).
77. VGA Cholesteric Display Modules and Controller Assemblies, Kent Display Incorporated, https://cdn
    .thomasnet.com/ccp/10069038/106600.pdf.
78. Y. Takashima and B. Hellman, “Review paper: imaging LiDAR by digital micromirror device,” Opt. Rev. 27, 400–408
    (2020).
79. T. Brosnihan et al., “Pixtronix digital micro-shutter display technology: a mems display for low power mobile
    multimedia displays,” Proc. SPIE 7594, 759408 (2010).
80. M. W. Miles, “A new reflective FPD technology using interferometric modulation,” J. Soc. Inf. Disp. 5(4), 379
    (1997).
81. M. W. Miles, “MEMS devices with stiction bumps,” US Patent 7,554,711 (2009).
82. M. W. Miles, “5.3: Digital paperTM: reflective displays using interferometric modulation,” in SID Symp. Digest of
    Tech. Pap., Vol. 31, pp. 32–35 (2000).
83. M. Kothari, “Method and device for compensating for color shift as a function of angle of view,” US Patent 7,630,123
    (2009).
84. M. W. Miles, “MEMS-based interferometric modulator for display applications,” Proc. SPIE 3876, 20–28 (1999).
85. E. K. Chan et al., “Continuous color reflective display fabricated in integrated MEMS-and-TFT-on-glass process,” J.
    Microelectromech. Syst. 26, 143–157 (2017).
86. J. Hong et al., “Continuous color reflective displays using interferometric absorption,” Optica 2, 589 (2015).
87. S. J. Cartamil-Bueno et al., “Graphene mechanical pixels for interferometric modulator displays,” Nat. Commun. 9,
    4837 (2018).
88. B. Gally et al., “5.1: invited paper: a 5.7 color mirasol XGA display for high performance applications,” in SID
    Symp. Digest of Tech. Pap., Vol. 42, pp. 36–39 (2011).
89. F. Jutzi et al., “Low voltage electrostatic 90° turning flap for reflective MEMS display,” in Int. Conf. Opt. MEMS
    and Nanophotonics, IEEE (2010).
90. F. Jutzi, W. Noell, and N. F. de Rooij, “Vertical electrostatically 90° turning flaps for reflective MEMS display,”
    Proc. SPIE 7930, 79300H (2011).
91. D. Herle et al., “Broadband mechanically tunable metasurface reflectivity modulator in the visible spectrum,” ACS
    Photonics 10(6), 1882–1889 (2023).
92. S. K. Cho, H. Moon, and C.-J. Kim, “Creating, transporting, cutting, and merging liquid droplets by
    electrowetting-based actuation for digital microfluidic circuits,” J. Microelectromech. Syst. 12, 70–80 (2003).
93. J. Li et al., “Current commercialization status of electrowetting-on-dielectric (EWOD) digital microfluidics,” Lab
    Chip 20(10), 1705–1712 (2020).
94. B. J. Feenstra, R. A. Hayes, and M. W. J. Prins, “Display device,” US Patent 7,898,718 (2011).
95. R. A. Hayes and B. J. Feenstra, “Video-speed electronic paper based on electrowetting,” Nature 425, 383–385 (2003).
96. F. Mugele and J.-C. Baret, “Electrowetting: from basics to applications,” J. Phys. Condens. Matter 17, R705–R774
    (2005).
97. IEEE Spectrum, “The electrowetting display,” (2013). https://www.youtube.com/watch?v=Bf1GjCaYzYg (accessed 25
    September 2023).
98. M. Zhou et al., “Simplified dynamical model for optical response of electrofluidic displays,” Displays 49, 26–34
    (2017).
99. E. M. Barston, “Comments on ‘electrohydrodynamic Rayleigh-Taylor bulk instability’,” Phys. Fluids 13, 2876–2878
    (1970).
100. L. Wang et al., “Driving scheme optimization for electrowetting displays based on contact angle hysteresis to
     achieve precise gray-scales,” Front. Phys. 9, 655547 (2021).
101. F. Li and F. Mugele, “How to make sticky surfaces slippery: contact angle hysteresis in electrowetting with
     alternating voltage,” Appl. Phys. Lett. 92, 244108 (2008).
102. Y.-C. Chen et al., “56.3: a charge trapping suppression method for quick response electrowetting displays,” in SID
     Symp. Digest of Tech. Pap., Vol. 41, p. 842 (2010).
103. J. R. Platt, “Electrochromism, a possible change of color producible in dyes by an electric field,” J. Chem. Phys.
     34, 862–863 (1961).
104. S. K. Deb, “A novel electrophotographic system,” Appl. Opt. 8, 192 (1969).
105. J. Svensson and C. Granqvist, “Electrochromic tungsten oxide films for energy efficient windows,” Sol. Energy
     Mater. 11, 29–34 (1984).
106. C. M. Lampert, “Electrochromic materials and devices for energy efficient windows,” Sol. Energy Mater. 11, 1–27
     (1984).
107. C. M. Lampert, “The world of large-area glazing and displays,” Proc SPIE 3788 (1999).
108. C. Lampert, “Large-area smart glass and integrated photovoltaics,” Sol. Energy Mater. Sol. Cells 76, 489–499
     (2003).

<!-- PDF page 32; printed page 020901-32 -->

109. A. M. Österholm et al., “Four shades of brown: tuning of electrochromic polymer blends toward highcontrast
     eyewear,” ACS Appl. Mater. Interfaces 7, 1413–1421 (2015).
110. Y. Wang et al., “Pulsed electrochemical deposition of porous WO3/sub on silver networks for highly flexible
     electrochromic devices,” J. Mater. Chem. C 7(7), 1966–1973 (2019).
111. H. Yu et al., “Side-chain engineering of green color electrochromic polymer materials: toward adaptive camouflage
     application,” J. Mater. Chem. C 4(12), 2269–2273 (2016).
112. N. O. Laschuk et al., “Post-synthetic color tuning of the ultra-effective and highly stable surface-confined
     electrochromic monolayer: shades of green for camouflage materials,” ACS Appl. Mater. Interfaces 13(33),
     39573–39583 (2021).
113. C. R. Wade, M. Li, and M. Dincă, “Facile deposition of multicolored electrochromic metal-organic framework thin
     films,” Angew. Chem. Int. Ed. 52, 13377–13381 (2013).
114. Y.-M. Zhang et al., “A single-molecule multicolor electrochromic device generated through medium engineering,”
     Light Sci. Appl. 4, e249–e249 (2015).
115. L. Niklaus et al., “Redox electrolytes for hybrid type II electrochromic devices with fe-MEPE or nisub1-ix/i/ subo
     as electrode materials,” ChemElectroChem 7, 3274–3283 (2020).
116. S. Bogati, A. Georg, and W. Graf, “Sputtered Si3N4 and SiO2 electron barrier layer between a redox electrolyte and
     the WO3 film in electrochromic devices,” Sol. Energy Mater. Sol. Cells 159, 395–404 (2017).
117. S. Bogati, R. Basnet, and A. Georg, “Iridium oxide catalyst for hybrid electrochromic device based on
     tetramethylthiourea (TMTU) redox electrolyte,” Sol. Energy Mater. Sol. Cells 189, 206–213 (2019).
118. Y. Wang et al., “A multicolour bistable electronic shelf label based on intramolecular proton-coupled electron
     transfer,” Nat. Mater. 18, 1335–1342 (2019).
119. X. Wang et al., “Reversible bond/cation-coupled electron transfer on phenylenediamine-based rhodamine b and its
     application on electrochromism,” ACS Appl. Mater. Interfaces 9(23), 20196–20204 (2017).
120. H. Shin et al., “Energy saving electrochromic windows from bistable low-HOMO level conjugated polymers,” Energy
     Environ. Sci. 9(1), 117–122 (2016).
121. T. S. Hernandez et al., “Bistable black electrochromic windows based on the reversible metal electrodeposition of
     Bi and Cu,” ACS Energy Lett. 3(1), 104–111 (2017).
122. S. Zhang et al., “AlSuP3∕sup intercalation/de-intercalation-enabled dual-band electrochromic smart windows with a
     high optical modulation, quick response and long cycle life,” Energy Environ. Sci. 11(10), 2884–2892 (2018).
123. Z. Sun and Y. Fang, “Fabry-Pérot interference cavity length tuned by plasmonic nanoparticle metasurface for
     nanophotonic device design,” ACS Appl. Nano Mater. 3, 10732–10738 (2020).
124. M. Gugole et al., “Electrochromic inorganic nanostructures with high chromaticity and superior brightness,” Nano
     Lett. 21(10), 4343–4350 (2021).
125. T. Xu et al., “High-contrast and fast electrochromic switching enabled by plasmonics,” Nat. Commun. 7(1), 10479
     (2016).
126. B.-H. Chen et al., “Printed multicolor high-contrast electrochromic devices,” ACS Appl. Mater. Interfaces 7,
     25069–25076 (2015).
127. K. Xiong et al., “Electronic paper: plasmonic metasurfaces with conjugated polymers for flexible electronic paper
     in color (adv. mater. 45/2016),” Adv. Mater. 28, 10103–10103 (2016).
128. N. Kobayashi et al., “Organic electrochromism for a new color electronic paper,” Sol. Energy Mater. Sol. Cells 92,
     136–139 (2008).
129. T. Yashiro et al., “Flexible electrochromic display,” in Proc. IDW, Vol. 13, pp. 1300–1303 (2013).
130. S. I. Cho et al., “Nanotube-based ultrafast electrochromic display,” Adv. Mater. 17(2), 171–175 (2005).
131. M. Wuttig, “Towards a universal memory?” Nat. Mater. 4, 265–266 (2005).
132. H. Bhaskaran and P. Hosseini, “Display device based on phase-change materials,” US Patent 9,823,538 (2017).
133. C. Koch et al., “Investigating the influence of resonant bonding on the optical properties of phase change
     materials (GeTe)subix/i/subSnSbsub2/subsesub4/sub,” Chem. Mater. 29, 9320–9327 (2017).
134. S. R. Ovshinsky, “Reversible electrical switching phenomena in disordered structures,” in Disordered Materials, pp.
     11–13, Springer US (1991).
135. E. Ohno et al., “TeGeSnAu alloys for phase change type optical disk memories,” Jpn. J. Appl. Phys. 28, 1235 (1989).
136. P. Hosseini, C. D. Wright, and H. Bhaskaran, “An optoelectronic framework enabled by low-dimensional phase-change
     films,” Nature 511, 206–211 (2014).
137. M. A. Kats et al., “Nanometre optical coatings based on strong interference effects in highly absorbing media,”
     Nat. Mater. 12(1), 20–24 (2013).
138. K. Shportko et al., “Resonant bonding in crystalline phase-change materials,” Nat. Mater. 7, 653–658 (2008).
139. B. Broughton et al., “38-4: solid-state reflective displays (SRD) utilizing ultrathin phase-change materials,” in
     SID Symp. Digest of Tech. Pap., Wiley Online Library, Vol. 48, pp. 546–549 (2017).

<!-- PDF page 33; printed page 020901-33 -->

140. S. G. Castillo et al., “57-4: solid state reflective display (SRD) with LTPS diode backplane,” in SID Symp. Digest
     of Tech. Pap., Wiley Online Library, Vol. 50, pp. 807–810 (2019).
141. O. Hemmatyar et al., “Advanced phase-change materials for enhanced meta-displays,” arXiv:2105.01313 (2021).
142. T. Zhou et al., “Electrically tunable non-volatile reflective display pixel structure based on phase change
     material,” J. Phys. Conf. Ser. 1544, 012034 (2020).
143. E. Yablonovitch, “Inhibited spontaneous emission in solid-state physics and electronics,” Phys. Rev. Lett. 58(20),
     2059 (1987).
144. S. John, “Strong localization of photons in certain disordered dielectric superlattices,” Phys. Rev. Lett. 58(23),
     2486 (1987).
145. Z. A. Zaky and A. H. Aly, “Novel smart window using photonic crystal for energy saving,” Sci. Rep. 12, 10104
     (2022).
146. H. Wang and K.-Q. Zhang, “Photonic crystal structures with tunable structure color as colorimetric sensors,”
     Sensors 13(4), 4192–4213 (2013).
147. G. A. Ozin and A. C. Arsenault, “P-ink and elast-ink from lab to market,” Mater. Today 11(7-8), 44–51 (2008).
148. I. Lee et al., “Quasi-amorphous colloidal structures for electrically tunable full-color photonic pixels with
     angle-independency,” Adv. Mater. 22(44), 4973–4977 (2010).
149. C. Jin et al., “Photonic gap in amorphous photonic materials,” Phys. Rev. B 63(19), 195107 (2001).
150. K. Ueno et al., “A soft glassy colloidal array in ionic liquid, which exhibits homogeneous, non-brilliant and
     angle-independent structural colours,” Chem. Commun. (24), 3603–3605 (2009).
151. Y. Fang et al., “In situ dynamic study of color-changing in liquid colloidal crystals for electrophoretic
     displays,” ACS Appl. Nano Mater. 5(8), 11249–11261 (2022).
152. G. Chen et al., “Development of bright and low angle dependence structural colors from order-disorder hierarchical
     photonic structure,” Dyes Pigments 161, 464–469 (2019).
153. N. Vogel et al., “Color from hierarchy: diverse optical properties of micron-sized spherical colloidal assemblies,”
     Proc. Natl. Acad. Sci. 112(35), 10845–10850 (2015).
154. K. Werner, “La chapter’s one-day conference covers North American display activity,” Inf. Disp. 35(4), 34–36
     (2019).
155. M. Wang et al., “59.1: invited paper: electrophoretic display platform comprising b, w, r particles,” in SID Symp.
     Digest of Tech. Pap., Wiley Online Library, Vol. 45, pp. 857–860 (2014).
156. W. Markvoort, H. E. A. Huitema, and L. M. Hage, “Sequential addressing of displays,” US Patent 8,866,733 (2014).
157. [E ink epaper ED103TC2, https://www.data-modul.com/sites/default/files/products/VB3300-KCDspecification-12051789.pdf (accessed 2 April 2024).](https://www.data-modul.com/sites/default/files/products/VB3300-KCD-specification-12051789.pdf)
158. R. Fleming et al., “48-2: electronic paper 2.0: frustrated eTIR as a path to color and video,” in SID Symp. Digest
     of Tech. Pap., Wiley Online Library, Vol. 49, pp. 630–632 (2018).
159. A. Khan et al., “Recent advances and product enhancements in reflective cholesteric displays,” Proc. SPIE 5741, 1–6
     (2005).
160. D. Corr et al., “Coloured electrochromic “paper-quality” displays based on modified mesoporous electrodes,” Solid
     State Ionics 165(1–4), 315–321 (2003).
161. I. J. Ko et al., “An optically efficient full-color reflective display with an electrochromic device and color
     production units,” J. Inf. Disp. 20, 155–160 (2019).
162. M. Z. Duan et al., “A reflective display technology based on electrofluidics,” Appl. Mech. Mater. 670, 976–981
     (2014).
163. S. Wilson and M. Hutley, “The optical properties of ‘moth eye’ antireflection surfaces,” Optica Acta: Int. J. Opt.
     29(7), 993–1009 (1982).
164. T. Yano, H. Sugawara, and J. Taniguchi, “Moth-eye structured mold using sputtered glassy carbon layer for
     large-scale applications,” Micro Nano Eng. 9, 100077 (2020).
165. H. K. Raut et al., “Anti-reflective coatings: a critical, in-depth review,” Energy Environ. Sci. 4(10), 3779– 3804
     (2011).
166. “The new re monitor by SVD: Our 32" RLCD with more connectivity,” Sun Vision Display, a TM Brand of New Vision
     Display, https://www.sunvisiondisplay.com/product/The-NEW-rE-Monitor-Featuring-32- Color-RLCD-Technology (accessed
     2 April 2024).
167. G. Hong et al., “A brief history of OLEDs—emitter development and industry milestones,” Adv. Mater. 33(9), 2005630
     (2021).
168. H. Alex et al., “Introduction of a new disruptive display technology in the existing display manufacturing
     infrastructure,” in Proc. Int. Disp. Workshops, p. 739 (2020).
169. J. Heikenfeld et al., “Electrofluidic displays using young–Laplace transposition of brilliant pigment dispersions,”
     Nat. Photonics 3(5), 292–296 (2009).
170. M. Jin et al., “Optofluid-based reflective displays,” Micromachines 9(4), 159 (2018).

<!-- PDF page 34; printed page 020901-34 -->

171. C. Gu et al., “Emerging electrochromic materials and devices for future displays,” Chem. Rev. 122(18), 14679–14721
     (2022).
172. Q. Fu et al., “Electrically responsive photonic crystals with bistable states for low-power electrophoretic color
     displays,” Nat. Commun. 13(1), 7007 (2022).
173. L. Whitehead, “Total internal reflection for illumination and displays,” SPIE Newsroom, https://spie.org/
     news/0461-total-internal-reflection-for-illumination-and-displays (2006).

Dorian Herle is a PhD student at École Polytechnique Fédérale de Lausanne (EPFL), Switzerland. He received his MSc
degree in mechanical engineering from EPFL in 2019. His current research focuses on MEMS-based tunable metasurfaces.

Olivier J. F. Martin conducts comprehensive research that combines the development of numerical techniques, advanced
nanofabrication, and experiments on plasmonic systems. Applications of his research include optical antennas,
metasurfaces, nonlinear optics, optical nano-manipulations, heterogeneous catalysis, security features, and optical
forces at the nanoscale. He has authored over 300 journal articles and holds several patents and invention disclosures.

Luis Guillermo Villanueva is an associate professor at École Polytechnique Fédérale de Lausanne, Switzerland, where he
specializes in NEMS/MEMS sensing technologies. He received his MSc degree in physics from Zaragoza and his PhD from UAB
in Barcelona. He has contributed over 100 papers to peer-reviewed journals. He has served on program committees for
major conferences including IEEE-NEMS and IEEE-Sensors and is the editor-inchief of the Physical Sensors Section of MDPI
Sensors.

Niels Quack is an associate professor at the University of Sydney, Australia. He received his MSc degree from Ecole
Polytechnique Fédérale de Lausanne (EPFL), Switzerland, in 2005, and his Dr.Sc. degree from ETH Zürich, Switzerland,
in 2010. He was a postdoctoral researcher at UC Berkeley, United States, from 2011 to 2015 and assistant professor at
EPFL from 2015 to 2021. His research focuses on photonic micro- and nanosystems. He is senior member of IEEE and of
Optica and a life member of SPIE.
