// Type declaration so <model-viewer> (Google's web component, loaded from a CDN
// module script — not an npm dependency) type-checks as a JSX intrinsic element.
import type React from "react";

type ModelViewerAttributes = React.DetailedHTMLProps<
  React.HTMLAttributes<HTMLElement>,
  HTMLElement
> & {
  src?: string;
  alt?: string;
  "camera-controls"?: boolean | string;
  "auto-rotate"?: boolean | string;
  "shadow-intensity"?: string;
  "rotation-per-second"?: string;
  "interaction-prompt"?: string;
  exposure?: string;
  loading?: string;
};

// React 19 / Next 15 resolves intrinsic elements via the `React.JSX` namespace,
// while older toolchains use the global `JSX` namespace. Augment both so
// <model-viewer> type-checks regardless.
declare module "react" {
  namespace JSX {
    interface IntrinsicElements {
      "model-viewer": ModelViewerAttributes;
    }
  }
}

declare global {
  namespace JSX {
    interface IntrinsicElements {
      "model-viewer": ModelViewerAttributes;
    }
  }
}

export {};
