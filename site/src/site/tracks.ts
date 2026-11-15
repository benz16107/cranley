// The sponsor tracks. The body of each page is generated from docs/story.md into src/content/tracks/<slug>.md;
// this file adds what the page links to.
import type { SlotId } from './slots'
import type { ProofId } from './proof'

export type Track = { slug: string; name: string; prize: string; summary: string; docs: [string, string][]; slots: SlotId[]; /** what people sent us (src/site/proof.ts) */ proof?: ProofId[]; /** the recorded interview leads the page */ interview?: true; /** YouTube id of the track's own video; its section shows only when this is set */ video?: string }

export const TRACKS: Track[] = [
  {
    slug: 'costar', name: 'CoStar', prize: 'Inside and Out: AI for the Built World',
    summary: 'All three layers in one frame (Matterport interiors, Vexcel aerial and 3D city, CoStar records), and an agent that plans, fans out per building and checks claims across layers.',
    docs: [['Record versus reality', '/docs/tools/record-vs-reality/'], ['Flood rehearsal', '/docs/tools/flood-rehearsal/'], ['Garage fit', '/docs/tools/garage-fit/'], ['Search by measurement', '/docs/tools/measure-search/'], ['Site scorecard', '/docs/tools/site-scorecard/'], ['Data sources and licences', '/docs/data-sources/'], ['The agent', '/docs/concepts/agent/']],
    slots: ['hero-loop', 'photoreal-building', 'record-vs-reality', 'flood-street'], proof: ['costar-garage-depth'],
  },
  {
    slug: 'amazon', name: 'Amazon', prize: 'Best Practical AI Innovation',
    summary: 'Ask in plain words and get a workspace you can act on. It works on your own home through the iPhone scan.',
    docs: [['Phone and iPhone app', '/docs/phone/'], ['Personas', '/docs/reference/personas/'], ['The workspace', '/docs/concepts/workspace/'], ['Getting started', '/docs/getting-started/']],
    slots: ['iphone-app', 'home-composer', 'pdf-report'], proof: ['amazon-occupational-therapists'],
  },
  {
    slug: 'peri', name: 'Peri', prize: 'Forward Deployed Challenge',
    summary: 'Built forward-deployed: we asked people and businesses what goes wrong with their buildings, by phone, in online communities and by email, then changed the tools to match.',
    docs: [['What people told us, in full (on GitHub)', 'https://github.com/benz16107/cranley/blob/main/docs/feedback.md'], ['Phone and iPhone app', '/docs/phone/'], ['Fire pre-plan', '/docs/tools/fire-preplan/'], ['Egress routes', '/docs/tools/egress-routes/'], ['Facility audit', '/docs/tools/facility-audit/'], ['Door widths', '/docs/tools/door-widths/']],
    slots: ['field-visit', 'pdf-report', 'fire-preplan'], interview: true, proof: ['quote-to-change', 'reddit-wall-2-workplaces', 'email-replies', 'outreach-at-a-glance'],
  },
  {
    slug: 'langchain', name: 'LangChain', prize: 'Best use of deepagents',
    summary: 'Planning, parallel subagents shown live, human approval that resumes from a MongoDB checkpoint, skills, memory, a rubric grader and LangSmith experiments.',
    docs: [['The agent', '/docs/concepts/agent/'], ['Sponsor integrations', '/docs/sponsor-integrations/#langchain-deepagents-langgraph-and-langsmith'], ['MCP server and CLI', '/docs/mcp/'], ['Agent and workspace API', '/docs/reference/api/agent/']],
    slots: ['agent-lanes', 'langsmith-trace'], video: 'SlK6NYPWnkI',
  },
  {
    slug: 'photon', name: 'Photon', prize: 'Build a Messaging Agent using Photon 2.0',
    summary: 'Text or call Cranley like you\'d text your real estate agent. Ask about a building the way you would ask your contractor, inspector, property manager or accessibility advisor, and the same agent and measuring tools answer in iMessage and on a phone call. The line is live for an allowlist of numbers, and on 15 Nov a real call went the whole way: the tools ran, the answer was read aloud, and the plan arrived by iMessage.',
    docs: [['Sponsor integrations', '/docs/sponsor-integrations/#photon'], ['The agent', '/docs/concepts/agent/'], ['Phone and iPhone app', '/docs/phone/'], ['Findings and reliability', '/docs/concepts/findings-and-reliability/']],
    slots: [], video: '748tXUAYXoI',
  },
  {
    slug: 'tiger-data', name: 'MLH: Tiger Data', prize: 'Best Use of Tiger Data',
    summary: 'The building facts database: hypertables, compression, continuous aggregates, DiskANN room search, a pgai vectorizer, and forks for what-ifs.',
    docs: [['Sponsor integrations', '/docs/sponsor-integrations/#tiger-cloud'], ['Search by measurement', '/docs/tools/measure-search/'], ['Similar rooms', '/docs/tools/similar-rooms/'], ['Renovate', '/docs/tools/renovate/'], ['Facts database API', '/docs/reference/api/facts/'], ['What-if API', '/docs/reference/api/whatif/']],
    slots: ['renovate', 'measure-search'], video: 'V98o5stF8iI',
  },
  {
    slug: 'mongodb', name: 'MLH: MongoDB Atlas', prize: 'Best Use of MongoDB Atlas',
    summary: 'Workspaces and their operation log, change-stream live sync with the phone, hybrid search, time series, vector memory and a guarded MCP server.',
    docs: [['Sponsor integrations', '/docs/sponsor-integrations/#mongodb-atlas'], ['The workspace', '/docs/concepts/workspace/'], ['Phone and iPhone app', '/docs/phone/'], ['Past work API', '/docs/reference/api/history/'], ['Live sync API', '/docs/reference/api/live/']],
    slots: ['live-sync', 'share-link'], video: 'Fdknkj5M3iE',
  },
]
