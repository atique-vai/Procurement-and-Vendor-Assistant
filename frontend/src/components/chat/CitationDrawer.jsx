function citationText(value) {
  return typeof value === "string" ? value.trim() : "";
}

function citationLabel(citation) {
  return (
    citationText(citation.doc_title) ||
    citationText(citation.title) ||
    citationText(citation.source) ||
    "Procurement policy"
  );
}

export default function CitationDrawer({ citations }) {
  if (!Array.isArray(citations)) return null;
  const sources = citations.filter(
    (citation) => citation && typeof citation === "object" && !Array.isArray(citation),
  );
  if (sources.length === 0) return null;

  return (
    <details className="citation-drawer">
      <summary className="citation-drawer-summary">
        <span className="citation-summary-mark" aria-hidden="true">§</span>
        <span className="citation-summary-copy">
          <strong>Policy sources</strong>
          <span>
            {sources.length} cited {sources.length === 1 ? "source" : "sources"}
          </span>
        </span>
        <span className="citation-toggle" aria-hidden="true" />
      </summary>
      <div className="citation-drawer-content">
        {sources.map((citation, index) => {
          const title = citationLabel(citation);
          const section = citationText(citation.section);
          const source = citationText(citation.source);
          const snippet = citationText(citation.snippet);
          const page = citation.page;
          const hasConfidence =
            typeof citation.confidence === "number" &&
            Number.isFinite(citation.confidence) &&
            citation.confidence >= 0 &&
            citation.confidence <= 1;
          const key = `${title}-${section}-${page ?? ""}-${index}`;

          return (
            <article className="citation-card" key={key}>
              <span className="citation-marker">{String(index + 1).padStart(2, "0")}</span>
              <div className="citation-card-content">
                <strong>{title}</strong>
                {section && <span className="citation-section">{section}</span>}
                <div className="citation-source-meta">
                  {source && source !== title && <span>{source}</span>}
                  {(typeof page === "string" || typeof page === "number") && (
                    <span>Page {page}</span>
                  )}
                  {hasConfidence && (
                    <span>{Math.round(citation.confidence * 100)}% match</span>
                  )}
                </div>
                {snippet && <p>{snippet}</p>}
              </div>
            </article>
          );
        })}
      </div>
    </details>
  );
}