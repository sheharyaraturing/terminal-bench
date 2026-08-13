'use client'

import { useEffect, useState } from 'react'

const EXPANDED_STORAGE_KEY = 'teamRosterExpanded:v1'

const ROSTER_ITEM_CSS = `.team-roster-item {
  content-visibility: auto;
  contain-intrinsic-size: 0 56px;
}
.roster-member-department {
  display: none;
}
.team-roster-item.is-expanded .roster-member-department {
  display: inline;
}`

type Member = {
  id: string
  name: string
  department: string
}

type TeamRosterPanelProps = {
  members: Member[]
}

function readBootstrapExpandedIds(): string[] {
  if (typeof window === 'undefined') return []
  const ids = (window as { __ROSTER_EXPANDED__?: string[] }).__ROSTER_EXPANDED__
  return Array.isArray(ids) ? ids : []
}

function saveExpandedIds(ids: string[]) {
  try {
    localStorage.setItem(EXPANDED_STORAGE_KEY, JSON.stringify(ids))
  } catch {
    // Storage may be unavailable in private browsing or when quota is exceeded.
  }
}

export default function TeamRosterPanel({ members }: TeamRosterPanelProps) {
  // The pre-hydration script below stashes the persisted ids on window and
  // patches the server-rendered rows before React hydrates. Reading the same
  // value here makes the first client render match the already-patched DOM, so
  // there is no hydration mismatch and no first-paint flash.
  const [expandedIds, setExpandedIds] = useState<string[]>(readBootstrapExpandedIds)

  useEffect(() => {
    saveExpandedIds(expandedIds)
  }, [expandedIds])

  const toggleExpanded = (id: string) => {
    setExpandedIds((curr) =>
      curr.includes(id) ? curr.filter((x) => x !== id) : [...curr, id]
    )
  }

  return (
    <section className="team-roster-panel">
      <style>{ROSTER_ITEM_CSS}</style>
      <header className="roster-header">
        <h2 className="roster-title">Team roster</h2>
        <span className="roster-count">{members.length} members</span>
      </header>
      <ul className="team-roster-list">
        {members.map((member) => (
          <li
            key={member.id}
            className={
              'team-roster-item' +
              (expandedIds.includes(member.id) ? ' is-expanded' : '')
            }
            data-member-id={member.id}
          >
            <button
              type="button"
              className="roster-member-toggle"
              aria-label={`Toggle ${member.name}`}
              onClick={() => toggleExpanded(member.id)}
            >
              {member.name}
            </button>
            <span className="roster-member-department">{member.department}</span>
          </li>
        ))}
      </ul>
      <script
        dangerouslySetInnerHTML={{
          __html: `(function () {
  try {
    var raw = localStorage.getItem('teamRosterExpanded:v1');
    var ids = raw ? JSON.parse(raw) : [];
    window.__ROSTER_EXPANDED__ = ids;
    var lookup = {};
    for (var i = 0; i < ids.length; i += 1) lookup[ids[i]] = true;
    var items = document.querySelectorAll('.team-roster-item[data-member-id]');
    for (var j = 0; j < items.length; j += 1) {
      if (lookup[items[j].getAttribute('data-member-id')]) {
        items[j].classList.add('is-expanded');
      }
    }
  } catch (e) {
    window.__ROSTER_EXPANDED__ = [];
  }
})();`,
        }}
      />
    </section>
  )
}
