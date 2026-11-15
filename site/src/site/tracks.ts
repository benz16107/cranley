// The sponsor tracks. The body of each page is generated from docs/story.md into src/content/tracks/<slug>.md;
// this file adds what the page links to. Photon has no section in the story yet, so its words are here.
import type { SlotId } from './slots'

export type Track = { slug: string; name: string; prize: string; summary: string; docs: [string, string][]; slots: SlotId[]; body?: string[] }

export const TRACKS: Track[] = [
  {
    slug: 'costar', name: 'CoStar', prize: 'Inside and Out: AI for the Built World',
    summary: 'All three layers in one frame (Matterport interiors, Vexcel aerial and 3D city, CoStar records), and an agent that plans, fans out per building and checks claims across layers.',
    docs: [['Record versus reality', '/docs/tools/record-vs-reality/'], ['Flood rehearsal', '/docs/tools/flood-rehearsal/'], ['Garage fit', '/docs/tools/garage-fit/'], ['Search by measurement', '/docs/tools/measure-search/'], ['Site scorecard', '/docs/tools/site-scorecard/'], ['Data sources and licences', '/docs/data-sources/'], ['The agent', '/docs/concepts/agent/']],
    slots: ['hero-loop', 'photoreal-building', 'record-vs-reality', 'flood-street'],
  },
  {
    slug: 'amazon', name: 'Amazon', prize: 'Best Practical AI Innovation',
    summary: 'Ask in plain words and get a workspace you can act on. It works on your own home through the iPhone scan.',
    docs: [['Phone and iPhone app', '/docs/phone/'], ['Personas', '/docs/reference/personas/'], ['The workspace', '/docs/concepts/workspace/'], ['Getting started', '/docs/getting-started/']],
    slots: ['iphone-app', 'home-composer', 'pdf-report'],
  },
  {
    slug: 'peri', name: 'Peri', prize: 'Forward Deployed Challenge',
    summary: 'A small business is in no dataset. The iPhone app scans the shop, and the owner keeps a PDF with numbered fixes and a list of what was not checked.',
    docs: [['Phone and iPhone app', '/docs/phone/'], ['Fire pre-plan', '/docs/tools/fire-preplan/'], ['Egress routes', '/docs/tools/egress-routes/'], ['Facility audit', '/docs/tools/facility-audit/'], ['Door widths', '/docs/tools/door-widths/']],
    slots: ['field-visit', 'pdf-report', 'fire-preplan'],
  },
  {
    slug: 'langchain', name: 'LangChain', prize: 'Best use of deepagents',
    summary: 'Planning, parallel subagents shown live, human approval that resumes from a MongoDB checkpoint, skills, memory, a rubric grader and LangSmith experiments.',
    docs: [['The agent', '/docs/concepts/agent/'], ['Sponsor integrations', '/docs/sponsor-integrations/#langchain-deepagents-langgraph-and-langsmith'], ['MCP server and CLI', '/docs/mcp/'], ['Agent and workspace API', '/docs/reference/api/agent/']],
    slots: ['agent-lanes', 'langsmith-trace'],
  },
  {
    slug: 'photon', name: 'Photon', prize: 'Photon 2.0 messaging',
    summary: 'Ask Cranley by text message. In progress: not merged when this page was built.',
    docs: [['The agent', '/docs/concepts/agent/'], ['Sponsor integrations', '/docs/sponsor-integrations/#photon'], ['Phone and iPhone app', '/docs/phone/']],
    slots: [],
    body: [
      'A messaging agent over Photon is being built during the event, on its own branch. It was not merged when this page was built, so nothing on this page is a claim that it works.',
      'The plan: ask by text and get the same tool results back, with rendered images and links that open the workspace. Photos, a location or a voice note can start a check. A group chat can vote on homes. A field visit can run by message, and the PDF report arrives in the chat.',
      'It runs on the same tool registry and the same workspace document as the web app, the phone companion and the MCP server, so a number in a message comes from the same calculation as the number on the screen.',
    ],
  },
  {
    slug: 'tiger-data', name: 'MLH: Tiger Data', prize: 'Best Use of Tiger Data',
    summary: 'The building facts database: hypertables, compression, continuous aggregates, DiskANN room search, a pgai vectorizer, and forks for what-ifs.',
    docs: [['Sponsor integrations', '/docs/sponsor-integrations/#tiger-cloud'], ['Search by measurement', '/docs/tools/measure-search/'], ['Similar rooms', '/docs/tools/similar-rooms/'], ['Renovate', '/docs/tools/renovate/'], ['Facts database API', '/docs/reference/api/facts/'], ['What-if API', '/docs/reference/api/whatif/']],
    slots: ['renovate', 'measure-search'],
  },
  {
    slug: 'mongodb', name: 'MLH: MongoDB Atlas', prize: 'Best Use of MongoDB Atlas',
    summary: 'Workspaces and their operation log, change-stream live sync with the phone, hybrid search, time series, vector memory and a guarded MCP server.',
    docs: [['Sponsor integrations', '/docs/sponsor-integrations/#mongodb-atlas'], ['The workspace', '/docs/concepts/workspace/'], ['Phone and iPhone app', '/docs/phone/'], ['Past work API', '/docs/reference/api/history/'], ['Live sync API', '/docs/reference/api/live/']],
    slots: ['live-sync', 'share-link'],
  },
]
