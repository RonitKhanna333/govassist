import type { ReactElement } from "react";

export type UseCaseSpec = {
  kind: "usecase";
  id: string;
  actors: string[];
  cases: { lines: string[]; actor: number }[];
};

export type SequenceSpec = {
  kind: "sequence";
  id: string;
  participants: string[];
  steps: { from: number; to: number; lines: string[] }[];
};

export type ClassSpec = {
  kind: "class";
  id: string;
  nodes: { id: string; title: string; lines: string[]; x: number; y: number; w: number; h: number }[];
  relations: { from: string; to: string; label: string }[];
};

export type DiagramSpec = UseCaseSpec | SequenceSpec | ClassSpec;

const palette = {
  background: "#101722",
  boundary: "#64748b",
  ink: "#f1efe7",
  muted: "#aab3c2",
  accent: "#d7af54",
  green: "#8dc49d",
  card: "#1a2433",
  line: "#7d8ba0",
};

function Lines({ lines, x, y, size = 14, fill = palette.ink, anchor = "middle" }: {
  lines: string[];
  x: number;
  y: number;
  size?: number;
  fill?: string;
  anchor?: "start" | "middle" | "end";
}) {
  return (
    <text x={x} y={y} textAnchor={anchor} fill={fill} fontSize={size} fontFamily="Segoe UI, Arial, sans-serif">
      {lines.map((line, index) => (
        <tspan key={`${line}-${index}`} x={x} dy={index === 0 ? 0 : size + 3}>
          {line}
        </tspan>
      ))}
    </text>
  );
}

function Actor({ label, x, y }: { label: string; x: number; y: number }) {
  return (
    <g>
      <circle cx={x} cy={y - 20} r="10" fill="none" stroke={palette.accent} strokeWidth="2" />
      <path d={`M${x} ${y - 10}V${y + 16}M${x - 15} ${y}H${x + 15}M${x} ${y + 16}l-12 17M${x} ${y + 16}l12 17`} fill="none" stroke={palette.accent} strokeWidth="2" strokeLinecap="round" />
      <Lines lines={[label]} x={x} y={y + 55} size={13} />
    </g>
  );
}

function UseCaseDiagram({ spec }: { spec: UseCaseSpec }) {
  const slug = spec.id.replace(/[^a-z0-9]/gi, "-");
  const caseX = 325;
  return (
    <svg className="diagram-svg" viewBox="0 0 880 360" role="img" aria-label={`${spec.id} use case diagram`}>
      <defs>
        <marker id={`${slug}-arrow`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M0 0L10 5L0 10z" fill={palette.line} />
        </marker>
      </defs>
      <rect x="210" y="15" width="650" height="330" rx="12" fill="none" stroke={palette.boundary} strokeDasharray="8 7" />
      <Lines lines={["GovAssist"]} x={230} y={37} size={13} fill={palette.muted} anchor="start" />
      {spec.actors.map((actor, index) => <Actor key={actor} label={actor} x={88} y={65 + index * 95} />)}
      {spec.cases.map((item, index) => {
        const y = 46 + index * 41;
        const actorY = 65 + item.actor * 95;
        return (
          <g key={`${item.lines[0]}-${index}`}>
            <line x1="140" y1={actorY} x2={caseX} y2={y + 20} stroke={palette.line} strokeWidth="1.5" markerEnd={`url(#${slug}-arrow)`} />
            <rect x={caseX} y={y} width="420" height="34" rx="17" fill={palette.card} stroke={palette.accent} />
            <Lines lines={item.lines} x={caseX + 210} y={y + (item.lines.length === 1 ? 22 : 13)} size={11} />
          </g>
        );
      })}
    </svg>
  );
}

function SequenceDiagram({ spec }: { spec: SequenceSpec }) {
  const slug = spec.id.replace(/[^a-z0-9]/gi, "-");
  const left = 18;
  const gap = 144;
  const center = (index: number) => left + index * gap + 62;
  return (
    <svg className="diagram-svg" viewBox="0 0 880 360" role="img" aria-label={`${spec.id} sequence diagram`}>
      <defs>
        <marker id={`${slug}-arrow`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M0 0L10 5L0 10z" fill={palette.green} />
        </marker>
      </defs>
      {spec.participants.map((participant, index) => (
        <g key={participant}>
          <rect x={left + index * gap} y="12" width="124" height="38" rx="7" fill={palette.card} stroke={palette.accent} />
          <Lines lines={participant.split(" / ")} x={center(index)} y={participant.includes(" / ") ? 27 : 36} size={11} />
          <line x1={center(index)} y1="50" x2={center(index)} y2="346" stroke={palette.boundary} strokeDasharray="4 5" />
        </g>
      ))}
      {spec.steps.map((step, index) => {
        const y = 76 + index * 39;
        const x1 = center(step.from);
        const x2 = center(step.to);
        const direction = x2 >= x1 ? 1 : -1;
        return (
          <g key={`${step.lines[0]}-${index}`}>
            <line x1={x1} y1={y} x2={x2 - direction * 4} y2={y} stroke={palette.green} strokeWidth="1.5" markerEnd={`url(#${slug}-arrow)`} />
            <Lines lines={step.lines} x={(x1 + x2) / 2} y={y - 6} size={10} fill={palette.muted} />
          </g>
        );
      })}
    </svg>
  );
}

function ClassDiagram({ spec }: { spec: ClassSpec }) {
  const slug = spec.id.replace(/[^a-z0-9]/gi, "-");
  const byId = Object.fromEntries(spec.nodes.map((node) => [node.id, node]));
  return (
    <svg className="diagram-svg" viewBox="0 0 1000 390" role="img" aria-label={`${spec.id} class diagram`}>
      <defs>
        <marker id={`${slug}-arrow`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M0 0L10 5L0 10z" fill={palette.line} />
        </marker>
      </defs>
      {spec.relations.map((relation) => {
        const from = byId[relation.from];
        const to = byId[relation.to];
        if (!from || !to) return null;
        const rightward = from.x < to.x;
        const x1 = rightward ? from.x + from.w : from.x;
        const x2 = rightward ? to.x : to.x + to.w;
        const y1 = from.y + from.h / 2;
        const y2 = to.y + to.h / 2;
        return (
          <g key={`${relation.from}-${relation.to}`}>
            <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={palette.line} strokeWidth="1.4" markerEnd={`url(#${slug}-arrow)`} />
            <Lines lines={[relation.label]} x={(x1 + x2) / 2} y={(y1 + y2) / 2 - 5} size={9} fill={palette.muted} />
          </g>
        );
      })}
      {spec.nodes.map((node) => (
        <g key={node.id}>
          <rect x={node.x} y={node.y} width={node.w} height={node.h} rx="7" fill={palette.card} stroke={palette.accent} />
          <rect x={node.x} y={node.y} width={node.w} height="30" rx="7" fill="#243247" />
          <Lines lines={[node.title]} x={node.x + node.w / 2} y={node.y + 20} size={11} />
          <Lines lines={node.lines} x={node.x + 12} y={node.y + 49} size={9} fill={palette.muted} anchor="start" />
        </g>
      ))}
    </svg>
  );
}

export function DiagramPreview({ spec }: { spec: DiagramSpec }): ReactElement {
  if (spec.kind === "usecase") return <UseCaseDiagram spec={spec} />;
  if (spec.kind === "sequence") return <SequenceDiagram spec={spec} />;
  return <ClassDiagram spec={spec} />;
}
