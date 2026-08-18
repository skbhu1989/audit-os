import { useEffect, useState } from 'react'
import { useApp } from '../context/AppContext'
import { dataApi } from '../api/client'
import { Card, Table, RiskBadge, Spinner, ErrorBanner } from '../components/ui'

const REQ_COLOR = { REQUIRED: 'text-red', RECOMMENDED: 'text-amber', OPTIONAL: 'text-faint' }
const COV_COLOR = { UPLOADED: 'GREEN', PARTIAL: 'AMBER', NOT_UPLOADED: 'RED' }

export default function DataCentre() {
  const { currentEngagementId } = useApp()
  const [checklist, setChecklist] = useState(null)
  const [error, setError] = useState(null)
  const [uploadStatus, setUploadStatus] = useState(null)
  const [uploading, setUploading] = useState(false)

  useEffect(() => { if (currentEngagementId) load() }, [currentEngagementId])

  function load() {
    dataApi.dataCentre(currentEngagementId).then(setChecklist).catch((e) => setError(e.message))
  }

  async function handleUpload(datasetType, file) {
    setUploading(true)
    setUploadStatus(null)
    try {
      const res = await dataApi.upload(currentEngagementId, datasetType, file)
      if (res.duplicate_detected) {
        const proceed = window.confirm(`${res.message}\n\nUpload anyway (APPEND)?`)
        if (proceed) {
          const res2 = await dataApi.upload(currentEngagementId, datasetType, file, 'APPEND')
          setUploadStatus(`${datasetType}: ${res2.status} — ${res2.rows_valid} rows`)
        } else {
          setUploadStatus(`${datasetType}: upload cancelled (duplicate)`)
        }
      } else {
        setUploadStatus(`${datasetType}: ${res.status} — ${res.rows_valid} rows, ${res.error_count} errors, ${res.warning_count} warnings`)
      }
      load()
    } catch (e) {
      setUploadStatus(`${datasetType}: failed — ${e.message}`)
    } finally {
      setUploading(false)
    }
  }

  if (!currentEngagementId) return <div className="text-faint p-10 text-center">Select an engagement first.</div>
  if (error) return <ErrorBanner message={error} />
  if (!checklist) return <Spinner />

  return (
    <div className="flex flex-col gap-4">
      <Card title="Data Readiness" eyebrow={`${checklist.overall_coverage_pct}% of required datasets uploaded`}>
        <div className="h-2 bg-paper-line rounded overflow-hidden">
          <div
            className="h-full bg-gold transition-all"
            style={{ width: `${checklist.overall_coverage_pct}%` }}
          />
        </div>
        {uploadStatus && <div className="text-[12px] font-mono text-slate mt-3">{uploadStatus}</div>}
      </Card>

      <Card title="Dynamic Checklist" eyebrow="What's uploaded, what's missing, what's partial (Section 39)">
        <Table
          columns={[
            { key: 'label', label: 'Dataset' },
            { key: 'requirement', label: 'Requirement', render: (r) => <span className={REQ_COLOR[r.requirement]}>{r.requirement}</span> },
            { key: 'coverage_status', label: 'Coverage', render: (r) => <RiskBadge level={COV_COLOR[r.coverage_status] || 'NO_DATA'} /> },
            { key: 'periods_uploaded', label: 'Periods', align: 'center' },
            { key: 'reason', label: 'Why', muted: true },
            {
              key: 'upload', label: 'Upload', align: 'right',
              render: (r) => (
                <label
                  className={`inline-block text-[13px] font-medium px-3.5 py-2 rounded cursor-pointer border border-gold text-gold bg-gold-soft hover:bg-gold/10 ${uploading ? 'opacity-40 pointer-events-none' : ''}`}
                >
                  <input
                    type="file" accept=".csv,.xlsx,.xls" className="hidden"
                    disabled={uploading}
                    onChange={(e) => e.target.files[0] && handleUpload(r.dataset_type, e.target.files[0])}
                  />
                  {uploading ? '…' : 'Choose file'}
                </label>
              ),
            },
          ]}
          rows={checklist.checklist}
        />
      </Card>
    </div>
  )
}
