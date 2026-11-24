import { useCallback, useEffect, useMemo, useState } from "react";
import ChatWindow from "./components/chat/ChatWindow.jsx";
import ManagerDashboard from "./components/dashboard/ManagerDashboard.jsx";
import GraphVisualizer from "./components/inspector/GraphVisualizer.jsx";
import useProcurementChat from "./hooks/useProcurementChat.js";
import {
  checkHealth as checkApiHealth,
  getPendingApprovals,
  getWorkflowDefinition,
  getWorkflowState,
  resolveApproval,
} from "./services/api.js";

const navigation = [
  { id: "assistant", label: "Procurement assistant", icon: "chat" },
  { id: "approvals", label: "Approvals", icon: "check" },
  { id: "workflow", label: "Workflow inspector", icon: "nodes" },
];

function Icon({ name, size = 18 }) {
  let shape;
  switch (name) {
    case "brand":
      shape = (
        <>
          <path d="M12 2.8 14.7 9l6.5 3-6.5 3-2.7 6.2L9.3 15 2.8 12l6.5-3L12 2.8Z" />
          <path d="m18.7 2 .8 2.1 2.1.9-2.1.8-.8 2.1-.9-2.1-2.1-.8 2.1-.9.9-2.1Z" />
        </>
      );
      break;
    case "chat":
      shape = (
        <>
          <path d="M20 11.5a7.5 7.5 0 0 1-7.5 7.5H6l-3 2v-9.5a7.5 7.5 0 0 1 7.5-7.5h2A7.5 7.5 0 0 1 20 11.5Z" />
          <path d="M8 11h8M8 14.5h5" />
        </>
      );
      break;
    case "check":
      shape = (
        <>
          <path d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z" />
          <path d="m8 12 2.5 2.5L16.5 9" />
        </>
      );
      break;
    case "nodes":
      shape = (
        <>
          <rect x="3" y="3" width="6" height="6" rx="1.5" />
          <rect x="15" y="15" width="6" height="6" rx="1.5" />
          <rect x="15" y="3" width="6" height="6" rx="1.5" />
          <path d="M9 6h6M6 9v6a3 3 0 0 0 3 3h6" />
        </>
      );
      break;
    case "send":
      shape = (
        <>
          <path d="m21 3-7.2 18-3.5-7.3L3 10.2 21 3Z" />
          <path d="M10.3 13.7 15 9" />
        </>
      );
      break;
    case "plus":
      shape = <path d="M12 5v14M5 12h14" />;
      break;
    case "refresh":
      shape = (
        <>
          <path d="M20 7v5h-5M4 17v-5h5" />
          <path d="M5.6 9a7 7 0 0 1 11.6-2L20 12M4 12l2.8 5a7 7 0 0 0 11.6-2" />
        </>
      );
      break;
    case "arrow":
      shape = (
        <>
          <path d="M7 17 17 7M8 7h9v9" />
        </>
      );
      break;
    case "clock":
      shape = (
        <>
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7v5l3 2" />
        </>
      );
      break;
    default:
      shape = <circle cx="12" cy="12" r="8" />;
  }

  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {shape}
    </svg>
  );
}

function formatCurrency(value, currency = "USD") {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "Not provided";
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency,
    }).format(amount);
  } catch {
    return `${currency} ${amount.toFixed(2)}`;
  }
}

function Sidebar({ activeView, onNavigate, approvalCount }) {
  return (
    <aside className="sidebar">
      <div className="brand-lockup">
        <span className="brand-mark">
          <Icon name="brand" size={22} />
        </span>
        <span className="brand-copy">
          <strong>ProcureAI</strong>
          <span>Procurement workspace</span>
        </span>
      </div>

      <div className="sidebar-caption">WORKSPACE</div>
      <nav className="primary-nav" aria-label="Main navigation">
        {navigation.map((item) => (
          <button
            className={`nav-item ${activeView === item.id ? "is-active" : ""}`}
            key={item.id}
            type="button"
            onClick={() => onNavigate(item.id)}
            aria-current={activeView === item.id ? "page" : undefined}
          >
            <Icon name={item.icon} size={19} />
            <span>{item.label}</span>
            {item.id === "approvals" && approvalCount > 0 && (
              <span className="nav-count">{approvalCount}</span>
            )}
          </button>
        ))}
      </nav>

      <div className="sidebar-spacer" />
      <div className="sidebar-footnote">
        <span className="footnote-icon">
          <Icon name="check" size={17} />
        </span>
        <div>
          <strong>Policy-aware by design</strong>
          <span>Requests are checked against procurement guidance.</span>
        </div>
      </div>
      <div className="workspace-profile">
        <span className="profile-avatar">P</span>
        <span>
          <strong>Procurement team</strong>
          <small>Workspace</small>
        </span>
        <span className="profile-menu" aria-hidden="true">···</span>
      </div>
    </aside>
  );
}

function PageHeader({ title, description, children }) {
  return (
    <div className="page-header">
      <div>
        <div className="breadcrumb">Workspace <span>/</span> {title}</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {children && <div className="page-actions">{children}</div>}
    </div>
  );
}

function WorkflowView({
  threadId,
  definition,
  definitionLoading,
  definitionError,
  inspectorThreadId,
  setInspectorThreadId,
  snapshot,
  stateLoading,
  stateError,
  onLoadDefinition,
  onInspect,
}) {
  return (
    <div className="workflow-view">
      <section className="workflow-card">
        <div className="workflow-card-header">
          <div>
            <div className="eyebrow">LANGGRAPH WORKFLOW</div>
            <h2>Procurement process</h2>
            <p>Inspect the workflow definition and the latest checkpoint for a request.</p>
          </div>
          <button
            className="quiet-button"
            type="button"
            onClick={onLoadDefinition}
            disabled={definitionLoading}
          >
            <Icon name="refresh" size={16} />
            Refresh diagram
          </button>
        </div>
        {definitionError && <div className="inline-alert" role="alert">{definitionError}</div>}
        {definitionLoading ? (
          <div className="empty-state compact"><span className="loader" /> Loading workflow...</div>
        ) : definition ? (
          <GraphVisualizer definition={definition} />
        ) : (
          <div className="empty-state compact">
            <p>Workflow definition is not available yet. Start the backend and retry.</p>
          </div>
        )}
      </section>

      <section className="workflow-card state-card">
        <div className="workflow-card-header">
          <div>
            <div className="eyebrow">CHECKPOINT INSPECTOR</div>
            <h2>Request state</h2>
            <p>Load the latest saved state for a conversation thread.</p>
          </div>
        </div>
        <form className="inspect-form" onSubmit={onInspect}>
          <label htmlFor="thread-id">Thread ID</label>
          <div className="inspect-form-row">
            <input
              id="thread-id"
              value={inspectorThreadId}
              onChange={(event) => setInspectorThreadId(event.target.value)}
              placeholder={threadId || "Paste a workflow thread ID"}
              maxLength={128}
            />
            <button
              className="send-button"
              type="submit"
              disabled={stateLoading || !inspectorThreadId.trim()}
            >
              Inspect <Icon name="arrow" size={15} />
            </button>
          </div>
        </form>
        {stateError && <div className="inline-alert" role="alert">{stateError}</div>}
        {stateLoading && <div className="loading-line"><span className="loader" /> Loading state...</div>}
        {snapshot && (
          <div className="snapshot-results">
            <div className="snapshot-summary">
              <span>Thread <code>{snapshot.thread_id}</code></span>
              <span>Next: {snapshot.next?.length ? snapshot.next.join(", ") : "Complete"}</span>
            </div>
            <details open>
              <summary>State values</summary>
              <pre><code>{JSON.stringify(snapshot.values, null, 2)}</code></pre>
            </details>
            <details>
              <summary>Tasks and metadata</summary>
              <pre><code>{JSON.stringify({ tasks: snapshot.tasks, metadata: snapshot.metadata }, null, 2)}</code></pre>
            </details>
          </div>
        )}
      </section>
      <p className="inspector-note">
        Workflow state can contain request details. Use this inspector only in an authorized workspace.
      </p>
    </div>
  );
}

function App() {
  const [activeView, setActiveView] = useState("assistant");
  const [apiStatus, setApiStatus] = useState("checking");
  const {
    threadId,
    messages,
    prompt,
    setPrompt,
    isSending,
    error: chatError,
    sendMessage,
    startNewConversation,
  } = useProcurementChat();

  const [approvals, setApprovals] = useState([]);
  const [approvalsLoading, setApprovalsLoading] = useState(false);
  const [approvalsError, setApprovalsError] = useState("");
  const [approvalNotice, setApprovalNotice] = useState("");
  const [workingThread, setWorkingThread] = useState("");

  const [definition, setDefinition] = useState("");
  const [definitionLoading, setDefinitionLoading] = useState(false);
  const [definitionError, setDefinitionError] = useState("");
  const [inspectorThreadId, setInspectorThreadId] = useState("");
  const [snapshot, setSnapshot] = useState(null);
  const [stateLoading, setStateLoading] = useState(false);
  const [stateError, setStateError] = useState("");

  const pageInfo = useMemo(
    () => ({
      assistant: {
        title: "Procurement assistant",
        description: "A policy-aware place to turn purchasing needs into clear next steps.",
      },
      approvals: {
        title: "Approval queue",
        description: "Review requests paused for a human decision before the workflow continues.",
      },
      workflow: {
        title: "Workflow inspector",
        description: "Explore the procurement workflow and inspect saved request state.",
      },
    }),
    [],
  );
  const currentPage = pageInfo[activeView];

  useEffect(() => {
    let active = true;
    const checkHealth = () => {
      checkApiHealth()
        .then(() => {
          if (active) setApiStatus("online");
        })
        .catch(() => {
          if (active) setApiStatus("offline");
        });
    };
    checkHealth();
    const intervalId = window.setInterval(checkHealth, 30000);
    return () => {
      active = false;
      window.clearInterval(intervalId);
    };
  }, []);

  const refreshApprovals = useCallback(async () => {
    setApprovalsLoading(true);
    setApprovalsError("");
    try {
      const result = await getPendingApprovals();
      setApprovals(result);
    } catch (error) {
      setApprovalsError(error instanceof Error ? error.message : "Unable to load approvals.");
    } finally {
      setApprovalsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (activeView === "approvals") void refreshApprovals();
  }, [activeView, refreshApprovals]);

  const refreshDefinition = useCallback(async () => {
    setDefinitionLoading(true);
    setDefinitionError("");
    try {
      const result = await getWorkflowDefinition();
      setDefinition(result.mermaid);
    } catch (error) {
      setDefinitionError(error instanceof Error ? error.message : "Unable to load workflow.");
    } finally {
      setDefinitionLoading(false);
    }
  }, []);

  useEffect(() => {
    if (activeView === "workflow" && !definition && !definitionLoading && !definitionError) {
      void refreshDefinition();
    }
  }, [activeView, definition, definitionError, definitionLoading, refreshDefinition]);

  function navigate(view) {
    setActiveView(view);
    if (view === "workflow" && threadId) setInspectorThreadId(threadId);
  }

  async function decideApproval(item, decision) {
    setWorkingThread(item.thread_id);
    setApprovalsError("");
    setApprovalNotice("");
    try {
      await resolveApproval(item.thread_id, decision);
      setApprovalNotice(
        `Request ${decision === "approve" ? "approved" : "rejected"}. The workflow has been resumed.`,
      );
      await refreshApprovals();
    } catch (error) {
      setApprovalsError(
        error instanceof Error ? error.message : "Unable to save the approval decision.",
      );
    } finally {
      setWorkingThread("");
    }
  }

  async function inspectThread(event) {
    event.preventDefault();
    const id = inspectorThreadId.trim();
    if (!id) return;
    setStateLoading(true);
    setStateError("");
    setSnapshot(null);
    try {
      const result = await getWorkflowState(id);
      setSnapshot(result);
    } catch (error) {
      setStateError(error instanceof Error ? error.message : "Unable to inspect this thread.");
    } finally {
      setStateLoading(false);
    }
  }

  return (
    <div className="app-shell">
      <Sidebar
        activeView={activeView}
        onNavigate={navigate}
        approvalCount={approvals.length}
      />
      <div className="main-shell">
        <header className="topbar">
          <div className="topbar-context">
            <span className={`api-status-dot api-${apiStatus}`} />
            <span>
              {apiStatus === "online"
                ? "Backend connected"
                : apiStatus === "checking"
                  ? "Connecting to backend"
                  : "Backend unavailable"}
            </span>
          </div>
          <div className="topbar-right">
            <span className="environment-label">LOCAL WORKSPACE</span>
            <span className="topbar-avatar">P</span>
          </div>
        </header>

        <main className="main-content">
          <PageHeader
            title={currentPage.title}
            description={currentPage.description}
          >
            {activeView === "assistant" && (
              <button
                className="primary-button"
                type="button"
                onClick={startNewConversation}
                disabled={isSending}
              >
                <Icon name="plus" size={17} />
                New request
              </button>
            )}
            {activeView === "approvals" && (
              <button
                className="quiet-button"
                type="button"
                onClick={() => void refreshApprovals()}
                disabled={approvalsLoading}
              >
                <Icon name="refresh" size={16} />
                Refresh
              </button>
            )}
          </PageHeader>

          {activeView === "assistant" && (
            <ChatWindow
              messages={messages}
              threadId={threadId}
              isSending={isSending}
              error={chatError}
              prompt={prompt}
              setPrompt={setPrompt}
              onSubmit={sendMessage}
              onNewConversation={startNewConversation}
              IconComponent={Icon}
              formatCurrency={formatCurrency}
            />
          )}
          {activeView === "approvals" && (
            <ManagerDashboard
              approvals={approvals}
              loading={approvalsLoading}
              error={approvalsError}
              notice={approvalNotice}
              workingThread={workingThread}
              onRefresh={() => void refreshApprovals()}
              onDecision={decideApproval}
              IconComponent={Icon}
              formatCurrency={formatCurrency}
            />
          )}
          {activeView === "workflow" && (
            <WorkflowView
              threadId={threadId}
              definition={definition}
              definitionLoading={definitionLoading}
              definitionError={definitionError}
              inspectorThreadId={inspectorThreadId}
              setInspectorThreadId={setInspectorThreadId}
              snapshot={snapshot}
              stateLoading={stateLoading}
              stateError={stateError}
              onLoadDefinition={() => void refreshDefinition()}
              onInspect={inspectThread}
            />
          )}
        </main>
      </div>
    </div>
  );
}

export default App;