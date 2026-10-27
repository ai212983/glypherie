import type * as React from "react";
import { PUBLIC_PAGES } from "./page-metadata";

interface PageMetadataProps {
  title: string;
  description: string;
  path?: string;
}

export function PageMetadata({ title, description, path }: PageMetadataProps): React.JSX.Element {
  const url = path !== undefined && __APP_SITE_URL__ ? new URL(path, __APP_SITE_URL__).href : undefined;
  return (
    <>
      <title>{title}</title>
      <meta name="description" content={description} />
      <meta name="robots" content={path === undefined ? "noindex,follow" : "index,follow"} />
      <meta property="og:title" content={title} />
      <meta property="og:description" content={description} />
      {url && <link rel="canonical" href={url} />}
      {url && <meta property="og:url" content={url} />}
    </>
  );
}

export function PublicPageMetadata({ page }: { page: keyof typeof PUBLIC_PAGES }): React.JSX.Element {
  return <PageMetadata {...PUBLIC_PAGES[page]} />;
}
