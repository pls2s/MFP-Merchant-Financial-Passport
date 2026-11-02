import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useRef } from "react";
import { Vector3, type Group } from "three";

const world = new Vector3();

/**
 * Text pinned to a point of the scene. A plain DOM node moved every frame, not drei's <Html>: that
 * mounts a nested React root per label, and removing the scene threw an uncaught `removeChild` error.
 * `text` may contain line breaks; the first line of `.tip3d` is the heading.
 */
export function Label({ position, text, className }: { position: [number, number, number]; text: string; className: string }) {
  const parent = useThree((s) => s.gl.domElement.parentElement);
  const anchor = useRef<Group>(null);
  const node = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!parent) return;
    const div = document.createElement("div");
    div.style.cssText = "position:absolute;left:0;top:0;pointer-events:none;visibility:hidden";
    parent.appendChild(div);
    node.current = div;
    return () => { div.remove(); node.current = null; };
  }, [parent]);

  useEffect(() => {
    if (!node.current) return;
    node.current.textContent = text;
    node.current.className = className;
  }, [text, className, parent]);

  useFrame(({ camera, size }) => {
    if (!anchor.current || !node.current) return;
    world.setFromMatrixPosition(anchor.current.matrixWorld).project(camera);
    const x = ((world.x + 1) / 2) * size.width;
    const y = ((1 - world.y) / 2) * size.height;
    node.current.style.transform = `translate(${x}px, ${y}px) translate(-50%, -50%)`;
    node.current.style.visibility = "visible";
  });

  return <group ref={anchor} position={position} />;
}
