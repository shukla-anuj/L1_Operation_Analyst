import { useEffect, useMemo, useState } from 'react'

type RCA = {
  root_cause: string
  contributing_factors: string[]
  resolution: {
    immediate: string
    long_term: string
  }
  confidence: number
  evidence_refs: string[]
}

type BackendRca = {
  root_cause?: string
  contributing_factors?: string[]
  timeline?: string[]
  resolution?: {
    immediate?: string
    long_term?: string
  }
  confidence_hint?: number
  evidence_refs?: string[]
  rca_draft?: string
  selected?: BackendRca
  candidates?: BackendRca[]
}

type DashboardIncident = {
  incident_id: number
  service: string | null
  error_log: string | null
  root_cause: string | null
  resolution: string | null
  validated: boolean
  created_at: string
  rca_id: number | null
  rca_json: BackendRca
  evidence: Record<string, unknown>
  rca_created_at: string | null
}

type ThemeMode = 'dark' | 'light'

const INCIDENTS_PER_PAGE = 3

export default function App() {
  const [incidents, setIncidents] = useState<DashboardIncident[]>([])
  const [selectedIncident, setSelectedIncident] = useState<DashboardIncident | null>(null)
  const [loadingIncidents, setLoadingIncidents] = useState(true)
  const [stackTrace, setStackTrace] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<RCA | null>(null)
  const [error, setError] = useState('')
  const [activeRcaIndex, setActiveRcaIndex] = useState(0)
  const [selectedIncidentId, setSelectedIncidentId] = useState<string | null>(null)
  const [theme, setTheme] = useState<ThemeMode>('dark')
  const [incidentPage, setIncidentPage] = useState(0)

  const isValid = useMemo(() => stackTrace.trim().length > 0, [stackTrace])

  const handleAnalyze = async () => {
    if (!isValid) {
      setError('Please paste a stack trace before analysis.')
      return
    }

    setLoading(true)
    setError('')
    setResult(null)
    setSelectedIncidentId(null)

    try {
      const response = await fetch('http://localhost:8000/api/incidents/analyze', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ incident_query: stackTrace }),
      })

      if (!response.ok) {
        throw new Error('Failed to analyze incident')
      }

      const analyzedIncident: DashboardIncident = await response.json()
      setSelectedIncident(analyzedIncident)
      setSelectedIncidentId(String(analyzedIncident.incident_id))

      const dashboardResponse = await fetch(
        'http://localhost:8000/api/dashboard/today',
      )

      if (dashboardResponse.ok) {
        const data: { incidents: DashboardIncident[] } =
          await dashboardResponse.json()
        setIncidents(data.incidents)
        setIncidentPage(0)
      }
    } catch {
      setError('Failed to analyze the incident. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const convertRca = (incident: DashboardIncident): RCA => {
    const rca = incident.rca_json.candidates?.[activeRcaIndex]
      ?? incident.rca_json.selected
      ?? incident.rca_json

    return {
      root_cause:
        rca.root_cause ??
        incident.root_cause ??
        'Root cause is not available.',
      contributing_factors: rca.contributing_factors ?? [],
      resolution: {
        immediate: rca.resolution?.immediate ?? 'Immediate resolution is not available.',
        long_term: rca.resolution?.long_term ?? 'Long-term resolution is not available.',
      },
      confidence: rca.confidence_hint ?? 0,
      evidence_refs: rca.evidence_refs ?? [],
    }
  }

  const rcaCandidates = selectedIncident?.rca_json.candidates ?? []
  const incidentPageCount = Math.max(
    1,
    Math.ceil(incidents.length / INCIDENTS_PER_PAGE),
  )
  const visibleIncidents = incidents.slice(
    incidentPage * INCIDENTS_PER_PAGE,
    (incidentPage + 1) * INCIDENTS_PER_PAGE,
  )

  const openIncident = async (incidentId: number) => {
    try {
      setError('')
      setSelectedIncidentId(String(incidentId))
      setResult(null)

      const response = await fetch(`http://localhost:8000/api/incidents/${incidentId}`)

      if (!response.ok) {
        throw new Error('Failed to load incident details')
      }

      const incident: DashboardIncident = await response.json()
      setSelectedIncident(incident)
      setActiveRcaIndex(0)
    } catch {
      setError('Unable to load incident details.')
    }
  }

  const displayResult = result ?? (
    selectedIncident ? convertRca(selectedIncident) : null
  )
  const showStats = Boolean(displayResult)

  useEffect(() => {
    if (rcaCandidates.length === 0) {
      setActiveRcaIndex(0)
      return
    }

    const highestConfidenceIndex = rcaCandidates.reduce(
      (bestIndex, candidate, index, candidates) =>
        (candidate.confidence_hint ?? 0) >
          (candidates[bestIndex].confidence_hint ?? 0)
          ? index
          : bestIndex,
      0,
    )

    setActiveRcaIndex(highestConfidenceIndex)
  }, [selectedIncident])

  useEffect(() => {
    const loadTodaysIncidents = async () => {
      try {
        setLoadingIncidents(true)

        const response = await fetch(
          'http://localhost:8000/api/dashboard/today',
        )

        if (!response.ok) {
          throw new Error('Failed to load incidents')
        }

        const data: { incidents: DashboardIncident[] } =
          await response.json()

        setIncidents(data.incidents)
        setIncidentPage(0)

        if (data.incidents.length > 0) {
          setSelectedIncident(data.incidents[0])
          setSelectedIncidentId(String(data.incidents[0].incident_id))
          setActiveRcaIndex(0)
        }
      } catch {
        setError('Unable to load today\'s incidents.')
      } finally {
        setLoadingIncidents(false)
      }
    }

    void loadTodaysIncidents()
  }, [])

  useEffect(() => {
    setIncidentPage((page) => Math.min(page, incidentPageCount - 1))
  }, [incidentPageCount])

  return (
    <div className={theme === 'dark' ? 'app-shell dark' : 'app-shell light'}>
      <header className="topbar">
        <div className="brand-block">
          <span className="brand-mark" aria-label="RCA AI mark">
            <span className="brand-core">RCA</span>
            <span className="brand-node brand-node-top" />
            <span className="brand-node brand-node-right" />
            <span className="brand-node brand-node-bottom" />
          </span>
          <div>
            <p className="eyebrow">AI Incident Intelligence</p>
            <h1>RCA CoPilot</h1>
          </div>
        </div>

        <div className="toolbar">
          <div className="theme-toggle" aria-label="Theme toggle">
            <button
              type="button"
              className={theme === 'dark' ? 'segment active' : 'segment'}
              onClick={() => setTheme('dark')}
            >
              Dark
            </button>
            <button
              type="button"
              className={theme === 'light' ? 'segment active' : 'segment'}
              onClick={() => setTheme('light')}
            >
              Light
            </button>
          </div>
        </div>
      </header>

      <div className="dashboard-shell">
        <aside className="sidebar panel">
          <div className="sidebar-header">
            <h2>Today's Incidents</h2>
            <div className="incident-pagination">
              <span className="incident-count">{incidents.length}</span>
              <button
                type="button"
                className="pagination-button"
                aria-label="Previous incidents"
                disabled={incidentPage === 0}
                onClick={() => setIncidentPage((page) => page - 1)}
              >
                Prev
              </button>
              <span className="pagination-status" aria-live="polite">
                {incidentPage + 1}/{incidentPageCount}
              </span>
              <button
                type="button"
                className="pagination-button"
                aria-label="Next incidents"
                disabled={incidentPage >= incidentPageCount - 1}
                onClick={() => setIncidentPage((page) => page + 1)}
              >
                Next
              </button>
            </div>
          </div>

          {loadingIncidents ? (
            <p>Loading incidents...</p>
          ) : (
            <div className="incident-list">
              {visibleIncidents.map((incident) => (
                <button
                  key={incident.incident_id}
                  type="button"
                  className={
                    selectedIncidentId === String(incident.incident_id)
                      ? 'incident-item active'
                      : 'incident-item'
                  }
                  onClick={() => openIncident(incident.incident_id)}
                >
                  <div className="incident-row">
                    <strong>INC-{incident.incident_id}</strong>
                    <span className="severity info">Incident</span>
                  </div>

                  <p>
                    {incident.error_log?.split('\n')[0] ?? 'Unknown incident'}
                  </p>

                  <div className="incident-meta">
                    <span>{incident.service ?? 'Unknown service'}</span>
                    <span>
                      {new Date(incident.created_at).toLocaleTimeString()}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </aside>

        <main className="workspace">
          {showStats && selectedIncident && (
            <section className="stats-grid">
              <div className="stat-card stat-confidence">
                <span>Confidence</span>
                <strong>{displayResult!.confidence}%</strong>
              </div>
              <div className="stat-card stat-similarity">
                <span>Similarity</span>
                <strong>Unavailable</strong>
              </div>
              <div className="stat-card stat-age">
                <span>Incident Age</span>
                <strong>
                  {Math.max(
                    0,
                    Math.floor(
                      (Date.now() - new Date(selectedIncident.created_at).getTime()) /
                        60000,
                    ),
                  )}{' '}
                  min
                </strong>
              </div>
              <div className="stat-card stat-ready">
                <span>RCA Ready</span>
                <strong>Yes</strong>
              </div>
            </section>
          )}

          <div className="layout">
            <section className="panel input-panel">
              <div className="panel-header">
                <h2>New Incident</h2>
                <button
                  type="button"
                  className="status-dot"
                  onClick={() => setStackTrace('')}
                >
                  Clear
                </button>
              </div>

              <textarea
                value={stackTrace}
                onChange={(e) => setStackTrace(e.target.value)}
                placeholder="Paste the stack trace, exception, or error logs here..."
              />

              <div className="action-row">
                <button onClick={handleAnalyze} disabled={loading || !isValid}>
                  {loading ? 'Analyzing...' : 'Analyze Incident'}
                </button>
              </div>

              {error && <div className="error-box">{error}</div>}
            </section>

            {displayResult ? (
              <section className="panel result-panel">
                <div className="panel-header">
                  <h2>Analysis Result</h2>
                  <span className="confidence-pill">{displayResult.confidence}% confidence</span>
                </div>

                {rcaCandidates.length > 0 && (
                  <>
                    <div className="rca-tabs" role="tablist" aria-label="RCA candidates">
                      {rcaCandidates.map((candidate, index) => (
                        <button
                          key={`${candidate.root_cause ?? 'rca'}-${index}`}
                          type="button"
                          role="tab"
                          aria-selected={activeRcaIndex === index}
                          className={activeRcaIndex === index ? 'rca-tab active' : 'rca-tab'}
                          onClick={() => {
                            setActiveRcaIndex(index)
                            setResult(null)
                          }}
                        >
                          <span>RCA {index + 1}</span>
                          <small>Confidence: {candidate.confidence_hint ?? 0}%</small>
                        </button>
                      ))}
                    </div>

                    <div className="rca-detail-panel">
                      <div className="compact-rca-grid">
                        <div className="result-section result-factors compact-rca-section">
                          <label>Contributing Factors</label>
                          {displayResult.contributing_factors.length > 0 ? (
                            <ul className="plain-list">
                              {displayResult.contributing_factors.map((factor) => (
                                <li key={factor}>{factor}</li>
                              ))}
                            </ul>
                          ) : (
                            <p>None recorded.</p>
                          )}
                        </div>

                        <div className="result-section result-evidence compact-rca-section">
                          <label>Evidence References</label>
                          {displayResult.evidence_refs.length > 0 ? (
                            <ul className="plain-list">
                              {displayResult.evidence_refs.map((reference) => (
                                <li key={reference}>{reference}</li>
                              ))}
                            </ul>
                          ) : (
                            <p>No evidence references available.</p>
                          )}
                        </div>
                      </div>

                      <div className="result-section result-resolution">
                        <label>Resolution</label>
                        <p><strong>Immediate:</strong> {displayResult.resolution.immediate}</p>
                        <p><strong>Long term:</strong> {displayResult.resolution.long_term}</p>
                      </div>
                    </div>
                  </>
                )}
              </section>
            ) : (
              <section className="panel empty-panel">
                <h2>No incident selected</h2>
                <p>Select one of the incidents on the left or paste a new stack trace to begin RCA analysis.</p>
              </section>
            )}
          </div>
        </main>
      </div>
    </div>
  )
}