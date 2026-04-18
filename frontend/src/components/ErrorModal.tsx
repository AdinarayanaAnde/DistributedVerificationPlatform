import React from "react";
import "./ErrorModal.css";

interface ErrorModalProps {
  message: string;
  onClose: () => void;
  onRetry: () => void;
  retrying: boolean;
}

export default function ErrorModal({ message, onClose, onRetry, retrying }: ErrorModalProps) {
  return (
    <div className="dvp-modal-overlay">
      <div className="dvp-modal dvp-modal--error">
        <div className="dvp-modal__header">
          <span className="dvp-modal__icon">&#9888;</span>
          <span className="dvp-modal__title">Connection Error</span>
        </div>
        <div className="dvp-modal__body">
          <p>{message}</p>
          <a href="mailto:adinarayana.ande@gmail.com" style={{ color: 'var(--accent)', textDecoration: 'underline', fontSize: '0.95em' }}>
            Need help? Contact support
          </a>
        </div>
        <div className="dvp-modal__footer">
          <button className="dvp-btn dvp-btn--primary" onClick={onRetry} disabled={retrying}>
            {retrying ? "Retrying..." : "Retry"}
          </button>
          <button className="dvp-btn dvp-btn--ghost" style={{ marginLeft: 12 }} onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
