import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import mdx from "@mdx-js/rollup";
import remarkFrontmatter from "remark-frontmatter";
import remarkMdxFrontmatter from "remark-mdx-frontmatter";
import remarkGfm from "remark-gfm";
import rehypeSlug from "rehype-slug";
import rehypePrettyCode from "rehype-pretty-code";

export default defineConfig({
  // mdx() must run before react() — it compiles .mdx files to JSX, which
  // react() then needs to transform like any other component file. Docs
  // content (frontend/src/content/docs/**) is plain frontmatter + MDX
  // ported from swishx-docs; remark-mdx-frontmatter exposes each page's
  // `title`/`description` as a `frontmatter` export instead of raw YAML
  // text, and rehype-pretty-code (Shiki under the hood, same highlighter
  // the original docs site used) does real syntax highlighting at build
  // time — no highlighting cost at runtime.
  plugins: [
    mdx({
      remarkPlugins: [remarkFrontmatter, remarkMdxFrontmatter, remarkGfm],
      rehypePlugins: [rehypeSlug, [rehypePrettyCode, { theme: "github-dark" }]],
    }),
    react(),
  ],
  server: { port: 5173 },
});
