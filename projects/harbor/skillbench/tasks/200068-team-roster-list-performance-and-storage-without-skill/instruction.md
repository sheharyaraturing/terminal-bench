We're polishing the team roster panel on our Next.js HR dashboard. The starter at inputs/team_roster_panel.tsx lets HR browse the member list and expand rows to see departments. Before release, QA flagged two problems: the roster is slow to render for large teams, and expanded-row state is saved without a version, so stored values can break across releases. Address this feedback following React best practices, and save the updated file as /root/team_roster_panel.fixed.tsx.

Requirements:

- User-visible behavior stays the same.
- Issue 1 (list): the initial render is slow for large rosters and needs to be addressed.
- Issue 2 (prefs): expanded-row state must restore reliably on return visits without breaking across releases, and must degrade gracefully if persistence isn't available. Because the dashboard is server-rendered, restoring this state must not cause a hydration mismatch or a flash of incorrect content on first paint.
