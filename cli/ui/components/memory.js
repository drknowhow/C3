// ─── Memory ───────────────────────────────
// Globals: T, I, GlowDot, Badge, StatBox, Btn, api, timeAgo, localDate, useState, useEffect

const Memory = () => {
  const [facts, setFacts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [newFact, setNewFact] = useState("");
  const [category, setCategory] = useState("general");
  const [storing, setStoring] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState(null);
  const [searching, setSearching] = useState(false);
  const [decisions, setDecisions] = useState([]);
  const [decisionsExpanded, setDecisionsExpanded] = useState(false);

  const categories = ["general", "architecture", "convention", "bug", "preference"];
  const catColors = {
    general: T.textMuted,
    architecture: T.blue,
    convention: T.purple,
    bug: T.error,
    preference: T.warn,
  };

  const loadFacts = () => {
    api.get('/api/memory/facts')
      .then(f => { setFacts(f); setLoading(false); })
      .catch(() => setLoading(false));
  };

  const loadDecisions = () => {
    api.get('/api/activity?type=decision&limit=50')
      .then(d => setDecisions(d))
      .catch(() => {});
  };

  useEffect(() => {
    loadFacts();
    loadDecisions();
    const iv = setInterval(() => { loadFacts(); loadDecisions(); }, 5000);
    return () => clearInterval(iv);
  }, []);

  const handleRemember = async () => {
    if (!newFact.trim()) return;
    setStoring(true);
    try {
      await api.post('/api/memory/remember', { fact: newFact, category });
      setNewFact("");
      loadFacts();
    } catch (e) {}
    setStoring(false);
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearching(true);
    try {
      const r = await api.post('/api/memory/recall', { query: searchQuery, top_k: 10 });
      setSearchResults(r);
    } catch (e) {}
    setSearching(false);
  };

  const handleDelete = async (id) => {
    await api.del(`/api/memory/facts/${id}`);
    loadFacts();
    if (searchResults) {
      setSearchResults(searchResults.filter(f => f.id !== id));
    }
  };

  const [exportMsg, setExportMsg] = useState(null);
  const handleExport = async () => {
    try {
      const r = await api.get('/api/memory/export');
      await navigator.clipboard.writeText(r.markdown);
      setExportMsg(`Copied ${r.count} facts as markdown`);
      setTimeout(() => setExportMsg(null), 3000);
    } catch (e) {
      setExportMsg("Export failed");
      setTimeout(() => setExportMsg(null), 3000);
    }
  };

  const totalRecalls = facts.reduce((s, f) => s + (f.relevance_count || 0), 0);

  // Group facts by category
  const grouped = {};
  facts.forEach(f => {
    const cat = f.category || "general";
    if (!grouped[cat]) grouped[cat] = [];
    grouped[cat].push(f);
  });

  return (
    <div className="fade-up" style={{ display: "flex", flexDirection: "column", gap: 16 }}>

      {/* Stats row */}
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <StatBox label="Stored Facts" value={facts.length} color={T.purple} loading={loading} />
        <StatBox label="Total Recalls" value={totalRecalls} sub="relevance score sum" color={T.accent} loading={loading} />
        <StatBox label="Decisions" value={decisions.length} sub="from sessions" color={T.blue} />
      </div>

      {/* Remember form */}
      <div style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 8, padding: 18 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: T.textMuted, textTransform: "uppercase", letterSpacing: 1, marginBottom: 12 }}>
          Remember a Fact
        </div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
          <div style={{ flex: 1, minWidth: 250 }}>
            <input
              value={newFact}
              onChange={e => setNewFact(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleRemember()}
              placeholder="Enter a fact to remember..."
              className="mono"
              style={{
                width: "100%", padding: "9px 12px", borderRadius: 6,
                background: T.surfaceAlt, border: `1px solid ${T.border}`,
                color: T.text, fontSize: 12, outline: "none",
              }}
            />
          </div>
          <select
            value={category}
            onChange={e => setCategory(e.target.value)}
            className="mono"
            style={{
              padding: "9px 12px", borderRadius: 6,
              background: T.surfaceAlt, border: `1px solid ${T.border}`,
              color: T.text, fontSize: 12, outline: "none",
            }}
          >
            {categories.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
          <Btn color={T.purple} onClick={handleRemember} disabled={!newFact.trim() || storing}>
            <I name="bookmark" size={14} /> {storing ? "Storing..." : "Remember"}
          </Btn>
        </div>
      </div>

      {/* Search */}
      <div style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 8, padding: 18 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: T.textMuted, textTransform: "uppercase", letterSpacing: 1, marginBottom: 12 }}>
          Search Facts
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          <div style={{
            flex: 1, display: "flex", alignItems: "center", gap: 8,
            padding: "0 14px", borderRadius: 6,
            background: T.surfaceAlt, border: `1px solid ${T.border}`,
          }}>
            <I name="search" size={14} color={T.textMuted} />
            <input
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleSearch()}
              placeholder="Search stored facts..."
              className="mono"
              style={{
                flex: 1, padding: "10px 0", background: "transparent",
                border: "none", color: T.text, fontSize: 13, outline: "none",
              }}
            />
          </div>
          <Btn color={T.blue} onClick={handleSearch} disabled={searching || !searchQuery.trim()}>
            <I name="search" size={14} /> {searching ? "Searching..." : "Search"}
          </Btn>
        </div>
        {searchResults && (
          <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 6 }}>
            {searchResults.length === 0 && (
              <div style={{ padding: 16, textAlign: "center", color: T.textMuted, fontSize: 13 }}>
                No matching facts found.
              </div>
            )}
            {searchResults.map((f, i) => (
              <div
                key={f.id}
                style={{
                  display: "flex", alignItems: "center", gap: 10,
                  padding: "10px 12px", borderRadius: 6,
                  background: T.surfaceAlt, border: `1px solid ${T.border}`,
                }}
              >
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, color: T.text, marginBottom: 4 }}>{f.fact}</div>
                  <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                    <Badge color={catColors[f.category] || T.textMuted}>{f.category}</Badge>
                    <span className="mono" style={{ fontSize: 10, color: T.textDim }}>recalls: {f.relevance_count}</span>
                    {f.score !== undefined && <Badge color={T.accent}>score: {f.score}</Badge>}
                  </div>
                </div>
                <button onClick={() => handleDelete(f.id)} style={{ background: "none", border: "none", cursor: "pointer", padding: 4 }}>
                  <I name="trash" size={14} color={T.error} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Decisions (collapsible) */}
      {decisions.length > 0 && (
        <div style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 8, overflow: "hidden" }}>
          <div
            onClick={() => setDecisionsExpanded(!decisionsExpanded)}
            style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              padding: "12px 18px", background: T.surfaceAlt, cursor: "pointer",
              borderBottom: decisionsExpanded ? `1px solid ${T.border}` : "none",
            }}
          >
            <span style={{
              fontSize: 12, fontWeight: 600, color: T.textMuted,
              textTransform: "uppercase", letterSpacing: 1,
              display: "flex", alignItems: "center", gap: 6,
            }}>
              <I name="brain" size={13} color={T.blue} /> Decisions
              <Badge color={T.blue}>{decisions.length}</Badge>
            </span>
            <I
              name="chevron"
              size={14}
              color={T.textMuted}
              style={{ transform: decisionsExpanded ? "rotate(90deg)" : "none", transition: "transform 0.15s" }}
            />
          </div>
          {decisionsExpanded && (
            <div style={{ padding: 14, display: "flex", flexDirection: "column", gap: 6 }}>
              {decisions.map((d, i) => (
                <div
                  key={i}
                  style={{
                    display: "flex", gap: 10, padding: "10px 12px",
                    borderRadius: 6, background: T.surfaceAlt,
                    border: `1px solid ${T.border}20`,
                  }}
                >
                  <GlowDot color={T.blue} size={6} />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 12, color: T.text, lineHeight: 1.5 }}>{d.decision}</div>
                    {d.reasoning && (
                      <div style={{ fontSize: 11, color: T.textMuted, marginTop: 4, fontStyle: "italic" }}>
                        {d.reasoning}
                      </div>
                    )}
                    <div className="mono" style={{ fontSize: 10, color: T.textDim, marginTop: 4 }}>
                      {timeAgo(d.timestamp)}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* All facts grouped by category */}
      <div style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 8, padding: 18 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: T.textMuted, textTransform: "uppercase", letterSpacing: 1 }}>
            All Facts
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {exportMsg && <span style={{ fontSize: 11, color: T.accent }}>{exportMsg}</span>}
            <Btn color={T.purple} onClick={handleExport} disabled={facts.length === 0}>
              <I name="copy" size={13} /> Export Markdown
            </Btn>
          </div>
        </div>
        {facts.length === 0 && !loading && (
          <div style={{ padding: 20, textAlign: "center", color: T.textMuted, fontSize: 13 }}>
            No facts stored yet. Use the form above or the MCP remember tool.
          </div>
        )}
        {Object.entries(grouped).map(([cat, items]) => (
          <div key={cat} style={{ marginBottom: 14 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <Badge color={catColors[cat] || T.textMuted}>{cat}</Badge>
              <span style={{ fontSize: 11, color: T.textDim }}>({items.length})</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {items.map(f => (
                <div
                  key={f.id}
                  style={{
                    display: "flex", alignItems: "center", gap: 10,
                    padding: "8px 12px", borderRadius: 6, background: T.surfaceAlt,
                  }}
                >
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 12, color: T.text }}>{f.fact}</div>
                    <div className="mono" style={{ fontSize: 10, color: T.textDim, marginTop: 2 }}>
                      {localDate(f.timestamp)} | recalls: {f.relevance_count}
                      {f.source_session && <> | session: {f.source_session.slice(0, 8)}</>}
                    </div>
                  </div>
                  <button onClick={() => handleDelete(f.id)} style={{ background: "none", border: "none", cursor: "pointer", padding: 4 }}>
                    <I name="trash" size={14} color={T.error} />
                  </button>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

    </div>
  );
};
