import { ContactShadows, Html, OrbitControls, RoundedBox } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { useState } from "react";
import { money, thaiDateShort } from "../../format";
import { useTokens } from "../../theme";
import { FitCamera, Sway } from "./Sway";

const CAMERA: [number, number, number] = [0, 2.6, 6.6];

/**
 * The next 14 days as a skyline: per day a forecast-sales tower (blue) beside the synthetic
 * expenses due that day (orange), both on one scale. Days where the cash may run short get a
 * red ring and a callout. Click a day to open its numbers in the panel beside the scene.
 */

export interface SkylineDay {
  date: string;
  sales: number;
  expenses: number;
  balance: number;
  gap: boolean;
}

const TOKENS = ["series-forecast", "series-expense", "bad", "accent", "surface-2", "text-2"] as const;
const MAX_H = 2.8;
const SPACING = 0.62;

function Day({ d, x, scale, selected, dimmed, onSelect, colors }: {
  d: SkylineDay; x: number; scale: number; selected: boolean; dimmed: boolean;
  onSelect: () => void; colors: Record<(typeof TOKENS)[number], string>;
}) {
  const [hover, setHover] = useState(false);
  const sH = Math.max(d.sales * scale, 0.02);
  const eH = d.expenses * scale;
  const op = dimmed && !hover ? 0.3 : 1;
  const lift = selected || hover ? 0.1 : 0;
  return (
    <group position={[x, lift, 0]}
      onPointerOver={(e) => { e.stopPropagation(); setHover(true); document.body.style.cursor = "pointer"; }}
      onPointerOut={() => { setHover(false); document.body.style.cursor = ""; }}
      onClick={(e) => { e.stopPropagation(); onSelect(); }}>
      <mesh position={[0, MAX_H / 2, 0]} visible={false}>
        <boxGeometry args={[SPACING, MAX_H + 0.5, 1.2]} />
      </mesh>
      <RoundedBox args={[0.24, sH, 0.24]} radius={Math.min(0.04, sH / 2.2)} position={[0, sH / 2, -0.17]}>
        <meshStandardMaterial color={colors["series-forecast"]} transparent opacity={op} roughness={0.5} metalness={0.1}
          emissive={colors["series-forecast"]} emissiveIntensity={selected ? 0.6 : 0.3} />
      </RoundedBox>
      {eH > 0.001 && (
        <RoundedBox args={[0.24, eH, 0.24]} radius={Math.min(0.04, eH / 2.2)} position={[0, eH / 2, 0.17]}>
          <meshStandardMaterial color={colors["series-expense"]} transparent opacity={op} roughness={0.6} metalness={0}
            emissive={colors["series-expense"]} emissiveIntensity={0.35} />
        </RoundedBox>
      )}
      {d.gap && (
        <>
          <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.01, 0]}>
            <ringGeometry args={[0.36, 0.44, 40]} />
            <meshBasicMaterial color={colors.bad} />
          </mesh>
          <Html position={[0, Math.max(sH, eH) + 0.32, 0]} center distanceFactor={6} zIndexRange={[20, 0]}>
            <span className="pill3d">⚠ {thaiDateShort(d.date)} เงินอาจไม่พอ</span>
          </Html>
        </>
      )}
      {(hover && !selected) && !d.gap && (
        <Html position={[0, Math.max(sH, eH) + 0.35, 0]} center distanceFactor={9} zIndexRange={[20, 0]}>
          <div className="tip3d">
            <strong>{thaiDateShort(d.date)}</strong>
            <div>ขาย <b className="num">{money(d.sales)}</b></div>
          </div>
        </Html>
      )}
      <Html position={[0, -0.02, 0.62]} center distanceFactor={10} zIndexRange={[10, 0]}>
        <span className={`axis3d${selected ? " on" : ""}`}>{Number(d.date.slice(8))}</span>
      </Html>
    </group>
  );
}

export default function CashSkyline3D({ days, selected, onSelect }: {
  days: SkylineDay[];
  selected: number | null;
  onSelect: (i: number | null) => void;
}) {
  const colors = useTokens(TOKENS);
  const max = Math.max(1, ...days.map((d) => Math.max(d.sales, d.expenses)));
  const scale = MAX_H / max;
  const offset = ((days.length - 1) * SPACING) / 2;
  return (
    <Canvas camera={{ position: CAMERA, fov: 42 }} dpr={[1, 2]} onPointerMissed={() => onSelect(null)}
      aria-label="ภาพ 3 มิติ: ยอดขายคาดการณ์และรายจ่ายจำลอง 14 วันข้างหน้า">
      <FitCamera base={CAMERA} width={days.length * SPACING} />
      <ambientLight intensity={0.6} />
      <directionalLight position={[3, 8, 6]} intensity={1.3} />
      <pointLight position={[-4, 3, 3]} intensity={10} color={colors.accent} />
      <Sway amount={0.22} paused={selected != null}>
        <group position={[0, -1.3, 0]}>
          <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.01, 0]}>
            <planeGeometry args={[days.length * SPACING + 1.2, 2.4]} />
            <meshStandardMaterial color={colors["surface-2"]} roughness={0.85} transparent opacity={0.9} />
          </mesh>
          {days.map((d, i) => (
            <Day key={d.date} d={d} x={i * SPACING - offset} scale={scale} colors={colors}
              selected={selected === i} dimmed={selected != null && selected !== i}
              onSelect={() => onSelect(selected === i ? null : i)} />
          ))}
          <ContactShadows position={[0, 0, 0]} opacity={0.3} scale={12} blur={2.2} far={3} />
        </group>
      </Sway>
      <OrbitControls enableZoom={false} enablePan={false} minPolarAngle={0.55} maxPolarAngle={1.4}
        minAzimuthAngle={-0.8} maxAzimuthAngle={0.8} />
    </Canvas>
  );
}
