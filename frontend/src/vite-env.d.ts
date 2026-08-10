/// <reference types="vite/client" />

// Ported docs content (frontend/src/content/docs/**/*.mdx) is compiled by
// @mdx-js/rollup (see vite.config.ts) — each file's default export is a
// component, plus a named `frontmatter` export from remark-mdx-frontmatter.
declare module "*.mdx" {
  import type { MDXProps } from "mdx/types";
  export const frontmatter: { title: string; description?: string };
  export default function MDXContent(props: MDXProps): JSX.Element;
}
