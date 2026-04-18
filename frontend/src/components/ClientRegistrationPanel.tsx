interface ClientRegistrationPanelProps {
  name: string;
  onSetName: (name: string) => void;
  clientKey: string;
  onRegisterClient: () => void;
  resourceName: string;
  onSetResourceName: (name: string) => void;
}

export function ClientRegistrationPanel({
  name,
  onSetName,
  clientKey,
  onRegisterClient,
  resourceName,
  onSetResourceName,
}: ClientRegistrationPanelProps) {
  return (
    <div className="dvp-sidebar__section">
      <div className="dvp-sidebar__section-title">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
          <circle cx="12" cy="7" r="4" />
        </svg>
        Client
      </div>
      {!clientKey ? (
        <div className="dvp-inline-form">
          <input
            className="dvp-input"
            value={name}
            onChange={(e) => onSetName(e.target.value)}
            placeholder="Your name or team name"
            onKeyDown={(e) => e.key === "Enter" && onRegisterClient()}
          />
          <button className="dvp-btn dvp-btn--primary dvp-btn--sm" onClick={onRegisterClient}>
            Register
          </button>
        </div>
      ) : (
        <div className="dvp-client-badge">
          ✓ {name}
          <code title={clientKey}>
            {clientKey.slice(0, 12)}
            …
          </code>
        </div>
      )}
      <div className="dvp-resource-row">
        <label>Resource:</label>
        <input
          className="dvp-input"
          value={resourceName}
          onChange={(e) => onSetResourceName(e.target.value)}
          style={{ height: 26, fontSize: 11 }}
        />
      </div>
    </div>
  );
}
