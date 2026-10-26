import { Component, Suspense, type ReactNode } from "react";

/**
 * Wrapper for every WebGL scene. The scenes are lazy-loaded (three.js is a large chunk) and are
 * never the only place a number lives: each one has a 2D chart, list or table with the same values.
 * No WebGL / a crash → `fallback`, the page keeps working.
 */

function webglAvailable(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return !!(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

class Boundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

export function Scene3D({ height, fallback, children }: { height: number; fallback: ReactNode; children: ReactNode }) {
  const ok = webglAvailable();
  return (
    <div className="scene3d" style={{ height }}>
      {ok ? (
        <Boundary fallback={fallback}>
          <Suspense fallback={<div className="scene3d-loading"><span className="spinner" /> กำลังโหลดภาพ 3 มิติ…</div>}>
            {children}
          </Suspense>
        </Boundary>
      ) : fallback}
    </div>
  );
}
