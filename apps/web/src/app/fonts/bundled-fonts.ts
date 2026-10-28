// Bundled starter fonts: known OFL-licensed files reused from the canonical
// fonts/ directory (no duplicated binaries). Vite emits each as a
// content-hashed asset; seeding fetches these URLs once into the
// browser-local library.
import robotoUrl from "../../../../../fonts/Roboto.ttf?url";
import robotoItalicUrl from "../../../../../fonts/Roboto-Italic.ttf?url";
import robotoFlexUrl from "../../../../../fonts/RobotoFlex.ttf?url";
import literataUrl from "../../../../../fonts/Literata.ttf?url";
import sourceSansUrl from "../../../../../fonts/SourceSans3.ttf?url";
import robotoLicenseUrl from "../../../../../fonts/OFL-Roboto.txt?url";
import robotoFlexLicenseUrl from "../../../../../fonts/OFL-RobotoFlex.txt?url";
import literataLicenseUrl from "../../../../../fonts/OFL-Literata.txt?url";
import sourceSansLicenseUrl from "../../../../../fonts/OFL-SourceSans3.txt?url";

export interface BundledFontDescriptor {
  url: string;
  name: string;
  fileName: string;
  licenseUrl: string;
  licenseName: string;
}

// Same-origin relative URL for a (possibly absolute) bundled asset URL, so
// descriptor fetches stay relative beneath any hosting prefix.
export function relativeFontUrl(url: string): string {
  try {
    const absolute = new URL(url, document.baseURI).href;
    const base = new URL(".", document.baseURI).href;
    if (absolute.startsWith(base)) return absolute.slice(base.length);
  } catch { /* keep the original URL */ }
  return url;
}

export const BUNDLED_FONTS: BundledFontDescriptor[] = [
  {
    url: robotoUrl,
    name: "Roboto",
    fileName: "Roboto.ttf",
    licenseUrl: robotoLicenseUrl,
    licenseName: "OFL-Roboto.txt",
  },
  {
    url: robotoItalicUrl,
    name: "Roboto Italic",
    fileName: "Roboto-Italic.ttf",
    licenseUrl: robotoLicenseUrl,
    licenseName: "OFL-Roboto.txt",
  },
  {
    url: robotoFlexUrl,
    name: "Roboto Flex",
    fileName: "RobotoFlex.ttf",
    licenseUrl: robotoFlexLicenseUrl,
    licenseName: "OFL-RobotoFlex.txt",
  },
  {
    url: literataUrl,
    name: "Literata",
    fileName: "Literata.ttf",
    licenseUrl: literataLicenseUrl,
    licenseName: "OFL-Literata.txt",
  },
  {
    url: sourceSansUrl,
    name: "Source Sans 3",
    fileName: "SourceSans3.ttf",
    licenseUrl: sourceSansLicenseUrl,
    licenseName: "OFL-SourceSans3.txt",
  },
];

export function bundledLicense(fileName: string): { url: string; name: string } | null {
  const descriptor = BUNDLED_FONTS.find((entry) => entry.fileName === fileName);
  return descriptor ? { url: descriptor.licenseUrl, name: descriptor.licenseName } : null;
}
