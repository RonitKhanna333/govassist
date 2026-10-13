"use client";

import {
  API_TARGET_KIND,
  API_TARGET_ORIGIN,
  type ApiTargetKind,
} from "@/lib/api";

const PRODUCTION_WEB_HOSTS = new Set([
  "govassist-web-ronit-khannas-projects.vercel.app",
  "govassist-web-git-main-ronit-khannas-projects.vercel.app",
]);
const PREVIEW_WEB_HOST = /^govassist-web-git-[a-z0-9-]+-ronit-khannas-projects\.vercel\.app$/i;

function isPreviewFrontend(): boolean {
  if (typeof window === "undefined") return false;
  const host = window.location.hostname;
  return PREVIEW_WEB_HOST.test(host) && !PRODUCTION_WEB_HOSTS.has(host);
}

function copy(kind: ApiTargetKind, preview: boolean): { title: string; detail: string; warning: boolean } {
  if (preview && kind === "production") {
    return {
      title: "Preview is calling the production API",
      detail: "Set NEXT_PUBLIC_API_BASE to the matching PR API preview before using this preview as backend evidence.",
      warning: true,
    };
  }
  if (preview && kind === "local") {
    return {
      title: "Preview has no remote API target",
      detail: "It is using the safe local default. Configure NEXT_PUBLIC_API_BASE in Vercel Preview settings.",
      warning: true,
    };
  }
  if (preview && kind === "preview") {
    return {
      title: "Preview API target configured",
      detail: "Confirm that this API preview belongs to the same PR before recording demo evidence.",
      warning: false,
    };
  }
  if (kind === "local") {
    return { title: "Local API target", detail: "This surface is using the local FastAPI process.", warning: false };
  }
  if (kind === "production") {
    return { title: "Production API target", detail: "This surface is using the existing production API.", warning: false };
  }
  if (kind === "invalid") {
    return { title: "Invalid API target", detail: "NEXT_PUBLIC_API_BASE is not a valid URL.", warning: true };
  }
  return { title: "Custom API target", detail: "Verify this target before treating the result as deployment evidence.", warning: false };
}

export function BackendTargetNotice() {
  const message = copy(API_TARGET_KIND, isPreviewFrontend());
  return (
    <aside className={`backend-target-notice${message.warning ? " warning" : ""}`} role={message.warning ? "alert" : "status"}>
      <div>
        <span className="backend-target-label">Backend target</span>
        <strong>{message.title}</strong>
      </div>
      <code>{API_TARGET_ORIGIN}</code>
      <p>{message.detail}</p>
    </aside>
  );
}
