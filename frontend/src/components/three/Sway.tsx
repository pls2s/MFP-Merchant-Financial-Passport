import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useRef, type ReactNode } from "react";

/**
 * Pull the camera back on narrow (portrait) canvases so a scene `width` units wide still fits.
 * `base` is the camera position used on wide screens.
 */
export function FitCamera({ base, width }: { base: [number, number, number]; width: number }) {
  const camera = useThree((s) => s.camera);
  const aspect = useThree((s) => s.size.width / s.size.height);
  useEffect(() => {
    const fov = ("fov" in camera ? (camera.fov as number) : 40) * (Math.PI / 180);
    const needed = (width / 2 + 0.6) / (Math.tan(fov / 2) * aspect); // distance to fit the width
    const scale = Math.max(1, needed / Math.hypot(base[1], base[2]));
    camera.position.set(base[0], base[1] * scale, base[2] * scale);
    camera.lookAt(0, 0, 0);
  }, [camera, aspect, base, width]);
  return null;
}
import type { Group } from "three";
import { prefersReducedMotion } from "../../theme";

/** Slow left-right sway so the scene reads as 3D without spinning away; paused while `paused`. */
export function Sway({ children, amount = 0.28, paused = false }: { children: ReactNode; amount?: number; paused?: boolean }) {
  const ref = useRef<Group>(null);
  const still = prefersReducedMotion();
  const t = useRef(0);
  useFrame((_, dt) => {
    if (!ref.current || still || paused) return;
    t.current += dt;
    ref.current.rotation.y = Math.sin(t.current * 0.25) * amount;
  });
  return <group ref={ref}>{children}</group>;
}
