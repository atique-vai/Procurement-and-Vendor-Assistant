import ApprovalCard from "./ApprovalCard.jsx";

export default function ManagerDashboard({
  approvals,
  loading,
  error,
  notice,
  workingThread,
  onRefresh,
  onDecision,
  IconComponent,
  formatCurrency,
}) {
  return (
    <section className="approvals-view">
      <div className="approval-summary">
        <div className="summary-icon"><IconComponent name="check" size={21} /></div>
        <div>
          <strong>{approvals.length}</strong>
          <span>{approvals.length === 1 ? "request needs" : "requests need"} your review</span>
        </div>
        <span className="summary-note">Decisions resume the procurement workflow.</span>
      </div>
      {notice && <div className="success-alert" role="status">{notice}</div>}
      {error && <div className="inline-alert" role="alert">{error}</div>}
      {loading ? (
        <div className="empty-state"><span className="loader" /> Loading approval queue...</div>
      ) : error && approvals.length === 0 ? (
        <div className="empty-state">
          <h2>Approval queue unavailable</h2>
          <p>Resolve the connection issue above, then try loading the queue again.</p>
          <button className="quiet-button" type="button" onClick={onRefresh}>
            <IconComponent name="refresh" size={16} /> Retry
          </button>
        </div>
      ) : approvals.length === 0 ? (
        <div className="empty-state">
          <span className="empty-icon"><IconComponent name="check" size={23} /></span>
          <h2>All caught up</h2>
          <p>There are no pending approvals in the workflow right now.</p>
          <button className="quiet-button" type="button" onClick={onRefresh}>
            <IconComponent name="refresh" size={16} /> Refresh queue
          </button>
        </div>
      ) : (
        <div className="approval-grid">
          {approvals.map((item) => (
            <ApprovalCard
              item={item}
              key={item.thread_id}
              busy={workingThread === item.thread_id}
              onDecision={onDecision}
              IconComponent={IconComponent}
              formatCurrency={formatCurrency}
            />
          ))}
        </div>
      )}
      {approvals.length > 0 && (
        <p className="approval-footnote">
          Confirm each request against your organization’s procurement policy before deciding.
        </p>
      )}
    </section>
  );
}