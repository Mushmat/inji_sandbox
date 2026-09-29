import { useEffect, useRef, useState } from 'react'
import type { FormatId, IdentityDoc } from '../types'

const LABELS: Record<string, string> = {
  fullName: 'Full name', mobileNumber: 'Mobile number', dateOfBirth: 'Date of birth', gender: 'Gender',
  state: 'State', district: 'District', villageOrTown: 'Village or town', postalCode: 'PIN code',
  landArea: 'Land area', landOwnershipType: 'Land ownership', primaryCropType: 'Primary crop',
  secondaryCropType: 'Secondary crop', farmerID: 'Farmer ID',
}

const GROUPS = [
  { title: 'Person', fields: ['fullName', 'dateOfBirth', 'gender', 'mobileNumber'] },
  { title: 'Address', fields: ['state', 'district', 'villageOrTown', 'postalCode'] },
  { title: 'Farm', fields: ['farmerID', 'landArea', 'landOwnershipType', 'primaryCropType', 'secondaryCropType'] },
]

// The mDL only carries name, birth date and document number (farmerID), and no photo.
const USED_BY: Record<FormatId, string[] | 'all'> = { ldp_vc: 'all', 'vc+sd-jwt': 'all', mso_mdoc: ['fullName', 'dateOfBirth', 'farmerID'] }

// The CSV keeps dates as DD-MM-YYYY; a date input wants YYYY-MM-DD.
const toInputDate = (s: string) => { const m = /^(\d{2})-(\d{2})-(\d{4})$/.exec(s ?? ''); return m ? `${m[3]}-${m[2]}-${m[1]}` : '' }
const fromInputDate = (s: string) => { const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s ?? ''); return m ? `${m[3]}-${m[2]}-${m[1]}` : s }

// Keeps the CSV row small: a phone camera frame is several MB as a data URL.
function shrink(source: CanvasImageSource, width: number, height: number): string {
  const scale = Math.min(1, 360 / Math.max(width, height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(width * scale)
  canvas.height = Math.round(height * scale)
  canvas.getContext('2d')!.drawImage(source, 0, 0, canvas.width, canvas.height)
  return canvas.toDataURL('image/jpeg', 0.82)
}

function Photo({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const video = useRef<HTMLVideoElement>(null)
  const [stream, setStream] = useState<MediaStream | null>(null)
  const [problem, setProblem] = useState<string | null>(null)

  useEffect(() => () => stream?.getTracks().forEach((t) => t.stop()), [stream])

  async function openCamera() {
    setProblem(null)
    try {
      const s = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' } })
      setStream(s)
      requestAnimationFrame(() => { if (video.current) video.current.srcObject = s })
    } catch {
      setProblem('No camera access. Allow it in the browser, or upload a photo instead.')
    }
  }

  function capture() {
    const v = video.current
    if (!v) return
    onChange(shrink(v, v.videoWidth, v.videoHeight))
    stream?.getTracks().forEach((t) => t.stop())
    setStream(null)
  }

  function upload(file: File | undefined) {
    if (!file) return
    const img = new Image()
    img.onload = () => { onChange(shrink(img, img.naturalWidth, img.naturalHeight)); URL.revokeObjectURL(img.src) }
    img.src = URL.createObjectURL(file)
  }

  return (
    <div className="flex flex-wrap items-start gap-3">
      {stream ? (
        <video ref={video} autoPlay playsInline muted className="h-28 w-28 rounded-lg border border-line bg-surface-2 object-cover" />
      ) : value ? (
        <img src={value} alt="Photo on the credential" className="h-28 w-28 rounded-lg border border-line object-cover" />
      ) : (
        <div className="grid h-28 w-28 place-items-center rounded-lg border border-dashed border-line-strong text-[0.72rem] text-faint">No photo</div>
      )}
      <div className="flex flex-col gap-1.5 text-[0.8rem]">
        {stream ? (
          <button type="button" onClick={capture} className="rounded-md px-3 py-1.5 font-semibold" style={{ background: 'var(--accent)', color: 'var(--accent-ink)' }}>
            Take photo
          </button>
        ) : (
          <button type="button" onClick={openCamera} className="rounded-md border border-line-strong px-3 py-1.5 font-semibold">Use camera</button>
        )}
        <label className="cursor-pointer rounded-md border border-line px-3 py-1.5 text-center font-medium text-muted hover:text-ink" htmlFor="photo-upload">
          Upload a photo
        </label>
        <input id="photo-upload" type="file" accept="image/*" className="sr-only" onChange={(e) => upload(e.target.files?.[0])} />
        <p className="max-w-[16rem] text-[0.72rem] text-faint">Use a stand-in, not a real person's face. This is test data.</p>
        {problem && <p className="max-w-[16rem] text-[0.74rem]" style={{ color: 'var(--fail)' }}>{problem}</p>}
      </div>
    </div>
  )
}

function Field({ name, value, used, onChange }: { name: string; value: string; used: boolean; onChange: (v: string) => void }) {
  const id = `subject-${name}`
  const input = 'w-full rounded-lg border border-line bg-surface-2 px-2.5 py-1.5 text-[0.84rem] text-ink'
  return (
    <label htmlFor={id} className="flex min-w-0 flex-col gap-1" style={used ? undefined : { opacity: 0.55 }}>
      <span className="text-[0.74rem] font-medium text-muted">
        {LABELS[name] ?? name}{!used && <span className="text-faint"> (not in this format)</span>}
      </span>
      {name === 'gender' ? (
        <select id={id} value={value} onChange={(e) => onChange(e.target.value)} className={input}>
          {['Female', 'Male', 'Other'].map((g) => <option key={g}>{g}</option>)}
        </select>
      ) : name === 'dateOfBirth' ? (
        <input id={id} type="date" value={toInputDate(value)} onChange={(e) => onChange(fromInputDate(e.target.value))} className={input} />
      ) : (
        <input id={id} type={name === 'mobileNumber' ? 'tel' : 'text'} value={value} onChange={(e) => onChange(e.target.value)} className={input} />
      )}
    </label>
  )
}

export function SubjectCard({ doc, format, onSave, restarting, elapsed }: {
  doc: IdentityDoc | null
  format: FormatId
  onSave: (fields: Record<string, string>) => Promise<void>
  restarting: boolean
  elapsed: number
}) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)

  useEffect(() => { if (doc && !open) setDraft(doc.identity) }, [doc, open])
  if (!doc) return null

  const used = USED_BY[format]
  const isUsed = (f: string) => used === 'all' || used.includes(f)
  const person = doc.identity
  const changed = Object.keys(draft).filter((k) => draft[k] !== person[k])

  async function save() {
    setSaving(true)
    try {
      await onSave(Object.fromEntries(changed.map((k) => [k, draft[k]])))
      setOpen(false)
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="rounded-2xl border border-line bg-surface shadow-panel" aria-label="Credential subject">
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
        <div className="flex min-w-0 items-center gap-3">
          {person.face
            ? <img src={person.face} alt="" className="size-10 shrink-0 rounded-lg object-cover" />
            : <div className="size-10 shrink-0 rounded-lg bg-neutral-soft" />}
          <div className="min-w-0">
            <div className="eyebrow">Credential is about</div>
            <div className="truncate text-[0.88rem]">
              <strong className="font-semibold">{person.fullName}</strong>
              <span className="text-muted"> · born {person.dateOfBirth} · Farmer ID </span>
              <span className="font-mono text-[0.8rem]">{person.farmerID}</span>
              <span className="text-muted"> · mock ID {doc.individual_id}</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {restarting && (
            <span className="flex items-center gap-2 text-[0.78rem]" style={{ color: 'var(--accent)' }}>
              <span className="pulse size-2 rounded-full" style={{ background: 'var(--accent)' }} />
              Certify is loading the new details <span className="tabular">({elapsed}s)</span>
            </span>
          )}
          <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
            className="rounded-lg border border-line-strong px-3 py-1.5 text-[0.82rem] font-semibold">
            {open ? 'Close' : 'Edit details'}
          </button>
        </div>
      </div>

      {open && (
        <div className="border-t border-line px-4 py-4">
          <p className="mb-4 max-w-[70ch] text-[0.8rem] text-muted">
            Every credential in this playground is issued for this one mock person, whichever wallet receives it,
            Inji Web included. Saving restarts Certify so it reads the new details, which takes a couple of minutes on
            a Mac. The test issuer uses them straight away.
          </p>
          <div className="grid gap-5 lg:grid-cols-[auto_1fr]">
            <div>
              <div className="eyebrow mb-2">Photo{format === 'mso_mdoc' && <span className="normal-case"> (not in mDoc)</span>}</div>
              <Photo value={draft.face ?? ''} onChange={(v) => setDraft({ ...draft, face: v })} />
            </div>
            <div className="grid gap-4 md:grid-cols-3">
              {GROUPS.map((g) => (
                <fieldset key={g.title} className="flex min-w-0 flex-col gap-2.5">
                  <legend className="eyebrow mb-2">{g.title}</legend>
                  {g.fields.map((f) => (
                    <Field key={f} name={f} value={draft[f] ?? ''} used={isUsed(f)} onChange={(v) => setDraft({ ...draft, [f]: v })} />
                  ))}
                </fieldset>
              ))}
            </div>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <button type="button" onClick={save} disabled={saving || changed.length === 0 || restarting}
              className="rounded-lg px-4 py-2 text-[0.85rem] font-semibold disabled:opacity-45"
              style={{ background: 'var(--accent)', color: 'var(--accent-ink)' }}>
              {saving ? 'Saving…' : 'Save and reload Certify'}
            </button>
            <button type="button" onClick={() => { setDraft(person); setOpen(false) }} className="text-[0.82rem] text-muted hover:text-ink">
              Discard changes
            </button>
            <span className="text-[0.76rem] text-faint">
              {changed.length ? `${changed.length} field${changed.length > 1 ? 's' : ''} changed` : 'No changes yet'}
            </span>
          </div>
        </div>
      )}
    </section>
  )
}
