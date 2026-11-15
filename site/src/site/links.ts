// Every outside link the pages use. An empty string hides the link.
export const LINKS = {
  github: 'https://github.com/benz16107/cranley',
  devpost: 'https://devpost.com/software/threshold-o1e7uj', // the draft's address; check it once the project is submitted
  video: '',
  demo: '', // the event's live demo; setting it shows the button and its notice on the home page
}

export const DEMO = {
  label: 'Try the live demo (code from Ben)',
  notice: "Demo for HackPrinceton, Nov 14-15 2026. The building data is used under the event's terms and is deleted after the event.",
}

// Who built it. Add teammates here; the home page lists whoever is in this array.
export const TEAM: { name: string; href?: string }[] = [{ name: 'Ben Zhou', href: 'https://thebenzhou.com' }]
