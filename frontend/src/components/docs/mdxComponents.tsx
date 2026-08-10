import type { ComponentPropsWithoutRef } from "react";
import { Link } from "react-router-dom";
import Callout from "./Callout";
import { Cards, Card } from "./Cards";
import { Tabs, Tab } from "./Tabs";
import { Steps, Step } from "./Steps";

// GFM tables (guides/error-handling.mdx's decision table, etc.) can run
// wider than the viewport, especially on mobile — this keeps that scroll
// contained to the table itself instead of the whole page scrolling
// sideways.
function DocsTable(props: ComponentPropsWithoutRef<"table">) {
  return (
    <div className="docs-table-wrap">
      <table {...props} />
    </div>
  );
}

// Ported content links internally with plain markdown ([text](/docs/...)),
// which compiles to a plain <a>. Overriding the default `a` element is what
// turns those into real client-side navigations instead of full page
// reloads — anything not starting with "/" (external URLs, mailto:) stays a
// normal anchor.
function DocsLink({ href = "", children, ...rest }: ComponentPropsWithoutRef<"a">) {
  if (href.startsWith("/")) {
    return (
      <Link to={href} {...rest}>
        {children}
      </Link>
    );
  }
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" {...rest}>
      {children}
    </a>
  );
}

// Passed as the `components` prop to every compiled MDX page (see
// DocsRoute.tsx) — the same override-map role swishx-docs' own
// getMDXComponents() played, just backed by our own components instead of
// @fumadocs/base-ui's. Default prose elements (h1-h4, p, table, code, ...)
// are deliberately left as native tags, styled by the shared .docs-content
// CSS block rather than component overrides.
export const docsMdxComponents = {
  a: DocsLink,
  table: DocsTable,
  Callout,
  Cards,
  Card,
  Tabs,
  Tab,
  Steps,
  Step,
};
