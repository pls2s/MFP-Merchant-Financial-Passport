import { ContactShadows, Html, OrbitControls, RoundedBox } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { useState } from "react";
import { useTokens } from "../../theme";
import { FitCamera, Sway } from "./Sway";

const CAMERA: [number, number, number] = [0.4, 3.2, 9.4];

/**
 * Home hero: how the experimental financial signal is spread over all stores, as a 3D histogram.
 * Each bin stacks stores at risk of a cash shortfall (red, bottom) under the rest (blue).
 * Clicking a bin filters the store list — the same filter exists as chips under the scene.
 */

export interface ScoreBin {
  from: number;
  to: number;
  total: number;
  atRisk: number;
}

const TOKENS = ["series-forecast", "bad", "accent", "accent-2", "surface-2", "text"] as const;
const MAX_H = 3.2;
const GAP = 0.04; // surface gap between stacked segments

function Bin({ bin, x, scale, selected, dimmed, onSelect, colors }: {
  bin: ScoreBin; x: number; scale: number; selected: boolean; dimmed: boolean;
  onSelect: () => void; colors: Record<(typeof TOKENS)[number], string>;
}) {
  const [hover, setHover] = useState(false);
  const riskH = bin.atRisk * scale;
  const safeH = (bin.total - bin.atRisk) * scale;
  const opacity = dimmed && !hover ? 0.28 : 1;
  const lift = selected || hover ? 0.12 : 0;
  return (
    <group position={[x, lift, 0]}
      onPointerOver={(e) => { e.stopPropagation(); setHover(true); document.body.style.cursor = "pointer"; }}
      onPointerOut={() => { setHover(false); document.body.style.cursor = ""; }}
      onClick={(e) => { e.stopPropagation(); onSelect(); }}>
      {/* invisible hit box, bigger than the painted bars */}
      <mesh position={[0, MAX_H / 2, 0]} visible={false}>
        <boxGeometry args={[0.62, MAX_H + 0.4, 0.8]} />
      </mesh>
      {riskH > 0.001 && (
        <RoundedBox args={[0.48, riskH, 0.48]} radius={Math.min(0.06, riskH / 2.2)} position={[0, riskH / 2, 0]}>
          <meshStandardMaterial color={colors.bad} transparent opacity={opacity} roughness={0.35} metalness={0.25} />
        </RoundedBox>
      )}
      {safeH > 0.001 && (
        <RoundedBox args={[0.48, safeH, 0.48]} radius={Math.min(0.06, safeH / 2.2)}
          position={[0, riskH + (riskH > 0 ? GAP : 0) + safeH / 2, 0]}>
          <meshStandardMaterial color={selected ? colors.accent : colors["series-forecast"]} transparent opacity={opacity}
            roughness={0.3} metalness={0.35} emissive={selected ? colors.accent : "#000"} emissiveIntensity={selected ? 0.25 : 0} />
        </RoundedBox>
      )}
      {(hover || selected) && (
        <Html position={[0, riskH + safeH + 0.35, 0]} center distanceFactor={9} zIndexRange={[20, 0]}>
          <div className="tip3d">
            <strong>คะแนน {bin.from}–{bin.to}</strong>
            <div><b className="num">{bin.total.toLocaleString("en-US")}</b> ร้าน</div>
            {bin.atRisk > 0 && <div className="bad-text">เงินอาจไม่พอ {bin.atRisk.toLocaleString("en-US")} ร้าน</div>}
          </div>
        </Html>
      )}
      <Html position={[0, -0.05, 0.5]} center distanceFactor={10} zIndexRange={[10, 0]}>
        <span className="axis3d">{bin.from}</span>
      </Html>
    </group>
  );
}

export default function ScoreHistogram3D({ bins, selected, onSelect }: {
  bins: ScoreBin[];
  selected: number | null;
  onSelect: (i: number | null) => void;
}) {
  const colors = useTokens(TOKENS);
  const max = Math.max(1, ...bins.map((b) => b.total));
  const scale = MAX_H / max;
  const spacing = 0.72;
  const offset = ((bins.length - 1) * spacing) / 2;
  return (
    <Canvas camera={{ position: CAMERA, fov: 38 }} dpr={[1, 2]} onPointerMissed={() => onSelect(null)}
      aria-label="กราฟ 3 มิติ: จำนวนร้านในแต่ละช่วงคะแนนสัญญาณการเงิน">
      <FitCamera base={CAMERA} width={bins.length * spacing + 1} />
      <ambientLight intensity={0.55} />
      <directionalLight position={[4, 8, 5]} intensity={1.3} />
      <pointLight position={[-5, 3, 2]} intensity={14} color={colors["accent-2"]} />
      <Sway paused={selected != null}>
      <group position={[-0.4, -1.4, 0]}>
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.01, 0]}>
          <circleGeometry args={[4.2, 64]} />
          <meshStandardMaterial color={colors["surface-2"]} roughness={0.8} metalness={0.1} transparent opacity={0.9} />
        </mesh>
        {bins.map((b, i) => (
          <Bin key={b.from} bin={b} x={i * spacing - offset} scale={scale} colors={colors}
            selected={selected === i} dimmed={selected != null && selected !== i}
            onSelect={() => onSelect(selected === i ? null : i)} />
        ))}
        <ContactShadows position={[0, 0, 0]} opacity={0.35} scale={10} blur={2.4} far={4} />
      </group>
      </Sway>
      <OrbitControls enableZoom={false} enablePan={false} minPolarAngle={0.6} maxPolarAngle={1.45}
        minAzimuthAngle={-0.9} maxAzimuthAngle={0.9} />
    </Canvas>
  );
}
