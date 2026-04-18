import { CLI_EXAMPLES } from "../constants";

interface CliPanelProps {
  cliCommand: string;
  onSetCliCommand: (cmd: string) => void;
  canRun: boolean;
  onRun: () => void;
}

export function CliPanel({ cliCommand, onSetCliCommand, canRun, onRun }: CliPanelProps) {
  return (
    <div className="dvp-cli-panel">
      <div className="dvp-sidebar__section-title" style={{ marginBottom: 0 }}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <polyline points="4 17 10 11 4 5" />
          <line x1="12" y1="19" x2="20" y2="19" />
        </svg>
        CLI Command
      </div>

      <div className="dvp-cli-hint">
        Run any test command directly. Allowed prefixes:
        <br />
        <code>pytest</code>, <code>python -m pytest</code>, <code>python -m unittest</code>
      </div>

      <input
        className="dvp-cli-input"
        value={cliCommand}
        onChange={(e) => onSetCliCommand(e.target.value)}
        placeholder="pytest tests/ -v --tb=short"
        onKeyDown={(e) => e.key === "Enter" && canRun && onRun()}
      />

      <div className="dvp-sidebar__section-title" style={{ marginBottom: 0, marginTop: 8 }}>
        Quick Examples
      </div>
      <div className="dvp-cli-examples">
        {CLI_EXAMPLES.map((cmd) => (
          <div key={cmd} className="dvp-cli-example" onClick={() => onSetCliCommand(cmd)}>
            $ {cmd}
          </div>
        ))}
      </div>
    </div>
  );
}
