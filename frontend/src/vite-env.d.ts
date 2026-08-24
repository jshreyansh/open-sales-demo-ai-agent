/// <reference types="vite/client" />

// Ported docs content (frontend/src/content/docs/**/*.mdx) is compiled by
// @mdx-js/rollup (see vite.config.ts) — each file's default export is a
// component, plus a named `frontmatter` export from remark-mdx-frontmatter.
declare module "*.mdx" {
  import type { MDXProps } from "mdx/types";
  export const frontmatter: { title: string; description?: string };
  export default function MDXContent(props: MDXProps): JSX.Element;
}

// The SwishX guided widget (public/swishx-widget.js) is a vanilla custom
// element loaded via a plain <script> tag (see index.html) — no npm
// package, no React types of its own, so JSX needs telling it's a real
// intrinsic element rather than an unknown component.
declare namespace JSX {
  interface IntrinsicElements {
    "swishx-widget": React.DetailedHTMLProps<React.HTMLAttributes<HTMLElement>, HTMLElement> & {
      "max-width"?: string;
    };
  }
}
