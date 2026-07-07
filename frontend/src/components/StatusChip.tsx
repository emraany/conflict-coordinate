import { colors, statusColor } from "../styles/tokens";
import type { ConflictStatus, CrisisStatus } from "../types";

interface Props {
  status: CrisisStatus | ConflictStatus;
}

export function StatusChip({ status }: Props) {
  const c = statusColor(status);
  return (
    <span
      className="stamp"
      style={{
        fontSize: 10,
        letterSpacing: "0.2em",
        color: c,
        border: `1px solid ${c}`,
        padding: "2px 8px",
        whiteSpace: "nowrap",
        background: `color-mix(in srgb, ${c} 8%, ${colors.bg})`,
      }}
    >
      [ {status.toUpperCase()} ]
    </span>
  );
}
