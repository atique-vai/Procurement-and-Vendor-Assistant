import CitationDrawer from "./CitationDrawer.jsx";

function formatTime(value = new Date()) {
  return new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
  }).format(value instanceof Date ? value : new Date(value));
}

function PurchaseOrderSummary({ order, formatCurrency }) {
  if (!order || !Array.isArray(order.items)) return null;
  const currency = order.currency || "USD";

  return (
    <section className="purchase-order-card" aria-label="Purchase order draft">
      <div className="po-card-heading">
        <div>
          <span className="eyebrow">Purchase order</span>
          <strong>{order.po_id || "Draft for review"}</strong>
        </div>
        {order.status && <span className="status-tag">{order.status}</span>}
      </div>
      {(order.department || order.cost_center_id) && (
        <p className="po-meta">
          {[order.department, order.cost_center_id].filter(Boolean).join(" · ")}
        </p>
      )}
      <div className="po-items">
        {order.items.map((item, index) => (
          <div className="po-item" key={`${item.product_id || item.item_name}-${index}`}>
            <div>
              <strong>{item.item_name || item.product_id || "Catalog item"}</strong>
              <span>
                {item.quantity || 1} × {formatCurrency(item.unit_price, item.currency || currency)}
              </span>
            </div>
            <span className="po-line-total">
              {formatCurrency(
                item.line_total ?? Number(item.quantity || 1) * Number(item.unit_price || 0),
                item.currency || currency,
              )}
            </span>
          </div>
        ))}
      </div>
      <div className="po-total">
        <span>Estimated total</span>
        <strong>{formatCurrency(order.total_amount, currency)}</strong>
      </div>
    </section>
  );
}

export default function MessageBubble({ message, IconComponent, formatCurrency }) {
  const isAssistant = message.role === "assistant";

  return (
    <article className={`message-row ${isAssistant ? "message-assistant" : "message-user"}`}>
      {isAssistant && (
        <span className="message-avatar">
          <IconComponent name="brand" size={16} />
        </span>
      )}
      <div className="message-content">
        <div className="message-meta">
          <strong>{isAssistant ? "Procurement assistant" : "You"}</strong>
          <time>{formatTime(message.time)}</time>
          {message.status === "waiting_for_approval" && (
            <span className="message-status">Manager review</span>
          )}
        </div>
        <div className="message-bubble">{message.text}</div>
        {message.purchaseOrder && (
          <PurchaseOrderSummary
            order={message.purchaseOrder}
            formatCurrency={formatCurrency}
          />
        )}
        {isAssistant && <CitationDrawer citations={message.citations} />}
      </div>
    </article>
  );
}