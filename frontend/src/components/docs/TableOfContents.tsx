import { useEffect, useState } from "react";

interface TocItem {
  id: string;
  text: string;
  level: number;
}

// Scans the actual rendered heading elements for the current page (ids come
// from rehype-slug, see vite.config.ts) rather than parsing anything at
// build time — the content set is small and static, so a runtime DOM scan
// on mount is simpler than a separate build-time TOC extraction pass.
// Mounted with key={slug} by DocsRoute so it gets one fresh scan per page
// instead of trying to diff between pages itself.
//
// Active section = the last heading whose top has scrolled above a fixed
// threshold, not "currently intersecting a band" (an earlier
// IntersectionObserver version left nothing highlighted once you scrolled
// past the last heading on a page — this plain scroll-position check keeps
// the last heading active all the way to the bottom, which is what you'd
// actually expect from a TOC).
export default function TableOfContents({ containerId }: { containerId: string }) {
  const [items, setItems] = useState<TocItem[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);

  useEffect(() => {
    const container = document.getElementById(containerId);
    if (!container) return;
    const headings = Array.from(container.querySelectorAll("h2[id], h3[id]")) as HTMLElement[];
    setItems(headings.map((h) => ({ id: h.id, text: h.textContent || "", level: h.tagName === "H3" ? 3 : 2 })));
    if (headings.length === 0) return;

    const THRESHOLD_PX = 120;

    function updateActive() {
      let current = headings[0].id;
      for (const h of headings) {
        if (h.getBoundingClientRect().top <= THRESHOLD_PX) {
          current = h.id;
        } else {
          break;
        }
      }
      setActiveId(current);
    }

    updateActive();
    window.addEventListener("scroll", updateActive, { passive: true });
    return () => window.removeEventListener("scroll", updateActive);
  }, [containerId]);

  if (items.length === 0) return null;

  return (
    <nav className="docs-toc">
      <div className="docs-toc__title">On this page</div>
      {items.map((item) => (
        <a
          key={item.id}
          href={`#${item.id}`}
          className={`docs-toc__link docs-toc__link--h${item.level} ${activeId === item.id ? "docs-toc__link--active" : ""}`}
        >
          {item.text}
        </a>
      ))}
    </nav>
  );
}
