// Sponsor logos, shown beside the tracks we entered so a reader can tell them apart at a glance. Each is the sponsor's
// own file, taken from its own site on 2026-11-15 and not recoloured or redrawn; `source` says exactly where from.
// The files are in public/media/logos/: the one the site shows, and <slug>.png at 48 px tall on a transparent
// background for pages elsewhere that link to it (https://cranley.app/media/logos/<slug>.png).
// `on` is the background the file was made for. A dark logo gets a small light chip in the dark theme, a white logo a
// dark chip in the light theme, unless the sponsor publishes both variants (`dark`), in which case each theme gets its own.
export type Logo = { name: string; file: string; dark?: string; on: 'light' | 'dark' | 'own'; w: number; h: number; source: string; note?: string }

export const LOGOS: Record<string, Logo> = {
  costar: { name: 'CoStar Group', file: 'costar.png', on: 'light', w: 275, h: 48,
    source: 'https://www.costargroup.com/sites/costargroup.com/files/costar-group-logo.png',
    note: 'The logo in the header of costargroup.com, a PNG (no SVG is published there). costar-source.png is the file as served; costar.png is it scaled to 48 px tall.' },
  amazon: { name: 'Amazon', file: 'amazon.svg', on: 'dark', w: 100, h: 33,
    source: 'https://assets.aboutamazon.com/59/21/d658597b447d97f8bc9aef3362e0/logo-inverse-1.svg',
    note: 'The white variant Amazon serves on aboutamazon.com and its press site. No dark variant of the plain logo is published there, so amazon-on-dark.png puts the same file on a dark chip for light pages.' },
  peri: { name: 'Peri', file: 'peri.svg', on: 'own', w: 300, h: 300,
    source: 'https://peri.so/assets/favicon-Bl_613QZ.svg',
    note: 'The mark peri.so uses as its icon. It carries its own dark square.' },
  langchain: { name: 'LangChain', file: 'langchain.svg', on: 'light', w: 131, h: 24,
    source: 'https://www.langchain.com/',
    note: 'The logo in the page header, an inline SVG. Saved as a file without the width and height the page sets on it; the page draws it in its text colour.' },
  photon: { name: 'Photon', file: 'photon.svg', on: 'light', w: 100, h: 120,
    source: 'https://photon.codes/',
    note: 'The mark in the "Photon home" link of the page header, an inline SVG. Saved as a file with the SVG namespace added; the page draws it in its text colour.' },
  mongodb: { name: 'MongoDB', file: 'mongodb.svg', on: 'light', w: 1102, h: 278,
    source: 'https://webimages.mongodb.com/_com_assets/cms/kuyjf3vea2hg34taa-horizontal_default_slate_blue.svg',
    note: 'The logo in the header of mongodb.com.' },
  'tiger-data': { name: 'Tiger Data', file: 'tiger-data.svg', dark: 'tiger-data-white.svg', on: 'light', w: 1314, h: 290,
    source: 'https://assets.tigerdata.com/timescale-web/brand/tiger-data/flat-logos/logo-horizontal-black.svg',
    note: 'From the brand folder tigerdata.com serves its logos from. The white variant is logo-horizontal-white.svg in the same folder.' },
}
