import type { Catalog, RoleOption, Selection } from '../types'

type RoleKey = 'issuer' | 'wallet' | 'verifier'

const ROLES: { key: RoleKey; title: string; list: keyof Pick<Catalog, 'issuers' | 'wallets' | 'verifiers'>; color: string; soft: string }[] = [
  { key: 'issuer', title: 'Issuer', list: 'issuers', color: 'var(--issuer)', soft: 'var(--issuer-soft)' },
  { key: 'wallet', title: 'Wallet', list: 'wallets', color: 'var(--wallet)', soft: 'var(--wallet-soft)' },
  { key: 'verifier', title: 'Verifier', list: 'verifiers', color: 'var(--verifier)', soft: 'var(--verifier-soft)' },
]

function Option({ id, option, selected, color, soft, onPick, disabled }: {
  id: string; option: RoleOption; selected: boolean; color: string; soft: string; onPick: () => void; disabled: boolean
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      id={`role-${id}`}
      disabled={disabled}
      onClick={onPick}
      className="w-full rounded-xl border p-3.5 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-60"
      style={{
        borderColor: selected ? color : 'var(--line)',
        background: selected ? soft : 'var(--surface)',
        boxShadow: selected ? `inset 0 0 0 1px ${color}` : undefined,
      }}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="font-semibold leading-tight">{option.name}</span>
        <span
          className="shrink-0 rounded-full px-2 py-0.5 text-[0.66rem] font-semibold tracking-wide uppercase"
          style={option.inji
            ? { background: 'var(--accent-soft)', color: 'var(--accent)' }
            : { background: 'var(--neutral-soft)', color: 'var(--muted)' }}
        >
          {option.inji ? 'Inji' : 'Non-Inji'}
        </span>
      </div>
      <div className="mt-1 font-mono text-[0.72rem] text-muted">
        {option.version ? `${option.version} · ` : ''}{option.protocol}
      </div>
      <p className="mt-2 text-[0.8rem] leading-snug text-muted">{option.detail}</p>
      {option.interactive && (
        <p className="mt-2 text-[0.74rem] font-medium" style={{ color }}>You drive this wallet yourself</p>
      )}
    </button>
  )
}

function Connector({ label }: { label: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-1 lg:mt-24 lg:flex-col lg:items-center lg:justify-start lg:gap-1 lg:py-0" aria-hidden="true">
      <span className="font-mono text-[0.68rem] font-medium text-muted">{label}</span>
      <svg className="hidden lg:block" width="64" height="10" viewBox="0 0 64 10">
        <path d="M0 5h58" stroke="var(--line-strong)" strokeWidth="1.5" strokeDasharray="3 3" />
        <path d="M56 1l6 4-6 4" fill="none" stroke="var(--muted)" strokeWidth="1.5" />
      </svg>
      <svg className="lg:hidden" width="10" height="22" viewBox="0 0 10 22">
        <path d="M5 0v16" stroke="var(--line-strong)" strokeWidth="1.5" strokeDasharray="3 3" />
        <path d="M1 14l4 6 4-6" fill="none" stroke="var(--muted)" strokeWidth="1.5" />
      </svg>
    </div>
  )
}

export function RoleSelector({ catalog, selection, onChange, locked }: {
  catalog: Catalog; selection: Selection; onChange: (s: Selection) => void; locked: boolean
}) {
  return (
    <div className="grid grid-cols-1 gap-2 lg:grid-cols-[1fr_auto_1fr_auto_1fr] lg:gap-3">
      {ROLES.map((role, i) => (
        <div key={role.key} className="contents">
          <fieldset className="min-w-0" role="radiogroup" aria-label={role.title}>
            <legend className="mb-2 flex w-full items-center gap-2">
              <span className="size-2.5 rounded-full" style={{ background: role.color }} />
              <span className="font-display text-lg font-semibold tracking-tight">{role.title}</span>
            </legend>
            <div className="flex flex-col gap-2">
              {Object.entries(catalog[role.list]).map(([id, option]) => (
                <Option
                  key={id}
                  id={id}
                  option={option}
                  selected={selection[role.key] === id}
                  color={role.color}
                  soft={role.soft}
                  disabled={locked}
                  onPick={() => onChange({ ...selection, [role.key]: id })}
                />
              ))}
            </div>
          </fieldset>
          {i < ROLES.length - 1 && <Connector label={i === 0 ? 'OpenID4VCI' : 'OpenID4VP'} />}
        </div>
      ))}
    </div>
  )
}
