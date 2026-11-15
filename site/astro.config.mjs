import { defineConfig } from 'astro/config'
import starlight from '@astrojs/starlight'

// Search engines stay out until the site is public: build with PUBLIC_INDEX=1 to let them in.
const noindex = process.env.PUBLIC_INDEX === '1' ? [] : [{ tag: 'meta', attrs: { name: 'robots', content: 'noindex' } }]

export default defineConfig({
  site: 'https://cranley.app',
  trailingSlash: 'always',
  vite: { server: { fs: { allow: ['..'] } } }, // the tokens are the App look's own file, under ../web
  integrations: [
    starlight({
      title: 'Cranley',
      description: 'Docs for Cranley: an agent that measures real buildings, inside and out.',
      logo: { light: './src/assets/mark-light.svg', dark: './src/assets/mark-dark.svg', alt: '' },
      favicon: '/favicon.svg',
      customCss: ['./src/styles/docs.css'],
      components: { SocialIcons: './src/components/DocsLinks.astro' },
      disable404Route: true,
      credits: false,
      head: noindex,
      tableOfContents: { minHeadingLevel: 2, maxHeadingLevel: 2 },
      sidebar: [
        { label: 'Start', items: ['docs', 'docs/getting-started', 'docs/faq'] },
        { label: 'Concepts', items: ['docs/concepts/workspace', 'docs/concepts/tools', 'docs/concepts/personas', 'docs/concepts/findings-and-reliability', 'docs/concepts/agent'] },
        { label: 'Tool reference', collapsed: true, items: [{ autogenerate: { directory: 'docs/tools' } }] },
        { label: 'Use it from', items: ['docs/mcp', 'docs/phone'] },
        {
          label: 'Reference',
          items: [
            { label: 'HTTP API', collapsed: true, items: [{ autogenerate: { directory: 'docs/reference/api' } }] },
            'docs/reference/result-format',
            'docs/reference/personas',
            'docs/reference/layers',
          ],
        },
        { label: 'Project', items: ['docs/architecture', 'docs/data-sources', 'docs/sponsor-integrations'] },
      ],
    }),
  ],
})
