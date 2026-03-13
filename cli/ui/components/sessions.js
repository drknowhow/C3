// SessionsPanel — merged Sessions + ActivityLog sub-views
// Globals: T, I, GlowDot, Badge, StatBox, Btn, api, timeAgo, localTime,
//          getToolColor, typeColors, useLiveDuration, useState, useEffect, useCallback

const SessionsPanel = () => {
  const [subView, setSubView] = useState("sessions"); // "sessions" | "activity"

  // ── Sessions state ─────────────────────────────────────────────────────────
  const [sessions, setSessions] = useState([]);
  const [currentSession, setCurrentSession] = useState(null);
  const [expanded, setExpanded] = useState(null);
  const [detail, setDetail] = useState(null);
  const [sessionsLoading, setSessionsLoading] = useState(true);

  const liveDuration = useLiveDuration(currentSession?.started, currentSession?.live);

  const loadSessions = useCallback(async () => {
    try {
      const s = await api.get("/api/sessions");
      setSessions(s);
      setSessionsLoading(false);
    } catch (e) { setSessionsLoading(false); }
  }, []);

  const loadCurrentSession = useCallback(async () => {
    try {
      const cur = await api.get("/api/sessions/current");
      setCurrentSession(cur);
    } catch (e) {}
  }, []);

  useEffect(() => {
    loadSessions();
    loadCurrentSession();
  }, [loadSessions, loadCurrentSession]);

  // Auto-refresh sessions list + current session + expanded detail every 5s
  useEffect(() => {
    const iv = setInterval(async () => {
      await loadSessions();
      await loadCurrentSession();
      if (expanded !== null && detail?.id) {
        try {
          const d = await api.get(`/api/sessions/${detail.id}`);
          if ((!d.tool_calls || d.tool_calls.length === 0) && d.started) {
            const params = new URLSearchParams({ type: "tool_call", limit: "200", since: d.started });
            if (d.ended) params.set("until", d.ended);
            const activityTools = await api.get(`/api/activity?${params}`);
            if (activityTools.length > 0) {
              d.tool_calls = activityTools.map(e => ({
                tool: e.tool || "unknown",
                args: e.args || {},
                result_summary: e.result_summary || "",
                timestamp: e.timestamp || "",
              })).reverse();
            }
          }
          setDetail(d);
        } catch (e) {}
      }
    }, 5000);
    return () => clearInterval(iv);
  }, [expanded, detail?.id, loadSessions, loadCurrentSession]);

  const handleExpand = async (i, id) => {
    if (expanded === i) { setExpanded(null); setDetail(null); return; }
    setExpanded(i);
    if (i === "current") return;
    try {
      const d = await api.get(`/api/sessions/${id}`);
      if ((!d.tool_calls || d.tool_calls.length === 0) && d.started) {
        const params = new URLSearchParams({ type: "tool_call", limit: "200", since: d.started });
        if (d.ended) params.set("until", d.ended);
        const activityTools = await api.get(`/api/activity?${params}`);
        if (activityTools.length > 0) {
          d.tool_calls = activityTools.map(e => ({
            tool: e.tool || "unknown",
            args: e.args || {},
            result_summary: e.result_summary || "",
            timestamp: e.timestamp || "",
          })).reverse();
        }
      }
      setDetail(d);
    } catch (e) { setDetail(null); }
  };

  // ── Activity state ──────────────────────────────────────────────────────────
  const [events, setEvents] = useState([]);
  const [actStats, setActStats] = useState(null);
  const [actFilter, setActFilter] = useState("");
  const [actLoading, setActLoading] = useState(true);
  const [actExpanded, setActExpanded] = useState(null);
  const [autoRefresh, setAutoRefresh] = useState(false);

  const eventTypes = ["tool_call", "decision", "file_change", "fact_stored", "session_start", "session_save"];

  const loadActivity = useCallback(async () => {
    try {
      const params = new URLSearchParams({ limit: "100" });
      if (actFilter) params.set("type", actFilter);
      const [ev, st] = await Promise.all([
        api.get(`/api/activity?${params}`),
        api.get("/api/activity/stats"),
      ]);
      setEvents(ev);
      setActStats(st);
    } catch (e) {}
    setActLoading(false);
  }, [actFilter]);

  useEffect(() => { loadActivity(); }, [loadActivity]);

  useEffect(() => {
    if (!autoRefresh) return;
    const iv = setInterval(loadActivity, 5000);
    return () => clearInterval(iv);
  }, [autoRefresh, loadActivity]);

  const todayCount = events.filter(e => {
    if (!e.timestamp) return false;
    return new Date(e.timestamp).toDateString() === new Date().toDateString();
  }).length;

  const eventSummary = (e) => {
    switch (e.type) {
      case "tool_call":    return `${e.tool || "unknown"} — ${e.result_summary || JSON.stringify(e.args || {}).slice(0, 60)}`;
      case "decision":     return e.decision || "";
      case "file_change":  return `${e.file || ""} (${e.change_type || "modified"})`;
      case "fact_stored":  return `[${e.category || "general"}] ${e.fact || ""}`;
      case "session_start":return `Session ${e.session_id || ""} — ${e.description || ""}`;
      case "session_save": return `Session ${e.session_id || ""} saved${e.summary ? ": " + e.summary : ""}`;
      default:             return JSON.stringify(e).slice(0, 80);
    }
  };

  // ── Sub-view toggle ─────────────────────────────────────────────────────────
  const tabStyle = (active) => ({
    padding: "6px 16px",
    borderRadius: 6,
    border: `1px solid ${active ? T.accent + "60" : T.border}`,
    background: active ? T.accentDim : "transparent",
    color: active ? T.accent : T.textMuted,
    fontSize: 12,
    fontFamily: "'JetBrains Mono', monospace",
    cursor: "pointer",
    transition: "all 0.15s",
  });

  // ── C3 Token Usage block (shared between current + past session detail) ─────
  const renderTokenUsage = (d, isLive) => {
    const cb = d.context_budget || {};
    const bt = cb.by_tool || {};
    const respTok = cb.response_tokens || 0;
    if (respTok === 0) return null;
    const toolEntries = Object.entries(bt).sort((a, b) => b[1] - a[1]);
    return (
      <div style={{ marginTop: 8 }}>
        <strong style={{ color: T.text }}>C3 Token Usage:</strong>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 6, padding: "10px 12px", background: T.surfaceAlt, borderRadius: 6 }}>
          <div style={{ textAlign: "center", minWidth: 80 }}>
            <div className="mono" style={{ fontSize: 16, fontWeight: 700, color: T.blue }}>{(respTok / 1000).toFixed(1)}K</div>
            <div style={{ fontSize: 9, color: T.textDim }}>response tokens</div>
          </div>
          <div style={{ textAlign: "center", minWidth: 80 }}>
            <div className="mono" style={{ fontSize: 16, fontWeight: 700, color: T.accent }}>{cb.call_count || 0}</div>
            <div style={{ fontSize: 9, color: T.textDim }}>C3 calls</div>
          </div>
          {isLive ? (
            <div style={{ textAlign: "center", minWidth: 80 }}>
              <div className="mono" style={{ fontSize: 16, fontWeight: 700, color: cb.over_budget ? T.error : T.accent }}>{cb.over_budget ? "OVER" : "OK"}</div>
              <div style={{ fontSize: 9, color: T.textDim }}>budget</div>
            </div>
          ) : (
            <div style={{ textAlign: "center", minWidth: 80 }}>
              <div className="mono" style={{ fontSize: 16, fontWeight: 700, color: T.purple }}>{cb.compression_level || 0}</div>
              <div style={{ fontSize: 9, color: T.textDim }}>compression lvl</div>
            </div>
          )}
          <div style={{ textAlign: "center", minWidth: 80 }}>
            <div className="mono" style={{ fontSize: 16, fontWeight: 700, color: T.warn }}>{cb.peak_tokens ? (cb.peak_tokens / 1000).toFixed(1) + "K" : "0"}</div>
            <div style={{ fontSize: 9, color: T.textDim }}>peak response</div>
          </div>
        </div>
        {toolEntries.length > 0 && (
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6 }}>
            {toolEntries.map(([tool, tokens]) => (
              <Badge key={tool} color={getToolColor(tool)}>{tool}: {tokens >= 1000 ? (tokens / 1000).toFixed(1) + "K" : tokens}</Badge>
            ))}
          </div>
        )}
      </div>
    );
  };

  // ── Tool calls list (shared between current + past session detail) ──────────
  const renderToolCalls = (toolCalls) => {
    if (!toolCalls || toolCalls.length === 0) return null;
    return (
      <div style={{ marginTop: 8 }}>
        <strong style={{ color: T.text }}>Tool Calls ({toolCalls.length}):</strong>
        <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 6 }}>
          {toolCalls.map((tc, j) => (
            <div key={j} style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 8px", borderRadius: 4, background: T.surfaceAlt }}>
              <Badge color={getToolColor(tc.tool)}>{tc.tool}</Badge>
              <span className="mono" style={{ fontSize: 11, color: T.textMuted, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {typeof tc.args === "object" ? JSON.stringify(tc.args).slice(0, 60) : String(tc.args || "").slice(0, 60)}
              </span>
              {(tc.result_summary || tc.result) && (
                <span className="mono" style={{ fontSize: 10, color: T.textDim }}>
                  {String(tc.result_summary || tc.result).slice(0, 40)}
                </span>
              )}
              {tc.timestamp && <span className="mono" style={{ fontSize: 10, color: T.textDim }}>{localTime(tc.timestamp)}</span>}
            </div>
          ))}
        </div>
      </div>
    );
  };

  // ── Session expanded detail body ────────────────────────────────────────────
  const renderSessionDetail = (d, isLive, displayDuration) => {
    const decisions = Array.isArray(d.decisions) ? d.decisions : [];
    const filesTouched = Array.isArray(d.files_touched) ? d.files_touched : [];
    const toolCalls = Array.isArray(d.tool_calls) ? d.tool_calls : [];
    return (
      <div style={{ fontSize: 12, color: T.textMuted, lineHeight: 1.8 }}>
        <div style={{ display: "flex", gap: 16, marginBottom: 8, padding: "8px 12px", background: T.surfaceAlt, borderRadius: 6, fontSize: 11, flexWrap: "wrap" }} className="mono">
          <span><strong style={{ color: T.text }}>Start:</strong> {d.started ? new Date(d.started).toLocaleString() : "—"}</span>
          <span><strong style={{ color: T.text }}>End:</strong> {d.ended ? new Date(d.ended).toLocaleString() : (isLive ? "Running" : "—")}</span>
          {displayDuration && <span><strong style={{ color: T.text }}>Duration:</strong> {displayDuration}</span>}
        </div>
        {decisions.length > 0 && (
          <div style={{ marginBottom: 6 }}>
            <strong style={{ color: T.text }}>Decisions:</strong>
            {decisions.map((dd, j) => <div key={j} style={{ paddingLeft: 12 }}>• {dd.decision}</div>)}
          </div>
        )}
        {filesTouched.length > 0 && (
          <div><strong style={{ color: T.text }}>Files:</strong> {filesTouched.map(f => f.file).join(", ")}</div>
        )}
        {(d.context_notes || []).length > 0 && (
          <div style={{ marginTop: 4 }}><strong style={{ color: T.text }}>Notes:</strong> {d.context_notes.join("; ")}</div>
        )}
        {renderToolCalls(toolCalls)}
        {renderTokenUsage(d, isLive)}
      </div>
    );
  };

  // ── Sessions sub-view ───────────────────────────────────────────────────────
  const renderSessions = () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Stats row */}
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <StatBox label="Total Sessions" value={sessions.length} color={T.blue} loading={sessionsLoading} />
        <StatBox label="Decisions" value={sessions.reduce((s, x) => s + (x.decisions || 0), 0)} color={T.purple} loading={sessionsLoading} />
        <StatBox label="Total Duration" value={(() => {
          const t = sessions.reduce((s, x) => s + (x.duration_seconds || 0), 0);
          if (t < 60) return t + "s";
          const m = Math.floor(t / 60);
          if (m < 60) return m + "m";
          return Math.floor(m / 60) + "h " + (m % 60) + "m";
        })()} color={T.accent} loading={sessionsLoading} />
        <StatBox label="Total Tool Calls" value={sessions.reduce((s, x) => s + (x.tool_calls || 0), 0)} color={T.warn} loading={sessionsLoading} />
        <StatBox label="C3 Tokens" value={(() => {
          const t = sessions.reduce((s, x) => s + (x.response_tokens || 0), 0);
          return t >= 1000 ? (t / 1000).toFixed(1) + "K" : t;
        })()} color={T.blue} loading={sessionsLoading} />
      </div>

      {/* Current Session Card */}
      {currentSession && (() => {
        const cur = currentSession;
        const isLive = cur.live === true;
        const decisions = Array.isArray(cur.decisions) ? cur.decisions : [];
        const filesTouched = Array.isArray(cur.files_touched) ? cur.files_touched : [];
        const toolCalls = Array.isArray(cur.tool_calls) ? cur.tool_calls : [];
        const displayDuration = isLive ? liveDuration : (cur.duration || "");
        return (
          <div style={{
            background: T.surface,
            border: `1px solid ${isLive ? T.accent : T.border}30`,
            borderLeft: `3px solid ${isLive ? T.accent : T.textMuted}`,
            borderRadius: 8,
            padding: 18,
          }}>
            <div style={{
              fontSize: 10, fontWeight: 700, color: isLive ? T.accent : T.textMuted,
              textTransform: "uppercase", letterSpacing: 1.2, marginBottom: 10,
              display: "flex", alignItems: "center", gap: 6,
            }}>
              {isLive && <GlowDot color={T.accent} size={6} />}
              {isLive ? "Live Session" : "Last Session"}
            </div>
            <div style={{ fontSize: 14, fontWeight: 600, color: T.text, marginBottom: 4 }}>
              {cur.description || cur.summary || "No summary"}
            </div>
            {cur.description && cur.summary && cur.summary !== cur.description && (
              <div style={{ fontSize: 12, color: T.textMuted, marginBottom: 6 }}>{cur.summary}</div>
            )}
            <div className="mono" style={{ fontSize: 11, color: T.textMuted, marginBottom: 12 }}>
              {cur.started ? new Date(cur.started).toLocaleString() : "—"}
              {displayDuration && <span style={{ color: T.accent, marginLeft: 10 }}>{displayDuration}</span>}
            </div>
            <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
              <div style={{ flex: 1, padding: "8px 10px", background: T.surfaceAlt, borderRadius: 6, textAlign: "center" }}>
                <div className="mono" style={{ fontSize: 16, fontWeight: 700, color: T.purple }}>{decisions.length}</div>
                <div style={{ fontSize: 9, color: T.textDim }}>decisions</div>
              </div>
              <div style={{ flex: 1, padding: "8px 10px", background: T.surfaceAlt, borderRadius: 6, textAlign: "center" }}>
                <div className="mono" style={{ fontSize: 16, fontWeight: 700, color: T.blue }}>{filesTouched.length}</div>
                <div style={{ fontSize: 9, color: T.textDim }}>files</div>
              </div>
              <div style={{ flex: 1, padding: "8px 10px", background: T.surfaceAlt, borderRadius: 6, textAlign: "center" }}>
                <div className="mono" style={{ fontSize: 16, fontWeight: 700, color: T.warn }}>{toolCalls.length}</div>
                <div style={{ fontSize: 9, color: T.textDim }}>tool calls</div>
              </div>
            </div>
            <button
              onClick={() => handleExpand("current", cur.id)}
              style={{
                padding: "6px 12px", background: "none", border: `1px solid ${T.border}`,
                borderRadius: 5, color: T.accent, fontSize: 11, cursor: "pointer",
                fontFamily: "'JetBrains Mono', monospace",
              }}
            >
              {expanded === "current" ? "Collapse details" : "View details →"}
            </button>
            {expanded === "current" && (
              <div style={{ marginTop: 12, paddingTop: 12, borderTop: `1px solid ${T.border}` }}>
                {renderSessionDetail(cur, isLive, displayDuration)}
              </div>
            )}
          </div>
        );
      })()}

      {sessions.length === 0 && !currentSession && !sessionsLoading && (
        <div style={{
          background: T.surface, border: `1px solid ${T.border}`, borderRadius: 8,
          padding: 30, textAlign: "center", color: T.textMuted, fontSize: 13,
        }}>
          No sessions yet. Sessions are created automatically when the MCP server starts.
        </div>
      )}

      {/* Past Sessions */}
      {sessions.length > 0 && (
        <div>
          <div style={{
            fontSize: 12, fontWeight: 600, color: T.textMuted, textTransform: "uppercase",
            letterSpacing: 1, marginBottom: 10, display: "flex", alignItems: "center", gap: 8,
          }}>
            Saved Sessions <Badge>{sessions.length}</Badge>
          </div>
          <div style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 8, overflow: "hidden" }}>
            {sessions.map((s, i) => {
              const idx = i;
              return (
                <div key={s.id} style={{ borderBottom: i < sessions.length - 1 ? `1px solid ${T.border}` : "none" }}>
                  <div
                    onClick={() => handleExpand(idx, s.id)}
                    style={{ padding: "14px 18px", display: "flex", justifyContent: "space-between", alignItems: "center", cursor: "pointer", transition: "background 0.15s" }}
                    onMouseEnter={e => e.currentTarget.style.background = T.surfaceAlt}
                    onMouseLeave={e => e.currentTarget.style.background = "transparent"}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <I name="chevron" size={14} color={T.textMuted} style={{ transition: "transform 0.2s", transform: expanded === idx ? "rotate(90deg)" : "" }} />
                      <div>
                        <div style={{ fontSize: 13, color: T.text, fontWeight: 500 }}>{s.summary || s.description || "No summary"}</div>
                        <div className="mono" style={{ fontSize: 11, color: T.textMuted, marginTop: 2 }}>{s.started ? new Date(s.started).toLocaleString() : "—"}</div>
                      </div>
                    </div>
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", justifyContent: "flex-end" }}>
                      {s.duration && <Badge color={T.accent}>{s.duration}</Badge>}
                      <Badge color={T.purple}>{s.decisions} decisions</Badge>
                      <Badge color={T.blue}>{s.files} files</Badge>
                      {s.tool_calls > 0 && <Badge color={T.warn}>{s.tool_calls} tools</Badge>}
                      {s.response_tokens > 0 && <Badge color={T.blue}>{(s.response_tokens / 1000).toFixed(1)}K tok</Badge>}
                    </div>
                  </div>
                  {expanded === idx && detail && (
                    <div style={{ padding: "0 18px 14px 42px" }}>
                      {renderSessionDetail(detail, false, detail.duration)}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );

  // ── Activity sub-view ───────────────────────────────────────────────────────
  const renderActivity = () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      {/* Stats row */}
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <StatBox
          label="Total Events"
          value={actStats?.total || 0}
          sub={`since ${actStats?.first ? new Date(actStats.first).toLocaleDateString() : "—"}`}
          color={T.accent}
          loading={actLoading}
        />
        <StatBox label="Today" value={todayCount} sub="events today" color={T.blue} loading={actLoading} />
        {Object.entries(actStats?.by_type || {}).slice(0, 3).map(([type, count]) => (
          <StatBox key={type} label={type.replace("_", " ")} value={count} color={typeColors[type] || T.textMuted} />
        ))}
      </div>

      {/* Controls */}
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <select
          value={actFilter}
          onChange={e => setActFilter(e.target.value)}
          className="mono"
          style={{
            padding: "7px 12px", borderRadius: 6, background: T.surfaceAlt,
            border: `1px solid ${T.border}`, color: T.text, fontSize: 12, outline: "none",
          }}
        >
          <option value="">All types</option>
          {eventTypes.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
        <button
          onClick={() => setAutoRefresh(!autoRefresh)}
          className="mono"
          style={{
            padding: "7px 14px", borderRadius: 6,
            border: `1px solid ${autoRefresh ? T.accent + "60" : T.border}`,
            background: autoRefresh ? T.accentDim : "transparent",
            color: autoRefresh ? T.accent : T.textMuted,
            fontSize: 12, cursor: "pointer",
          }}
        >
          {autoRefresh ? "Auto-refresh ON" : "Auto-refresh OFF"}
        </button>
        <Btn variant="outline" onClick={loadActivity}><I name="refresh" size={13} /> Refresh</Btn>
      </div>

      {/* Event timeline */}
      <div style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 8, overflow: "hidden" }}>
        {events.length === 0 && !actLoading && (
          <div style={{ padding: 30, textAlign: "center", color: T.textMuted, fontSize: 13 }}>
            No activity logged yet. Use MCP tools to generate events.
          </div>
        )}
        {events.map((e, i) => (
          <div
            key={i}
            onClick={() => setActExpanded(actExpanded === i ? null : i)}
            style={{
              padding: "10px 16px",
              borderBottom: i < events.length - 1 ? `1px solid ${T.border}` : "none",
              cursor: "pointer",
              background: actExpanded === i ? T.surfaceAlt : "transparent",
              transition: "background 0.15s",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span className="mono" style={{ fontSize: 10, color: T.textDim, minWidth: 55, flexShrink: 0 }}>{timeAgo(e.timestamp)}</span>
              <Badge color={typeColors[e.type] || T.textMuted}>{e.type}</Badge>
              {e.type === "tool_call" && e.tool && <Badge color={getToolColor(e.tool)}>{e.tool}</Badge>}
              <span className="mono" style={{ fontSize: 11, color: T.textMuted, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {e.type === "tool_call" ? (e.result_summary || JSON.stringify(e.args || {}).slice(0, 60)) : eventSummary(e)}
              </span>
              <I name="chevron" size={12} color={T.textDim} style={{ transform: actExpanded === i ? "rotate(90deg)" : "none", transition: "transform 0.15s", flexShrink: 0 }} />
            </div>
            {actExpanded === i && (
              <pre className="mono fade-up" style={{
                marginTop: 8, padding: 10, background: T.bg, borderRadius: 6,
                fontSize: 11, color: T.textMuted, overflow: "auto", maxHeight: 200,
                whiteSpace: "pre-wrap", wordBreak: "break-all",
              }}>
                {JSON.stringify(e, null, 2)}
              </pre>
            )}
          </div>
        ))}
      </div>
    </div>
  );

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <div className="fade-up" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Sub-view toggle */}
      <div style={{ display: "flex", gap: 8 }}>
        <button style={tabStyle(subView === "sessions")} onClick={() => setSubView("sessions")}>Sessions</button>
        <button style={tabStyle(subView === "activity")} onClick={() => setSubView("activity")}>Activity</button>
      </div>

      {subView === "sessions" ? renderSessions() : renderActivity()}
    </div>
  );
};
