// Every outside link the pages use. An empty string hides the link.
export const LINKS = {
  github: 'https://github.com/benz16107/cranley',
  devpost: 'https://devpost.com/software/threshold-o1e7uj', // the draft's address; check it once the project is submitted
  video: '',
  // The app itself, behind the access code: vercel.json proxies /app, /m, /api, /assets, /models and /enter to the
  // demo door on our server (scripts/public-gate), whose own address keeps working as a fallback.
  demo: 'https://cranley.app/app', // the event's live demo. Setting it shows the button and its notice on the home page and switches the FAQ's and the privacy page's wording
}

export const DEMO = {
  label: 'Try the live demo (code from Ben)',
  notice: "Demo for HackPrinceton, Nov 14-15 2026. The building data is used under the event's terms and is deleted after the event.",
}

// Who built it. Add teammates here; the home page lists whoever is in this array.
export const TEAM: { name: string; href?: string }[] = [{ name: 'Ben Zhou', href: 'https://thebenzhou.com' }]
