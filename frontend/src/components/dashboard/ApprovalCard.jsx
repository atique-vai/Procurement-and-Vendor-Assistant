import { useEffect, useState } from "react";

import { getWorkflowState } from "../../services/api.js";

function purchaseOrderFrom(details) {
  if (!details || typeof details !== "object" || Array.isArray(details)) {
    return null;
  }
  if (Array.isArray(details.items)) return details;
  for (const key of [
    "purchase_order",
    "po_draft",
    "draft_po",
    "approval_request",
    "approval",
    "request",
    "value",
  ]) {
    const found = purchaseOrderFrom(details[key]);
    if (found) return found;
  }
  return null;
}

export default function ApprovalCard({
  item,
  busy,
  onDecision,
  IconComponent,
  formatCurrency,
}) {
  const [order, setOrder] = useState(() => purchaseOrderFrom(item.details));
  const [orderLoading, setOrderLoading] = useState(false);
  const [orderError, setOrderError] = useState("");
  const requester = order?.requester_name || order?.department || "Procurement request";

  useEffect(() => {
    setOrder(purchaseOrderFrom(item.details));
    setOrderError("");
  }, [item.details]);

  async function loadOrderDetails() {
    setOrderLoading(true);
    setOrderError("");
    try {
      const state = await getWorkflowState(item.thread_id);
      const foundOrder = purchaseOrderFrom(state.values);
      if (!foundOrder) {
        throw new Error("No purchase order details were found for this workflow.");
      }
      setOrder(foundOrder);
    } catch (error) {
      setOrderError(
        error instanceof Error ? error.message : "Unable to load purchase order details.",
      );
    } finally {
      setOrderLoading(false);
    }
  }

  return (
    <article className="approval-card">
      <div className="approval-card-top">
        <span className="approval-icon"><IconComponent name="clock" size={18} /></span>
        <div className="approval-title">
          <span className="eyebrow">AWAITING REVIEW</span>
          <h3>{requester}</h3>
        </div>
        <span className="status-tag status-pending">{item.status || "Pending"}</span>
      </div>
      {order ? (
        <div className="approval-order">
          <div className="approval-order-meta">
            <span>{order.po_id || "Purchase order draft"}</span>
            {order.cost_center_id && <span>{order.cost_center_id}</span>}
          </div>
          <div className="approval-items">
            {(order.items || []).slice(0, 3).map((line, index) => (
              <div key={`${line.product_id || line.item_name}-${index}`}>
                <span>{line.item_name || line.product_id || "Catalog item"}</span>
                <span>×{line.quantity || 1}</span>
              </div>
            ))}
            {order.items.length > 3 && (
              <span className="muted-copy">+{order.items.length - 3} more items</span>
            )}
          </div>
          <div className="approval-total">
            <span>Estimated total</span>
            <strong>{formatCurrency(order.total_amount, order.currency || "USD")}</strong>
          </div>
        </div>
      ) : (
        <div className="approval-order approval-details-missing">
          <p className="muted-copy">Load the request state to review its purchase details.</p>
          {orderError && <p className="inline-alert" role="alert">{orderError}</p>}
          <button
            className="quiet-button"
            type="button"
            onClick={() => void loadOrderDetails()}
            disabled={orderLoading}
          >
            {orderLoading ? "Loading details..." : "Load purchase details"}
          </button>
        </div>
      )}
      <div className="approval-card-footer">
        <div className="thread-reference">
          <span>THREAD</span>
          <code title={item.thread_id}>{item.thread_id}</code>
        </div>
        <div className="approval-actions">
          <button
            className="decision-button decision-reject"
            type="button"
            disabled={busy || !order}
            onClick={() => onDecision(item, "reject")}
            title={!order ? "Load purchase details before deciding" : undefined}
          >
            Reject
          </button>
          <button
            className="decision-button decision-approve"
            type="button"
            disabled={busy || !order}
            onClick={() => onDecision(item, "approve")}
            title={!order ? "Load purchase details before deciding" : undefined}
          >
            {busy ? "Saving..." : "Approve"}
          </button>
        </div>
      </div>
    </article>
  );
}