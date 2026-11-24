export default function JsonDebugPanel({ snapshot }) {
  if (!snapshot) return null;

  const sections = [
    { title: "State values", value: snapshot.values, open: true },
    {
      title: "Tasks and metadata",
      value: { tasks: snapshot.tasks, metadata: snapshot.metadata },
      open: false,
    },
  ];

  return (
    <div className="snapshot-results">
      <div className="snapshot-summary">
        <span>
          Thread <code>{snapshot.thread_id}</code>
        </span>
        <span>
          Next: {snapshot.next?.length ? snapshot.next.join(", ") : "Complete"}
        </span>
      </div>
      {sections.map(({ title, value, open }) => (
        <details key={title} open={open}>
          <summary>{title}</summary>
          <pre>
            <code>{JSON.stringify(value, null, 2)}</code>
          </pre>
        </details>
      ))}
    </div>
  );
}