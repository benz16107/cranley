// What people sent us, as pictures: public/media/<id>.webp, 2000 px wide (the home page's thumbnail is
// outreach-at-a-glance-thumb.webp). They are the proof thread's dark renders: every screenshot on the site is in dark
// mode (Ben's rule, 2026-11-15). They are copied in by hand, not by `generate.py --media`: each one is read for names,
// usernames, addresses and scan data first, in both polarities, and the bytes get the public sync's scans. The line of
// our r/f150 post that gave a measured garage's size is a flat box at source. In the picture of the email replies, the two people who have
// not agreed to be named are covered by flat boxes: names, addresses, signatures, the museum's event and the theatre's footer.
export const INTERVIEW = {
  url: 'https://youtu.be/xFw0Rpz9pbk', // the conversation cut with the email exchange that led to the call as its opening (15 Nov, 4:40 am)
  embed: 'https://www.youtube-nocookie.com/embed/xFw0Rpz9pbk',
  title: 'Interview with Jean Ryan, President of Disabled In Action of Metropolitan New York',
  caption: 'The recorded call with Jean Ryan, President of Disabled In Action of Metropolitan New York, cut to the conversation: the emails that led to it, then each question and her answer. She agreed to be filmed and named.',
}

const BLURRED = 'Usernames are blurred.'
export const PROOF = {
  'quote-to-change': { w: 2000, h: 1592,
    alt: 'Six things people told us, each beside the tool it changed and the commit: two quotes from the interview with Jean Ryan and four Reddit replies',
    caption: 'Six things we were told, each with the tool it changed and the commit. Names and usernames are blurred, except Jean Ryan, who agreed to be named.' },
  'reddit-wall-2-workplaces': { w: 2000, h: 1937,
    alt: 'Our questions in five Reddit communities for people who run stores, kitchens, restaurants, teams and emergency plans, with answers from each',
    caption: `What we asked in five Reddit communities for people who run workplaces, and answers from each. ${BLURRED}` },
  'email-replies': { w: 2000, h: 3230,
    alt: 'The emails we sent and what came back: "Call me" from Jean Ryan, a museum director asking for a call, written answers from the managing director of a Los Angeles theatre and the artistic director of a Houston theatre company, and two declines',
    caption: 'The email we sent and each reply to it. Names, email addresses, signatures and the names of the organisations are covered, except Jean Ryan.' },
  'outreach-at-a-glance': { w: 2000, h: 1328,
    alt: 'The outreach in numbers: the recorded interview, the people and communities who answered, the emails sent, the replies and the commits that followed',
    caption: 'The outreach, counted. It shows totals only: no names or usernames appear in it.' },
  'amazon-occupational-therapists': { w: 2000, h: 1645,
    alt: 'Our question to occupational therapists on Reddit, two therapists\' lists of what they check in a home, and the checks added to the tools from those lists',
    caption: `Two occupational therapists answered with what they check in a home, and their lists became checks in the tools. ${BLURRED}` },
  'costar-garage-depth': { w: 2000, h: 1942,
    alt: 'Reddit answers from pickup and boat owners about garage depth, each beside the change it caused in the garage fit tool',
    caption: `Pickup and boat owners on garage depth, which listings leave out, each with the change it caused in the garage fit tool. ${BLURRED} One line of our own post, which gave a measured garage's size, is covered.` },
  'reddit-wall-1-homes-and-vehicles': { w: 2000, h: 2619,
    alt: 'Our questions in five Reddit communities about homes and vehicles, with answers from each and the role each person gave',
    caption: `What we asked in five Reddit communities for pickup, boat and RV owners and occupational therapists, and answers from each. ${BLURRED} One line of our own post, which gave a measured garage's size, is covered.` },
} as const
export type ProofId = keyof typeof PROOF
