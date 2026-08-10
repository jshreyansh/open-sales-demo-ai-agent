import type { ComponentType } from "react";
import { useParams } from "react-router-dom";
import DocsLayout from "./DocsLayout";
import TableOfContents from "../../components/docs/TableOfContents";
import { docsMdxComponents } from "../../components/docs/mdxComponents";

interface DocsModule {
  default: ComponentType<{ components?: typeof docsMdxComponents }>;
  frontmatter: { title: string; description?: string };
}

// Eagerly bundled at build time — this is a small, finite content set (see
// frontend/src/content/docs/), not something that benefits from per-page
// lazy chunks.
const modules = import.meta.glob("../../content/docs/**/*.mdx", { eager: true }) as Record<string, DocsModule>;

function slugFromPath(path: string): string {
  const stripped = path.replace("../../content/docs/", "").replace(/\.mdx$/, "");
  return stripped === "index" ? "" : stripped;
}

const pagesBySlug = new Map(Object.entries(modules).map(([path, mod]) => [slugFromPath(path), mod]));

const CONTENT_ID = "docs-page-content";

// Matched against App.tsx's "/docs/api" and "/docs/api/*" routes — the
// wildcard segment is the content slug (empty string for "/docs/api"
// itself, which resolves to content/docs/index.mdx).
export default function DocsRoute() {
  const params = useParams();
  const slug = params["*"] ?? "";
  const page = pagesBySlug.get(slug);

  if (!page) {
    return (
      <DocsLayout activeSlug={slug}>
        <h1 className="docs-page-title">Page not found</h1>
        <p>That documentation page doesn't exist.</p>
      </DocsLayout>
    );
  }

  const Page = page.default;
  return (
    <DocsLayout activeSlug={slug} toc={<TableOfContents key={slug} containerId={CONTENT_ID} />}>
      <h1 className="docs-page-title">{page.frontmatter.title}</h1>
      {page.frontmatter.description && <p className="docs-page-description">{page.frontmatter.description}</p>}
      <div className="docs-content-body" id={CONTENT_ID}>
        <Page components={docsMdxComponents} />
      </div>
    </DocsLayout>
  );
}
