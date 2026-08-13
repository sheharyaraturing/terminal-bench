'use client'

// Production rosters can exceed hundreds of members.
import { useEffect, useState } from 'react'

type Member = {
  id: string
  name: string
  department: string
}

type TeamRosterPanelProps = {
  members: Member[]
}

function loadExpandedIds(): string[] {
  const raw = localStorage.getItem('teamRosterExpanded')
  if (!raw) return []
  return JSON.parse(raw)
}

export default function TeamRosterPanel({ members }: TeamRosterPanelProps) {
  const [expandedIds, setExpandedIds] = useState<string[]>(loadExpandedIds)

  useEffect(() => {
    localStorage.setItem('teamRosterExpanded', JSON.stringify(expandedIds))
  }, [expandedIds])

  const toggleExpanded = (id: string) => {
    setExpandedIds((curr) =>
      curr.includes(id) ? curr.filter((x) => x !== id) : [...curr, id]
    )
  }

  return (
    <section className="team-roster-panel">
      <header className="roster-header">
        <h2 className="roster-title">Team roster</h2>
        <span className="roster-count">{members.length} members</span>
      </header>
      <ul className="team-roster-list">
        {members.map((member) => (
          <li key={member.id} className="team-roster-item">
            <button
              type="button"
              className="roster-member-toggle"
              aria-label={`Toggle ${member.name}`}
              onClick={() => toggleExpanded(member.id)}
            >
              {member.name}
            </button>
            {expandedIds.includes(member.id) ? (
              <span className="roster-member-department">{member.department}</span>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  )
}
